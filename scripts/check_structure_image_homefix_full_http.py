from __future__ import annotations

import json
import re
import socket
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
AUDIT_JSON = ROOT / "audit" / "structure-image-homefix-full-audit.json"
AUDIT_MD = ROOT / "audit" / "structure-image-homefix-full-audit.md"
META = ROOT / "intermediate" / "normalized-pages.json"
IMG = re.compile(r'<img\b[^>]*src="([^"]+)"', re.I)


def available(start: int) -> int:
    for port in range(start, start + 100):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no available preview port")


def main() -> None:
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    if audit["status"] != "PASS":
        raise RuntimeError("full audit is not PASS")
    target = Path(audit["target"])
    metadata = json.loads(META.read_text(encoding="utf-8"))
    specs = [
        ("지역 일반", lambda x: not x.get("school_name") and x.get("page_type") == "과외"),
        ("지역 수학", lambda x: not x.get("school_name") and x.get("page_type") == "수학과외"),
        ("지역 영어", lambda x: not x.get("school_name") and x.get("page_type") == "영어과외"),
        ("학교 일반", lambda x: x.get("page_type") == "학교과외"),
        ("학교 수학", lambda x: x.get("page_type") == "학교수학과외"),
        ("학교 영어", lambda x: x.get("page_type") == "학교영어과외"),
    ]
    pages = []
    for category, predicate in specs:
        matches = sorted((x for x in metadata if predicate(x)), key=lambda x: str(x["slug"]))[:3]
        pages.extend({"category": category, "slug": str(x["slug"]), "path": f"/{x['slug']}/"} for x in matches)
    region_pages = [x for x in pages if x["category"].startswith("지역")][:5]
    school_pages = [x for x in pages if x["category"].startswith("학교")][:5]
    region_images = [
        IMG.search((target / x["slug"] / "index.html").read_text(encoding="utf-8")).group(1)
        for x in region_pages
    ]
    school_images = [
        IMG.search((target / x["slug"] / "index.html").read_text(encoding="utf-8")).group(1)
        for x in school_pages
    ]
    hero = IMG.search((target / "index.html").read_text(encoding="utf-8")).group(1)
    requests = [
        {"category": "홈", "path": "/"},
        *pages,
        {"category": "Hero 이미지", "path": urlsplit(hero).path},
        *({"category": "지역 이미지", "path": urlsplit(path).path} for path in region_images),
        *({"category": "학교 이미지", "path": urlsplit(path).path} for path in school_images),
        {"category": "CSS", "path": "/assets/css/structure-home-image-fix.css"},
        {"category": "favicon", "path": "/assets/favicon/favicon.ico"},
        {"category": "manifest", "path": "/site.webmanifest"},
    ]
    port = available(8080)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(target), **kwargs)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    results = []
    try:
        for item in requests:
            with urlopen(base + quote(item["path"], safe="/"), timeout=20) as response:
                body = response.read()
                results.append({
                    **item, "status": response.status,
                    "content_type": response.headers.get_content_type(), "bytes": len(body),
                })
    finally:
        server.shutdown()
        server.server_close()

    counts = {}
    for category, _ in specs:
        counts[category] = sum(x["status"] == 200 for x in results if x["category"] == category)
    summary = {
        "checked_requests": len(results), "http_200": sum(x["status"] == 200 for x in results),
        "home_200": sum(x["status"] == 200 for x in results if x["category"] == "홈"),
        **{category.replace(" ", "_") + "_200": value for category, value in counts.items()},
        "hero_image_200": sum(x["status"] == 200 for x in results if x["category"] == "Hero 이미지"),
        "region_images_200": sum(x["status"] == 200 for x in results if x["category"] == "지역 이미지"),
        "school_images_200": sum(x["status"] == 200 for x in results if x["category"] == "학교 이미지"),
        "css_200": sum(x["status"] == 200 for x in results if x["category"] == "CSS"),
        "favicon_200": sum(x["status"] == 200 for x in results if x["category"] == "favicon"),
        "manifest_200": sum(x["status"] == 200 for x in results if x["category"] == "manifest"),
    }
    passed = summary["http_200"] == len(results) and all(value == 3 for value in counts.values()) and (
        summary["hero_image_200"] == 1 and summary["region_images_200"] == 5
        and summary["school_images_200"] == 5 and summary["css_200"] == 1
        and summary["favicon_200"] == 1 and summary["manifest_200"] == 1
    )
    audit["http_preview"] = {
        "status": "PASS" if passed else "FAIL", "checked_at": datetime.now().astimezone().isoformat(),
        "base_url": base, "summary": summary, "results": results,
    }
    if not passed:
        audit["status"] = "FAIL"
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    with AUDIT_MD.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n## HTTP 대표 검증\n\n")
        handle.write(f"- 판정: **{'PASS' if passed else 'FAIL'}**\n")
        handle.write(f"- 검증 URL: `{base}`\n")
        for key, value in summary.items():
            handle.write(f"- {key}: {value}\n")
    print(json.dumps({"status": "PASS" if passed else "FAIL", "base_url": base, "summary": summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
