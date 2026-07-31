from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit"
BASE_URL = "http://127.0.0.1:8053"


def local_url(path: str) -> str:
    return BASE_URL + quote(path if path.startswith("/") else "/" + path, safe="/%")


def main() -> None:
    required = [
        "/",
        "/구로구과외/",
        "/개봉동과외/",
        "/구로구초등과외/",
        "/구로구구로구영어과외/",
        "/경기도수학과외/",
        "/경기도중등수학과외/",
        "/경기도고등수학과외/",
        "/부천시부천시수학과외/",
        "/파주시파주시수학과외/",
        "/assets/images/content/body-common.webp",
        "/assets/css/navigation-ui-preview.css",
        "/sitemap.xml",
        "/robots.txt",
    ]
    search_dir = ROOT / "candidate_output_navigation_ui_preview_2" / "assets" / "images" / "search"
    required.extend(f"/assets/images/search/{path.name}" for path in sorted(search_dir.glob("*"))[:12])

    with (AUDIT / "navigation-ui-page-list.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    sampled = [row["page_url"] for row in rows if row.get("status") == "PASS"][:125]

    paths: list[str] = []
    for path in [*required, *sampled]:
        path = "/" + path.split("goodstudy.co.kr/", 1)[-1].lstrip("/") if "goodstudy.co.kr/" in path else path
        if path not in paths:
            paths.append(path)

    results = []
    for path in paths:
        url = local_url(path)
        status = 0
        error = ""
        try:
            with urlopen(url, timeout=15) as response:
                status = response.status
        except HTTPError as exc:
            status = exc.code
            error = str(exc)
        except URLError as exc:
            error = str(exc)
        results.append({"path": path, "url": url, "status": status, "error": error})

    report = {
        "checked_at": datetime.now().astimezone().isoformat(),
        "base_url": BASE_URL,
        "checked": len(results),
        "http_200": sum(row["status"] == 200 for row in results),
        "failed": sum(row["status"] != 200 for row in results),
        "status": "PASS" if all(row["status"] == 200 for row in results) and len(results) >= 100 else "FAIL",
        "results": results,
    }
    (AUDIT / "navigation-ui-http-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in ("status", "checked", "http_200", "failed")}, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
