from __future__ import annotations

import hashlib
import json
import socket
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "candidate_output_structureclean"
META = ROOT / "intermediate" / "normalized-pages.json"
AUDIT_JSON = ROOT / "audit" / "structure-full-audit.json"
AUDIT_MD = ROOT / "audit" / "structure-full-audit.md"


def available_port(start: int = 8040) -> int:
    for port in range(start, start + 100):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available preview port from 8040 through 8139")


def select_samples(metadata: list[dict[str, object]]) -> list[dict[str, str]]:
    specifications = [
        ("시도", 1, lambda x: x.get("geo_level") == "province" and x.get("page_type") == "과외"),
        ("시군구", 2, lambda x: x.get("geo_level") == "district" and x.get("page_type") == "과외"),
        ("읍면동", 2, lambda x: x.get("geo_level") == "locality" and x.get("page_type") == "과외"),
        ("지역 수학", 2, lambda x: not x.get("school_name") and x.get("page_type") == "수학과외"),
        ("지역 영어", 2, lambda x: not x.get("school_name") and x.get("page_type") == "영어과외"),
        ("학교 일반", 2, lambda x: x.get("page_type") == "학교과외"),
        ("학교 수학", 2, lambda x: x.get("page_type") == "학교수학과외"),
        ("학교 영어", 2, lambda x: x.get("page_type") == "학교영어과외"),
    ]
    selected = [{"category": "홈", "slug": "", "path": "/"}]
    for category, count, predicate in specifications:
        matches = sorted(
            (x for x in metadata if predicate(x)),
            key=lambda x: str(x["slug"]),
        )[:count]
        if len(matches) != count:
            raise RuntimeError(f"Insufficient samples for {category}: {len(matches)}")
        selected.extend(
            {"category": category, "slug": str(item["slug"]), "path": f"/{item['slug']}/"}
            for item in matches
        )
    return selected


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    metadata = json.loads(META.read_text(encoding="utf-8"))
    samples = select_samples(metadata)
    port = available_port()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(TARGET), **kwargs)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    results: list[dict[str, object]] = []
    try:
        for sample in samples:
            url = base_url + quote(sample["path"], safe="/")
            with urlopen(url, timeout=20) as response:
                body = response.read().decode("utf-8")
                results.append({
                    **sample,
                    "url": url,
                    "status": response.status,
                    "content_type": response.headers.get_content_type(),
                    "structure_css_linked": "/assets/css/structure-preview.css" in body,
                })
        css_url = base_url + "/assets/css/structure-preview.css"
        with urlopen(css_url, timeout=20) as response:
            css_body = response.read()
            css_check = {
                "url": css_url,
                "status": response.status,
                "content_type": response.headers.get_content_type(),
                "bytes": len(css_body),
                "matches_approved_css": hashlib.sha256(css_body).hexdigest()
                == sha256(ROOT / "assets" / "css" / "structure-preview.css"),
            }
    finally:
        server.shutdown()
        server.server_close()

    preservation = {}
    for name in ("robots.txt", "sitemap.xml", "site.webmanifest", "assets/favicon/favicon.ico"):
        source = ROOT / "candidate_output_descriptionclean" / name
        target = TARGET / name
        preservation[name] = {
            "source_exists": source.exists(),
            "target_exists": target.exists(),
            "byte_identical": source.exists() and target.exists() and sha256(source) == sha256(target),
        }
    passed = (
        len(results) == 16
        and all(row["status"] == 200 and row["structure_css_linked"] for row in results)
        and css_check["status"] == 200
        and css_check["content_type"] == "text/css"
        and css_check["matches_approved_css"]
        and all(value["byte_identical"] for value in preservation.values())
    )
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    audit["http_preview"] = {
        "status": "PASS" if passed else "FAIL",
        "checked_at": datetime.now().astimezone().isoformat(),
        "base_url": base_url,
        "representative_pages": results,
        "css": css_check,
        "preservation": preservation,
    }
    required_zero = (
        "read_errors", "zero_byte", "h1_errors", "duplicate_h1_h2", "empty_sections",
        "duplicate_card_hrefs", "broken_links", "orphan_pages", "home_unreachable_pages",
        "css_missing", "favicon_errors", "manifest_errors", "title_changed",
        "description_changed", "slug_changes", "canonical_changed", "sitemap_changes",
        "jsonld_changed", "internal_link_targets_changed", "school_connection_changes",
        "page_count_change", "body_content_text_changed",
    )
    full_audit_passed = all(audit["summary"].get(key, 0) == 0 for key in required_zero)
    audit["status"] = "PASS" if passed and full_audit_passed else "FAIL"
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    with AUDIT_MD.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n## HTTP 대표 페이지 확인\n\n")
        handle.write(f"- 판정: **{'PASS' if passed else 'FAIL'}**\n")
        handle.write(f"- 미리보기: `{base_url}`\n")
        handle.write(f"- 대표 HTML 200 및 CSS 연결: {sum(r['status'] == 200 and r['structure_css_linked'] for r in results)}/16\n")
        handle.write(f"- CSS 200, text/css, 승인 파일 일치: {css_check['status'] == 200 and css_check['content_type'] == 'text/css' and css_check['matches_approved_css']}\n")
        handle.write(f"- robots.txt 원본 동일: {preservation['robots.txt']['byte_identical']}\n")
    print(json.dumps({
        "status": "PASS" if passed else "FAIL",
        "base_url": base_url,
        "representative_pages": len(results),
        "http_200_css_linked": sum(r["status"] == 200 and r["structure_css_linked"] for r in results),
        "css": css_check,
        "samples": samples,
    }, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
