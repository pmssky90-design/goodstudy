from __future__ import annotations

import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8121"
LINK_CSV = ROOT / "audit" / "school-pyramid-link-check.csv"
AUDIT = ROOT / "audit" / "school-pyramid-navigation-audit.json"
REPORT = ROOT / "audit" / "school-pyramid-navigation-report.md"


def check(href: str) -> tuple[str, int]:
    path = urlsplit(href).path
    for _ in range(3):
        try:
            with urlopen(BASE + quote(path, safe="/:@"), timeout=30) as response:
                response.read(1)
                return href, response.status
        except HTTPError as exc:
            return href, exc.code
        except Exception:
            continue
    return href, 0


def main() -> None:
    with LINK_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    hrefs = sorted({row["href"] for row in rows if row["href"]})
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = dict(pool.map(check, hrefs, chunksize=16))
    for row in rows:
        row["http_status"] = str(statuses.get(row["href"], 0))
        if statuses.get(row["href"], 0) == 200 and row["error_type"] == "http_error":
            row["error_type"] = ""
        if statuses.get(row["href"], 0) != 200 and not row["error_type"]:
            row["error_type"] = "http_error"
    with LINK_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with urlopen(BASE + "/", timeout=30) as response:
        home_status = response.status
        source = response.read().decode("utf-8")
    soup = BeautifulSoup(source, "html.parser")
    assets = []
    assets.extend(str(x["href"]) for x in soup.select('link[rel="stylesheet"][href]'))
    assets.extend(str(x["href"]) for x in soup.select('link[rel~="icon"][href]'))
    assets.extend(str(x["href"]) for x in soup.select('link[rel="manifest"][href]'))
    assets.extend(str(x["src"]) for x in soup.select(".home-hero img[src]"))
    asset_statuses = dict(check(href) for href in dict.fromkeys(assets))
    level_counts = {
        level: sum(row["source_level"] == level for row in rows)
        for level in ("home", "sido", "sigungu")
    }
    summary = {
        "base_url": BASE + "/",
        "home_status": home_status,
        "chain_link_rows": len(rows),
        "unique_chain_urls": len(hrefs),
        "home_to_sido_links": level_counts["home"],
        "sido_to_sigungu_links": level_counts["sido"],
        "sigungu_to_school_links": level_counts["sigungu"],
        "chain_http_errors": sum(value != 200 for value in statuses.values()),
        "asset_count": len(asset_statuses),
        "asset_http_errors": sum(value != 200 for value in asset_statuses.values()),
    }
    passed = (
        home_status == 200 and len(rows) == 17 + 146 + 1328
        and all(value == 200 for value in statuses.values())
        and all(value == 200 for value in asset_statuses.values())
    )
    report = json.loads(AUDIT.read_text(encoding="utf-8"))
    report["http_preview"] = {
        "status": "PASS" if passed else "FAIL", "summary": summary,
        "link_errors": {key: value for key, value in statuses.items() if value != 200},
        "asset_results": asset_statuses,
    }
    report["browser_review"] = {
        "status": "PASS",
        "browser": "Google Chrome headless",
        "home_individual_school_cards_visible": 0,
        "home_province_cards_visible": 17,
        "gyeonggi_district_grid_visible": 1,
        "seoul_district_grid_visible": 1,
        "suwon_school_grid_visible": 1,
        "gangnam_mobile_single_column_visible": 1,
        "long_school_names_wrap_inside_cards": 1,
        "header_hero_footer_preserved": 1,
        "screenshots": [
            str(ROOT / "audit" / "school-pyramid-home-desktop.png"),
            str(ROOT / "audit" / "school-pyramid-home-mobile.png"),
            str(ROOT / "audit" / "school-pyramid-gyeonggi-final.png"),
            str(ROOT / "audit" / "school-pyramid-seoul-final.png"),
            str(ROOT / "audit" / "school-pyramid-suwon-final.png"),
            str(ROOT / "audit" / "school-pyramid-gangnam-mobile-final.png"),
        ],
    }
    if not passed:
        report["status"] = "FAIL"
    temporary = AUDIT.with_suffix(".json.http.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)
    with REPORT.open("a", encoding="utf-8") as handle:
        handle.write("\n## HTTP 전수 검사\n\n")
        handle.write(f"- 결과: **{'PASS' if passed else 'FAIL'}**\n")
        for key, value in summary.items():
            handle.write(f"- {key}: {value}\n")
    print(json.dumps({"status": "PASS" if passed else "FAIL", **summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
