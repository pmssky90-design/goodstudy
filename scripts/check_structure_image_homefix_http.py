from __future__ import annotations

import json
import socket
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "candidate_output_structure_image_homefix_preview"
AUDIT_JSON = ROOT / "audit" / "structure-image-homefix-preview-audit.json"
ANALYSIS_MD = ROOT / "audit" / "structure-image-homefix-analysis.md"


def port_from(start: int) -> int:
    for port in range(start, start + 100):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no available port")


def main() -> None:
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    region = [x for x in audit["selected_pages"] if not x["school_name"]][:5]
    school = [x for x in audit["selected_pages"] if x["school_name"]][:5]
    images = [
        "/assets/images/content/body-common.webp",
        *[f"/assets/images/search/thumb{index:02}.png" for index in range(1, 10)],
    ]
    paths = [
        "/", "/assets/css/structure-home-image-fix.css",
        *[f"/{x['slug']}/" for x in region],
        *[f"/{x['slug']}/" for x in school],
        *images, "/assets/favicon/favicon.ico", "/site.webmanifest",
    ]
    port = port_from(8070)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(TARGET), **kwargs)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    results = []
    try:
        for path in paths:
            with urlopen(base + quote(path, safe="/"), timeout=20) as response:
                body = response.read()
                results.append({
                    "path": path, "status": response.status,
                    "content_type": response.headers.get_content_type(), "bytes": len(body),
                })
    finally:
        server.shutdown()
        server.server_close()

    by_path = {x["path"]: x for x in results}
    summary = {
        "checked_requests": len(results),
        "http_200": sum(x["status"] == 200 for x in results),
        "home_200": int(by_path["/"]["status"] == 200),
        "css_200": int(by_path["/assets/css/structure-home-image-fix.css"]["status"] == 200),
        "region_pages_200": sum(by_path[f"/{x['slug']}/"]["status"] == 200 for x in region),
        "school_pages_200": sum(by_path[f"/{x['slug']}/"]["status"] == 200 for x in school),
        "image_samples_200": sum(by_path[x]["status"] == 200 for x in images),
        "favicon_200": int(by_path["/assets/favicon/favicon.ico"]["status"] == 200),
        "manifest_200": int(by_path["/site.webmanifest"]["status"] == 200),
    }
    passed = (
        summary["http_200"] == len(results)
        and summary["region_pages_200"] == 5
        and summary["school_pages_200"] == 5
        and summary["image_samples_200"] == 10
    )
    audit["http_preview"] = {
        "status": "PASS" if passed else "FAIL",
        "checked_at": datetime.now().astimezone().isoformat(),
        "base_url": base,
        "summary": summary,
        "results": results,
    }
    if not passed:
        audit["status"] = "FAIL"
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    with ANALYSIS_MD.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n## HTTP 검증\n\n")
        handle.write(f"- 판정: **{'PASS' if passed else 'FAIL'}**\n")
        handle.write(f"- 검증 URL: `{base}`\n")
        for key, value in summary.items():
            handle.write(f"- {key}: {value}\n")
    print(json.dumps({"status": "PASS" if passed else "FAIL", "base_url": base, "summary": summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
