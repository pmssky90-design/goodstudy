from __future__ import annotations

import json
import re
import socket
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "candidate_output_navigation_linkfix"
AUDIT = ROOT / "audit" / "navigation-linkfix-audit.json"
CHECKPOINT = ROOT / "intermediate" / "navigation-linkfix-build-checkpoint.json"


def available(start: int) -> int:
    for port in range(start, start + 100):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no available port")


def main() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if audit["status"] != "PASS":
        raise RuntimeError("navigation audit is not PASS")
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    pilot = {x["slug"]: x["children"] for x in checkpoint["pilot_pages"]}
    required_slugs = [
        "구로구구로구영어과외", "구로구구로구수학과외",
        "대전광역시영어과외", "대전광역시수학과외",
    ]
    page_paths = ["/", *[f"/{slug}/" for slug in required_slugs]]
    english_children = next(children for slug, children in pilot.items() if slug == "구로구구로구영어과외")
    english_children += next(children for slug, children in pilot.items() if slug == "대전광역시영어과외")
    math_children = next(children for slug, children in pilot.items() if slug == "구로구구로구수학과외")
    math_children += next(children for slug, children in pilot.items() if slug == "대전광역시수학과외")
    english_paths = [f"/{slug}/" for slug in english_children[:10]]
    math_paths = [f"/{slug}/" for slug in math_children[:10]]
    asset_paths = [
        "/assets/css/structure-home-image-fix.css",
        "/assets/images/content/body-common.webp",
        "/assets/favicon/favicon.ico", "/site.webmanifest",
    ]
    port = available(8090)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(TARGET), **kwargs)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    results = []
    try:
        for category, paths in (
            ("page", page_paths), ("english_child", english_paths),
            ("math_child", math_paths), ("asset", asset_paths),
        ):
            for path in paths:
                with urlopen(base + quote(path, safe="/"), timeout=20) as response:
                    results.append({"category": category, "path": path, "status": response.status})
        with urlopen(base + "/", timeout=20) as response:
            home = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
    soup = BeautifulSoup(home, "html.parser")
    school_links = soup.select(".region-school-links a[href]")
    school_links_valid = sum(
        str(link["href"]).startswith("#") and soup.find(id=str(link["href"])[1:]) is not None
        for link in school_links
    )
    summary = {
        "home_200": next(x["status"] for x in results if x["path"] == "/"),
        "representative_pages_200": sum(x["status"] == 200 for x in results if x["category"] == "page") - 1,
        "english_children_200": sum(x["status"] == 200 for x in results if x["category"] == "english_child"),
        "math_children_200": sum(x["status"] == 200 for x in results if x["category"] == "math_child"),
        "home_school_links": len(school_links), "home_school_links_valid": school_links_valid,
        "assets_200": sum(x["status"] == 200 for x in results if x["category"] == "asset"),
    }
    passed = (
        all(x["status"] == 200 for x in results)
        and summary["representative_pages_200"] == 4
        and summary["english_children_200"] == 10 and summary["math_children_200"] == 10
        and summary["home_school_links"] == summary["home_school_links_valid"] == 17
        and summary["assets_200"] == 4
    )
    audit["http_preview"] = {
        "status": "PASS" if passed else "FAIL", "checked_at": datetime.now().astimezone().isoformat(),
        "base_url": base, "summary": summary, "results": results,
    }
    if not passed:
        audit["status"] = "FAIL"
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS" if passed else "FAIL", "base_url": base, "summary": summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
