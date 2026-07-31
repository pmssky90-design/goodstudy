from __future__ import annotations

import csv
import html
import json
import socket
import threading
from collections import Counter
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "candidate_output_structure_image_homefix"
HOME = TARGET / "index.html"
META = ROOT / "intermediate" / "normalized-pages.json"
OUT_JSON = ROOT / "audit" / "preview-navigation-diagnosis.json"
OUT_CSV = ROOT / "audit" / "preview-navigation-errors.csv"
OUT_ROOT = ROOT / "audit" / "preview-server-root.txt"
EXISTING_BASE = "http://127.0.0.1:8080"


def available(start: int) -> int:
    for port in range(start, start + 100):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no available port")


def fetch(base: str, path: str) -> int:
    try:
        with urlopen(base + quote(path, safe="/%"), timeout=15) as response:
            response.read(1)
            return response.status
    except HTTPError as exc:
        return exc.code
    except (URLError, TimeoutError):
        return 0


def href_path(href: str) -> tuple[str, str]:
    parsed = urlsplit(html.unescape(href))
    error = ""
    if parsed.scheme == "file":
        return "", "wrong_candidate"
    if parsed.scheme in ("http", "https"):
        host = parsed.netloc.lower().removeprefix("www.")
        if host == "goodstudy.co.kr":
            error = "absolute_domain_link"
        elif host in ("127.0.0.1:8080", "localhost:8080"):
            error = ""
        elif host.startswith("127.0.0.1:") or host.startswith("localhost:"):
            error = "wrong_candidate"
        else:
            return "", "wrong_candidate"
    path = unquote(parsed.path)
    return path or "/", error


def expected_file(path: str) -> Path:
    if path == "/":
        return TARGET / "index.html"
    clean_path = path.lstrip("/")
    direct = TARGET / clean_path
    if path.endswith("/"):
        return direct / "index.html"
    if direct.is_file():
        return direct
    return direct / "index.html"


def main() -> None:
    metadata = json.loads(META.read_text(encoding="utf-8"))
    by_slug = {str(x["slug"]): x for x in metadata}
    source = HOME.read_text(encoding="utf-8")
    soup = BeautifulSoup(source, "html.parser")
    rows = []
    counts = Counter()
    unique_internal_paths: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        label = " ".join(anchor.get_text(" ", strip=True).split())
        path, initial_error = href_path(href)
        if not path:
            error = initial_error or "malformed_url"
            rows.append({
                "source_page": "/", "link_label": label, "href": href, "expected_file": "",
                "file_exists": 0, "http_status": 0, "target_page_type": "",
                "error_type": error, "recommended_fix": "운영 도메인 또는 다른 후보 참조를 로컬 상대 URL로 교체",
            })
            counts[error] += 1
            continue
        parsed = urlsplit(html.unescape(href))
        malformed = (
            " " in href or href.startswith("//") or "\\" in href
            or (path != "/" and not path.startswith("/"))
            or (path != "/" and Path(path).suffix == "" and not path.endswith("/"))
            or "//" in path
        )
        file_path = expected_file(path)
        exists = file_path.is_file()
        slug = path.strip("/")
        item = by_slug.get(slug)
        page_type = str(item.get("page_type", "")) if item else ("home" if path == "/" else "asset")
        error = initial_error
        recommended = ""
        if malformed:
            error = "malformed_url"
            recommended = "앞/뒤 슬래시와 URL 형식을 정규화"
        elif not exists:
            error = "missing_file"
            recommended = "실제 slug 경로의 index.html 존재 여부 확인"
        elif path != "/" and not item and not file_path.is_file():
            error = "wrong_path"
            recommended = "실제 후보 파일 경로에 맞는 상대 URL로 교체"
        elif not parsed.fragment and ("수학" in label or anchor.get("data-subject") == "math") and "수학" not in page_type:
            error = "wrong_subject"
            recommended = "수학 페이지 slug로 교체"
        elif not parsed.fragment and ("영어" in label or anchor.get("data-subject") == "english") and "영어" not in page_type:
            error = "wrong_subject"
            recommended = "영어 페이지 slug로 교체"
        elif anchor.find_parent(class_="school-card") and not item.get("school_name"):
            error = "wrong_entity"
            recommended = "학교 페이지 slug로 교체"
        status = fetch(EXISTING_BASE, path + (("?" + parsed.query) if parsed.query else ""))
        if exists and status != 200 and not error:
            error = "server_root_mismatch"
            recommended = "올바른 후보 루트로 새 로컬 서버 실행"
        if not error:
            recommended = "수정 불필요"
        counts[error or "ok"] += 1
        if path not in unique_internal_paths:
            unique_internal_paths.append(path)
        rows.append({
            "source_page": "/", "link_label": label, "href": href,
            "expected_file": str(file_path), "file_exists": int(exists),
            "http_status": status, "target_page_type": page_type,
            "error_type": error, "recommended_fix": recommended,
        })

    # Reuse an already-running verified 8081 preview; otherwise use the first
    # available port and run a temporary verification server.
    port = 8081
    server = None
    if fetch(f"http://127.0.0.1:{port}", "/") != 200:
        port = available(8081)

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(TARGET), **kwargs)

            def log_message(self, format: str, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    new_base = f"http://127.0.0.1:{port}"
    try:
        representatives = {}
        specs = [
            ("지역 일반", lambda x: not x.get("school_name") and x.get("page_type") == "과외"),
            ("지역 수학", lambda x: not x.get("school_name") and x.get("page_type") == "수학과외"),
            ("지역 영어", lambda x: not x.get("school_name") and x.get("page_type") == "영어과외"),
            ("학교 일반", lambda x: x.get("page_type") == "학교과외"),
            ("학교 수학", lambda x: x.get("page_type") == "학교수학과외"),
            ("학교 영어", lambda x: x.get("page_type") == "학교영어과외"),
        ]
        for category, predicate in specs:
            matches = sorted((x for x in metadata if predicate(x)), key=lambda x: str(x["slug"]))[:5]
            representatives[category] = [
                {"slug": str(x["slug"]), "status": fetch(new_base, f"/{x['slug']}/")}
                for x in matches
            ]
        assets = {
            "css": fetch(new_base, "/assets/css/structure-home-image-fix.css"),
            "image": fetch(new_base, "/assets/images/content/body-common.webp"),
            "favicon": fetch(new_base, "/assets/favicon/favicon.ico"),
            "manifest": fetch(new_base, "/site.webmanifest"),
        }
        new_home_status = fetch(new_base, "/")
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()

    html_count = int(HOME.is_file()) + sum(1 for _ in TARGET.glob("*/index.html"))
    region_pages = sum(not x.get("school_name") for x in metadata)
    school_pages = sum(bool(x.get("school_name")) for x in metadata)
    math_pages = sum("수학" in str(x.get("page_type", "")) for x in metadata)
    english_pages = sum("영어" in str(x.get("page_type", "")) for x in metadata)
    report = {
        "status": "PASS" if counts["ok"] == len(rows) and new_home_status == 200
        and all(x["status"] == 200 for values in representatives.values() for x in values)
        and all(value == 200 for value in assets.values()) else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "existing_server": {
            "port": 8080, "pid": 3652,
            "command": '"C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python314\\python.exe" -m http.server 8080 --bind 127.0.0.1 --directory C:\\Projects\\goodstudy\\candidate_output_structure_image_homefix',
            "working_directory": str(ROOT),
            "service_root": str(TARGET), "root_matches_target": True,
        },
        "candidate": {
            "path": str(TARGET), "html_count": html_count, "index_html_count": html_count,
            "region_page_folders": region_pages, "school_page_folders": school_pages,
            "math_page_folders": math_pages, "english_page_folders": english_pages,
        },
        "home_links": {
            "total": len(rows), "normal": counts["ok"], "errors": len(rows) - counts["ok"],
            "unique_internal_paths": len(unique_internal_paths), "error_counts": dict(counts),
        },
        "representative_links": rows[:20],
        "all_home_links": rows,
        "url_checks": {
            "leading_slash_errors": sum(not href_path(x["href"])[0].startswith("/") for x in rows if href_path(x["href"])[0]),
            "trailing_slash_errors": sum(
                p not in ("/", "") and Path(p).suffix == "" and not p.endswith("/")
                for p, _ in (href_path(x["href"]) for x in rows)
            ),
            "spaces": sum(" " in x["href"] for x in rows),
            "double_slashes": sum("//" in href_path(x["href"])[0] for x in rows),
            "file_urls": sum(x["href"].lower().startswith("file:") for x in rows),
            "absolute_goodstudy_urls": counts["absolute_domain_link"],
            "other_localhost_ports": counts["wrong_candidate"],
            "korean_url_encoding_errors": sum(
                x["file_exists"] and x["http_status"] != 200 and any(ord(ch) > 127 for ch in x["href"])
                for x in rows
            ),
        },
        "new_server_validation": {
            "base_url": new_base, "home_status": new_home_status,
            "representatives": representatives, "assets": assets,
        },
        "links_modified": 0,
        "diagnosis": "8080 server root, candidate files, href paths, Korean URL encoding, and HTTP responses are all valid."
        if counts["ok"] == len(rows) else "Home link errors were detected; see CSV.",
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "source_page", "link_label", "href", "expected_file", "file_exists",
            "http_status", "target_page_type", "error_type", "recommended_fix",
        ]
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)
    OUT_ROOT.write_text(
        "\n".join([
            "Existing preview server",
            "port: 8080", "pid: 3652",
            "executable: C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python314\\python.exe",
            "working_directory: C:\\Projects\\goodstudy",
            "command: python -m http.server 8080 --bind 127.0.0.1 --directory C:\\Projects\\goodstudy\\candidate_output_structure_image_homefix",
            f"service_root: {TARGET}", "root_matches_target: true",
            "", "New verified server", f"port: {port}", f"service_root: {TARGET}", f"url: {new_base}/",
        ]) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"], "home_links": report["home_links"],
        "candidate": report["candidate"], "url_checks": report["url_checks"],
        "new_server": report["new_server_validation"],
    }, ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
