from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit" / "school-excel-linkfix-audit.json"
BASE = "http://127.0.0.1:8100/"


def status(url: str) -> int:
    try:
        with urlopen(url, timeout=20) as response:
            response.read(1)
            return response.status
    except HTTPError as exc:
        return exc.code
    except Exception:
        return 0


def local_url(href: str) -> str:
    path = urlsplit(href).path
    return BASE.rstrip("/") + quote(path, safe="/:@")


def main() -> None:
    with urlopen(BASE, timeout=20) as response:
        home_status = response.status
        source = response.read().decode("utf-8")
    soup = BeautifulSoup(source, "html.parser")
    region_slugs = ["구로구과외", "구로구구로구수학과외", "구로구구로구영어과외", "개봉동과외"]
    region_results = {slug: status(BASE + quote(slug) + "/") for slug in region_slugs}
    anchor_links = soup.select(".region-school-navigation a[href^='#schools-']")
    anchor_results = {
        str(link["href"]): int(soup.find(id=str(link["href"])[1:]) is not None)
        for link in anchor_links
    }
    school_hrefs = sorted({str(x["href"]) for x in soup.select("section.region-school-navigation .school-card-links a[href]")})
    school_results = {href: status(local_url(href)) for href in school_hrefs}
    asset_hrefs = sorted({
        str(x.get("href") or x.get("src"))
        for x in soup.select("link[rel='stylesheet'][href], link[rel~='icon'][href], link[rel='manifest'][href], img[src]")
    })
    asset_results = {href: status(local_url(href)) for href in asset_hrefs}
    summary = {
        "base_url": BASE,
        "home_status": home_status,
        "representative_region_checks": len(region_results),
        "representative_region_http_errors": sum(x != 200 for x in region_results.values()),
        "province_anchor_count": len(anchor_results),
        "broken_province_anchors": sum(x != 1 for x in anchor_results.values()),
        "school_link_count": len(school_results),
        "school_link_http_errors": sum(x != 200 for x in school_results.values()),
        "asset_count": len(asset_results),
        "asset_http_errors": sum(x != 200 for x in asset_results.values()),
    }
    passed = (
        home_status == 200
        and len(anchor_results) == 17
        and all(x == 200 for x in region_results.values())
        and all(x == 200 for x in school_results.values())
        and all(x == 200 for x in asset_results.values())
        and all(x == 1 for x in anchor_results.values())
    )
    report = json.loads(AUDIT.read_text(encoding="utf-8"))
    report["http_preview"] = {
        "status": "PASS" if passed else "FAIL",
        "summary": summary,
        "region_results": region_results,
        "province_anchor_results": anchor_results,
        "school_link_errors": {k: v for k, v in school_results.items() if v != 200},
        "asset_errors": {k: v for k, v in asset_results.items() if v != 200},
    }
    if not passed:
        report["status"] = "FAIL"
    temporary = AUDIT.with_suffix(".json.http.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)
    print(json.dumps({"status": "PASS" if passed else "FAIL", **summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
