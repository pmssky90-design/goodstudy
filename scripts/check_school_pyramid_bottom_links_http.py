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
BASE = "http://127.0.0.1:8122"
MOVED_CSV = ROOT / "audit" / "school-pyramid-bottom-links-check.csv"
CHAIN_CSV = ROOT / "audit" / "school-pyramid-link-check.csv"
AUDIT = ROOT / "audit" / "school-pyramid-bottom-links-audit.json"
REPORT = ROOT / "audit" / "school-pyramid-bottom-links-report.md"


def check(href: str) -> tuple[str, int]:
    path = urlsplit(href).path or "/"
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


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    moved_rows = read_rows(MOVED_CSV)
    chain_rows = read_rows(CHAIN_CSV)
    hrefs = sorted(
        {row["href"] for row in moved_rows if row["href"]}
        | {row["href"] for row in chain_rows if row["href"]}
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = dict(pool.map(check, hrefs, chunksize=16))

    for row in moved_rows:
        status = statuses.get(row["href"], 0)
        row["http_status"] = str(status)
        row["error_type"] = "" if status == 200 else "http_error"
    with MOVED_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=moved_rows[0].keys())
        writer.writeheader()
        writer.writerows(moved_rows)

    with urlopen(BASE + "/", timeout=30) as response:
        home_status = response.status
        source = response.read().decode("utf-8")
    soup = BeautifulSoup(source, "html.parser")
    assets = [
        *(str(x["href"]) for x in soup.select('link[rel="stylesheet"][href]')),
        *(str(x["href"]) for x in soup.select('link[rel~="icon"][href]')),
        *(str(x["href"]) for x in soup.select('link[rel="manifest"][href]')),
        *(str(x["src"]) for x in soup.select(".home-hero img[src]")),
    ]
    asset_statuses = dict(check(href) for href in dict.fromkeys(assets))
    moved_hrefs = {row["href"] for row in moved_rows if row["href"]}
    chain_hrefs = {row["href"] for row in chain_rows if row["href"]}
    summary = {
        "base_url": BASE + "/",
        "home_status": home_status,
        "moved_link_rows": len(moved_rows),
        "unique_moved_urls": len(moved_hrefs),
        "moved_link_http_errors": sum(statuses[href] != 200 for href in moved_hrefs),
        "chain_link_rows": len(chain_rows),
        "unique_chain_urls": len(chain_hrefs),
        "chain_link_http_errors": sum(statuses[href] != 200 for href in chain_hrefs),
        "all_unique_urls_checked": len(hrefs),
        "all_url_http_errors": sum(value != 200 for value in statuses.values()),
        "asset_count": len(asset_statuses),
        "asset_http_errors": sum(value != 200 for value in asset_statuses.values()),
    }
    passed = (
        home_status == 200
        and len(moved_rows) == 472
        and len(chain_rows) == 1491
        and all(value == 200 for value in statuses.values())
        and all(value == 200 for value in asset_statuses.values())
    )
    report = json.loads(AUDIT.read_text(encoding="utf-8"))
    report["http_preview"] = {
        "status": "PASS" if passed else "FAIL",
        "summary": summary,
        "link_errors": {key: value for key, value in statuses.items() if value != 200},
        "asset_results": asset_statuses,
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
