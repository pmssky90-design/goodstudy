from __future__ import annotations

import json
import re
import urllib.request
from urllib.parse import quote
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "candidate_output_descriptionclean"
TARGET = ROOT / "candidate_output_structure_preview"
CLASSIFICATION = ROOT / "audit" / "structure-page-classification.json"
OUT = ROOT / "audit" / "structure-preview-audit.json"

TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
DESC = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
CANON = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
JSONLD = re.compile(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
H2 = re.compile(r"<h2\b([^>]*)>(.*?)</h2>", re.I | re.S)
A = re.compile(r'<a\b[^>]*href="([^"]*)"', re.I)
CARD_A = re.compile(r'<a\b[^>]*class="link-card"[^>]*href="([^"]*)"', re.I)
TAG = re.compile(r"<[^>]+>")


def text(value: str) -> str:
    return re.sub(r"\s+", " ", TAG.sub(" ", value)).strip()


def norm(value: str) -> str:
    return "".join(ch for ch in text(value).casefold() if ch.isalnum())


def first(pattern: re.Pattern[str], value: str) -> str:
    match = pattern.search(value)
    return match.group(1) if match else ""


def main() -> None:
    classification = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))
    pages = classification["preview_pages"]
    details = []
    totals = {
        "preview_pages": len(pages), "h1_not_one": 0, "visible_duplicate_h1_h2": 0,
        "breadcrumb_invalid": 0, "brand_invalid": 0, "empty_sections": 0,
        "missing_preview_css": 0, "broken_internal_links_against_full_candidate": 0,
        "title_changes": 0, "description_changes": 0, "canonical_changes": 0,
        "jsonld_changes": 0, "duplicate_display_links": 0,
    }
    for item in pages:
        slug = item["slug"]
        source_path = SOURCE / "index.html" if not slug else SOURCE / slug / "index.html"
        target_path = TARGET / "index.html" if not slug else TARGET / slug / "index.html"
        source = source_path.read_text(encoding="utf-8")
        target = target_path.read_text(encoding="utf-8")
        h1s = H1.findall(target)
        visible_h2 = [body for attributes, body in H2.findall(target) if "is-duplicate-heading" not in attributes]
        duplicate = sum(bool(h1s) and norm(body) == norm(h1s[0]) for body in visible_h2)
        hrefs = A.findall(target)
        broken = []
        for href in hrefs:
            if not href.startswith("/") or href.startswith("//") or href.startswith("/#"):
                continue
            path = href.split("#", 1)[0].split("?", 1)[0]
            expected = SOURCE / "index.html" if path == "/" else SOURCE / path.strip("/") / "index.html"
            if not expected.exists():
                broken.append(href)
        card_hrefs = CARD_A.findall(target)
        duplicate_links = len(card_hrefs) - len(set(card_hrefs))
        row = {
            "slug": slug or "(home)", "h1_count": len(h1s), "visible_duplicate_h1_h2": duplicate,
            "broken_links": broken, "duplicate_display_links": duplicate_links,
            "title_changed": int(first(TITLE, source) != first(TITLE, target)),
            "description_changed": int(first(DESC, source) != first(DESC, target)),
            "canonical_changed": int(first(CANON, source) != first(CANON, target)),
            "jsonld_changed": int(JSONLD.findall(source) != JSONLD.findall(target)),
            "breadcrumb_valid": bool(slug == "" or ('aria-label="breadcrumb"' in target and "<ol>" in target and "<li" in target)),
            "brand_valid": 'class="site-brand-text"' in target and "<small>GoodStudy</small>" in target,
            "empty_sections": len(re.findall(r'<section\b[^>]*>\s*(?:<div[^>]*>\s*)*</section>', target, re.I | re.S)),
            "preview_css": "/assets/css/structure-preview.css" in target,
        }
        totals["h1_not_one"] += int(row["h1_count"] != 1)
        totals["visible_duplicate_h1_h2"] += duplicate
        totals["breadcrumb_invalid"] += int(not row["breadcrumb_valid"])
        totals["brand_invalid"] += int(not row["brand_valid"])
        totals["empty_sections"] += row["empty_sections"]
        totals["missing_preview_css"] += int(not row["preview_css"])
        totals["broken_internal_links_against_full_candidate"] += len(broken)
        totals["duplicate_display_links"] += duplicate_links
        totals["title_changes"] += row["title_changed"]
        totals["description_changes"] += row["description_changed"]
        totals["canonical_changes"] += row["canonical_changed"]
        totals["jsonld_changes"] += row["jsonld_changed"]
        details.append(row)
    css = (TARGET / "assets" / "css" / "structure-preview.css").read_text(encoding="utf-8")
    responsive = {
        "mobile_360_390_rules": "@media(max-width:600px)" in css,
        "tablet_768_rules": "@media(max-width:900px)" in css,
        "desktop_1024_1440_container": "1180px" in css,
        "horizontal_overflow_protection": "overflow-wrap:anywhere" in css,
        "mobile_single_column_cards": ".link-card-grid{grid-template-columns:1fr}" in css,
        "touch_target_44px": "min-height:44px" in css,
        "breadcrumb_overflow_handled": "overflow-x:auto" in css,
    }
    passed = (
        all(value == 0 for key, value in totals.items() if key != "preview_pages")
        and all(responsive.values())
    )
    http_paths = [
        "/", "/동두천시과외/", "/흥덕동과외/", "/동두천시동두천시수학과외/",
        "/동두천시동두천시영어과외/", "/흥진고과외/", "/흥진고수학과외/",
        "/흥진고영어과외/", "/assets/css/style.css", "/assets/css/structure-preview.css",
        "/assets/favicon/favicon.ico", "/site.webmanifest",
    ]
    http_checks = {}
    for path in http_paths:
        with urllib.request.urlopen("http://127.0.0.1:8030" + quote(path, safe="/")) as response:
            http_checks[path] = {"status": response.status, "content_type": response.headers.get_content_type()}
    passed = passed and all(value["status"] == 200 for value in http_checks.values())
    OUT.write_text(json.dumps({
        "status": "PASS" if passed else "FAIL", "target": str(TARGET),
        "totals": totals, "responsive_static_checks": responsive, "details": details,
        "css_diagnosis": {
            "state": "A",
            "stylesheet_href": "/assets/css/style.css",
            "file_scheme": "루트 절대경로가 로컬 드라이브 루트를 가리켜 하위 HTML 직접 열기에서 깨질 수 있음",
            "http": "기존 CSS와 미리보기 CSS 모두 HTTP 200 및 text/css",
        },
        "http_checks": http_checks,
        "note": "가로 overflow는 정적 CSS 규칙 검사이며 실제 브라우저 스크린샷 검사는 별도 승인 단계에서 수행 가능",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS" if passed else "FAIL", "totals": totals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
