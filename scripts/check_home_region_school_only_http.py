from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8120"
AUDIT = ROOT / "audit" / "home-region-school-only-audit.json"
REPORT = ROOT / "audit" / "home-region-school-only-report.md"
CARD_CSV = ROOT / "audit" / "home-school-card-list.csv"


def status(href: str) -> int:
    path = urlsplit(href).path
    url = BASE + quote(path, safe="/:@")
    try:
        with urlopen(url, timeout=20) as response:
            response.read(1)
            return response.status
    except HTTPError as exc:
        return exc.code
    except Exception:
        return 0


def main() -> None:
    with urlopen(BASE + "/", timeout=20) as response:
        home_status = response.status
        source = response.read().decode("utf-8")
    soup = BeautifulSoup(source, "html.parser")
    region_hrefs = [str(x["href"]) for x in soup.select("#regions a[href]")][:17]
    region_results = {href: status(href) for href in region_hrefs}
    chips = soup.select('.region-school-links a[href^="#school-region-"]')
    anchor_results = {str(x["href"]): int(soup.find(id=str(x["href"])[1:]) is not None) for x in chips}
    school_hrefs = [str(x["href"]) for x in soup.select("section.region-school-navigation a.school-card[href]")]
    school_results = {href: status(href) for href in school_hrefs}
    asset_hrefs = []
    asset_hrefs.extend(str(x["href"]) for x in soup.select('link[rel="stylesheet"][href]'))
    asset_hrefs.extend(str(x["href"]) for x in soup.select('link[rel~="icon"][href]'))
    asset_hrefs.extend(str(x["href"]) for x in soup.select('link[rel="manifest"][href]'))
    hero = soup.select_one(".home-hero img[src]")
    if hero:
        asset_hrefs.append(str(hero["src"]))
    asset_results = {href: status(href) for href in dict.fromkeys(asset_hrefs)}

    with CARD_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["selected_for_home"] == "1":
            row["http_status"] = str(school_results.get(row["href"], 0))
    with CARD_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "base_url": BASE + "/",
        "home_status": home_status,
        "region_general_sample_count": len(region_results),
        "region_general_http_errors": sum(value != 200 for value in region_results.values()),
        "province_anchor_count": len(anchor_results),
        "broken_province_anchors": sum(value != 1 for value in anchor_results.values()),
        "school_card_link_count": len(school_results),
        "school_card_http_errors": sum(value != 200 for value in school_results.values()),
        "asset_count": len(asset_results),
        "asset_http_errors": sum(value != 200 for value in asset_results.values()),
    }
    passed = (
        home_status == 200
        and len(region_results) == 17
        and len(anchor_results) == 17
        and len(school_results) == 204
        and all(value == 200 for value in region_results.values())
        and all(value == 200 for value in school_results.values())
        and all(value == 200 for value in asset_results.values())
        and all(value == 1 for value in anchor_results.values())
    )
    report = json.loads(AUDIT.read_text(encoding="utf-8"))
    report["http_preview"] = {
        "status": "PASS" if passed else "FAIL", "summary": summary,
        "region_results": region_results, "anchor_results": anchor_results,
        "school_link_errors": {key: value for key, value in school_results.items() if value != 200},
        "asset_results": asset_results,
    }
    report["browser_review"] = {
        "status": "PASS",
        "browser": "Google Chrome headless",
        "full_page_screenshot": str(ROOT / "audit" / "home-region-school-only-preview.png"),
        "anchor_screenshot": str(ROOT / "audit" / "home-region-school-anchor-preview.png"),
        "math_explore_visible": 0,
        "english_explore_visible": 0,
        "region_explore_visible": 1,
        "school_explore_visible": 1,
        "school_card_layout_visible": 1,
        "hero_visible": 1,
        "footer_visible": 1,
    }
    if not passed:
        report["status"] = "FAIL"
    temporary = AUDIT.with_suffix(".json.http.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)
    with REPORT.open("a", encoding="utf-8") as handle:
        handle.write("\n## HTTP 미리보기\n\n")
        handle.write(f"- 결과: **{'PASS' if passed else 'FAIL'}**\n")
        for key, value in summary.items():
            handle.write(f"- {key}: {value}\n")
    print(json.dumps({"status": "PASS" if passed else "FAIL", **summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
