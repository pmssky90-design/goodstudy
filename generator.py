from __future__ import annotations

import json
import logging
import shutil
import socket
import struct
import subprocess
import sys
import zlib
from collections import Counter
from pathlib import Path

from config import AUDIT_DIR, CANDIDATE_OUTPUT_DIR, INTERMEDIATE_DIR, SOURCE_EXCEL
from sitegen.excel_loader import SourceError, load_sheets
from sitegen.hierarchy import build_relations
from sitegen.normalizer import normalize_pages
from sitegen.renderer import render_site
from sitegen.school_matcher import school_match_report
from sitegen.slug_registry import resolve_slugs
from sitegen.validator import ValidationError, audit_output, preflight


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def png(size: int) -> bytes:
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            book = size * .2 < x < size * .8 and size * .18 < y < size * .82
            center = abs(x - size / 2) < max(1, size * .035)
            color = (25, 118, 90, 255) if book else (243, 248, 246, 255)
            if center and book:
                color = (255, 255, 255, 255)
            rows.extend(color)
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")


def ensure_favicons() -> None:
    target = Path("assets/favicon")
    target.mkdir(parents=True, exist_ok=True)
    for size, name in ((16, "favicon-16x16.png"), (32, "favicon-32x32.png"), (180, "apple-touch-icon.png")):
        (target / name).write_bytes(png(size))
    data = png(32)
    ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(data), 22) + data
    (target / "favicon.ico").write_bytes(ico)


def free_port() -> int:
    for port in range(8000, 8010):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("8000~8009 포트가 모두 사용 중입니다.")


def run(start_server: bool = True) -> dict[str, object]:
    AUDIT_DIR.mkdir(exist_ok=True)
    INTERMEDIATE_DIR.mkdir(exist_ok=True)
    logging.basicConfig(filename=AUDIT_DIR / "build.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8", force=True)
    sheets, sheet_report = load_sheets(SOURCE_EXCEL)
    pages, title_stats = normalize_pages(sheets)
    registry, slug_stats, redirects = resolve_slugs(pages)
    relations = build_relations(pages)
    matches, fallback_stats = school_match_report(pages)
    for page in pages:
        page.canonical_url = f"https://goodstudy.co.kr/{page.slug}/"
    pre = preflight(pages)
    write_json(INTERMEDIATE_DIR / "source-sheet-report.json", {"sheets": sheet_report, "total_rows": sum(x["rows"] for x in sheet_report)})
    write_json(INTERMEDIATE_DIR / "normalized-pages.json", [p.to_dict() for p in pages])
    write_json(INTERMEDIATE_DIR / "relations.json", relations)
    write_json(INTERMEDIATE_DIR / "slug-registry.json", registry)
    write_json(INTERMEDIATE_DIR / "school-matches.json", matches)
    write_json(INTERMEDIATE_DIR / "redirects.json", redirects)
    write_json(INTERMEDIATE_DIR / "validation-report.json", pre)
    if not pre["passed"]:
        write_json(AUDIT_DIR / "preflight-errors.json", pre)
        raise ValidationError("사전 검증 실패: " + ", ".join(pre["errors"]))
    reuse_output = "--reuse-output" in sys.argv
    if not reuse_output:
        if CANDIDATE_OUTPUT_DIR.exists():
            shutil.rmtree(CANDIDATE_OUTPUT_DIR)
        ensure_favicons()
        render_site(pages)
    post = audit_output(pages)
    page_types = Counter(p.page_type for p in pages)
    report = {
        "source_excel": str(SOURCE_EXCEL), "sheet_count": len(sheet_report), "sheets": sheet_report,
        "total_source_rows": sum(x["rows"] for x in sheet_report), "normalized_nodes": len(pages),
        "generated_pages": len(pages) + 1, "region_pages": sum(not p.school_name for p in pages),
        "school_pages": sum(bool(p.school_name) for p in pages), "page_types": dict(sorted(page_types.items())),
        "slug_duplicates": slug_stats, **title_stats, **fallback_stats, "post_audit": post,
        "candidate_output": str(CANDIDATE_OUTPUT_DIR), "audit": str(AUDIT_DIR), "intermediate": str(INTERMEDIATE_DIR),
    }
    write_json(INTERMEDIATE_DIR / "build-report.json", report)
    write_json(AUDIT_DIR / "final-audit.json", post)
    fatal = ["duplicate_canonical", "empty_title", "empty_description", "site_name_in_title",
             "forbidden_nationwide_title", "broken_internal_links", "home_unreachable_pages",
             "duplicate_sitemap", "www_urls", "http_urls", "index_urls", "double_slash_paths"]
    failures = [key for key in fatal if post.get(key)]
    if failures:
        raise ValidationError("생성 후 검증 실패: " + ", ".join(failures))
    if start_server:
        port = free_port()
        process = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
                                    "--directory", str(CANDIDATE_OUTPUT_DIR)],
                                   stdout=(AUDIT_DIR / "preview-server.log").open("a", encoding="utf-8"),
                                   stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        report["preview_url"] = f"http://localhost:{port}/"
        report["preview_pid"] = process.pid
        write_json(INTERMEDIATE_DIR / "build-report.json", report)
    return report


if __name__ == "__main__":
    try:
        result = run("--no-server" not in sys.argv)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (SourceError, ValidationError, RuntimeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(1)
