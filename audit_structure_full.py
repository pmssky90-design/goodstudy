from __future__ import annotations

import csv
import html
import json
import os
import re
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from build_structure_preview import classify

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "candidate_output_descriptionclean"
TARGET = ROOT / "candidate_output_structureclean"
META = ROOT / "intermediate" / "normalized-pages.json"
OUT_JSON = ROOT / "audit" / "structure-full-audit.json"
OUT_MD = ROOT / "audit" / "structure-full-audit.md"
LAYOUT = ROOT / "audit" / "structure-layout-report.md"
DUP_CSV = ROOT / "audit" / "structure-link-duplicates.csv"
ERROR_CSV = ROOT / "audit" / "structure-errors.csv"
CURRENT = ROOT / "audit" / "current-candidate.json"

TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
DESC = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
CANON = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
JSONLD = re.compile(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
H2 = re.compile(r"<h2\b([^>]*)>(.*?)</h2>", re.I | re.S)
A = re.compile(r'<a\b[^>]*href="([^"]*)"', re.I)
CARD_A = re.compile(r'<a\b[^>]*class="link-card"[^>]*href="([^"]*)"', re.I)
CONTENT = re.compile(r'<div class="content">(.*?)</div>\s*</article>', re.I | re.S)
SECTION = re.compile(r"<section\b[^>]*>(.*?)</section>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", value))).strip()


def first(pattern: re.Pattern[str], value: str) -> str:
    match = pattern.search(value)
    return html.unescape(match.group(1)) if match else ""


def internal(href: str) -> str | None:
    parsed = urlsplit(html.unescape(href))
    if parsed.scheme or parsed.netloc:
        if parsed.netloc.lower().removeprefix("www.") != "goodstudy.co.kr":
            return None
    path = unquote(parsed.path)
    if not path.startswith("/") or path.startswith("//"):
        return None
    return path if path.endswith("/") else path + "/"


def inspect(pair: tuple[Path, Path]) -> dict[str, object]:
    source_path, target_path = pair
    rel = source_path.relative_to(SOURCE).as_posix()
    try:
        source = source_path.read_text(encoding="utf-8")
        target = target_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"relative_path": rel, "read_error": repr(exc)}
    source_links = {x for x in (internal(href) for href in A.findall(source)) if x is not None}
    target_links = {x for x in (internal(href) for href in A.findall(target)) if x is not None}
    cards = CARD_A.findall(target)
    h1s = H1.findall(target)
    visible_h2 = [body for attributes, body in H2.findall(target) if "is-duplicate-heading" not in attributes]
    duplicate_h1_h2 = sum(bool(h1s) and clean(body) == clean(h1s[0]) for body in visible_h2)
    empty_sections = sum(not clean(block) for block in SECTION.findall(target))
    source_content = CONTENT.search(source)
    target_content = CONTENT.search(target)
    return {
        "relative_path": rel, "read_error": "", "zero_byte": int(target_path.stat().st_size == 0),
        "h1_count": len(h1s), "duplicate_h1_h2": duplicate_h1_h2,
        "empty_sections": empty_sections, "duplicate_card_hrefs": len(cards) - len(set(cards)),
        "duplicate_card_values": [href for href, count in Counter(cards).items() if count > 1],
        "css_missing": int("/assets/css/structure-preview.css" not in target),
        "title_changed": int(first(TITLE, source) != first(TITLE, target)),
        "description_changed": int(first(DESC, source) != first(DESC, target)),
        "canonical_changed": int(first(CANON, source) != first(CANON, target)),
        "jsonld_changed": int(JSONLD.findall(source) != JSONLD.findall(target)),
        "internal_link_targets_changed": int(source_links != target_links),
        "source_only_links": sorted(source_links - target_links),
        "target_only_links": sorted(target_links - source_links),
        "body_content_text_changed": int(
            clean(source_content.group(1) if source_content else "")
            != clean(target_content.group(1) if target_content else "")
        ),
        "target_links": sorted(target_links),
    }


def atomic_text(path: Path, value: str, encoding: str = "utf-8") -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding=encoding, newline="\n") as handle:
        handle.write(value); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def main() -> None:
    source_paths = [SOURCE / "index.html"] + sorted(SOURCE.glob("*/index.html"), key=lambda p: p.relative_to(SOURCE).as_posix())
    target_paths = [TARGET / path.relative_to(SOURCE) for path in source_paths]
    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, zip(source_paths, target_paths), chunksize=32))
    counts = Counter()
    errors: list[dict[str, str]] = []
    duplicates: list[dict[str, str]] = []
    adjacency: dict[str, set[str]] = {}
    all_paths = {"/" if p.name == "index.html" and p.parent == TARGET else "/" + p.parent.name + "/" for p in target_paths}
    for row in rows:
        rel = str(row["relative_path"])
        current = "/" if rel == "index.html" else "/" + Path(rel).parent.name + "/"
        if row.get("read_error"):
            counts["read_errors"] += 1
            errors.append({"relative_path": rel, "code": "read_error", "detail": str(row["read_error"])})
            continue
        for key in (
            "zero_byte", "duplicate_h1_h2", "empty_sections", "duplicate_card_hrefs", "css_missing",
            "title_changed", "description_changed", "canonical_changed", "jsonld_changed",
            "internal_link_targets_changed", "body_content_text_changed",
        ):
            counts[key] += int(row[key])
        counts["h1_errors"] += int(row["h1_count"] != 1)
        adjacency[current] = set(row["target_links"])
        for key in (
            "zero_byte", "duplicate_h1_h2", "empty_sections", "css_missing", "title_changed",
            "description_changed", "canonical_changed", "jsonld_changed",
            "internal_link_targets_changed", "body_content_text_changed",
        ):
            if row[key]:
                errors.append({"relative_path": rel, "code": key, "detail": ""})
        if row["h1_count"] != 1:
            errors.append({"relative_path": rel, "code": "h1_count", "detail": str(row["h1_count"])})
        for href in row["duplicate_card_values"]:
            duplicates.append({"relative_path": rel, "href": href})
    broken: list[tuple[str, str]] = []
    for source_url, targets in adjacency.items():
        for target_url in targets:
            if target_url not in all_paths:
                broken.append((source_url, target_url))
    incoming = Counter(target for targets in adjacency.values() for target in targets if target in all_paths)
    orphans = sorted(path for path in all_paths if path != "/" and incoming[path] == 0)
    reachable, queue = {"/"}, deque(["/"])
    while queue:
        for target_url in adjacency.get(queue.popleft(), set()):
            if target_url in adjacency and target_url not in reachable:
                reachable.add(target_url); queue.append(target_url)
    unreachable = sorted(all_paths - reachable)
    metadata = json.loads(META.read_text(encoding="utf-8"))
    classes = Counter()
    for item in metadata:
        value = classify(item)
        classes[f"entity:{value['entity_type']}"] += 1
        classes[f"subject:{value['subject_type']}"] += 1
        classes[f"grade:{value['grade_type']}"] += 1
    source_files = {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file()}
    target_files = {p.relative_to(TARGET).as_posix() for p in TARGET.rglob("*") if p.is_file()}
    allowed_extra = {"assets/css/structure-preview.css"}
    slug_changes = len((source_files ^ target_files) - allowed_extra)
    sitemap_changed = int((SOURCE / "sitemap.xml").read_bytes() != (TARGET / "sitemap.xml").read_bytes())
    page_count_change = len(target_paths) - len(source_paths)
    favicon_error = int(not (TARGET / "assets" / "favicon" / "favicon.ico").exists())
    manifest_error = int(not (TARGET / "site.webmanifest").exists())
    school_connection_changes = sum(
        row.get("internal_link_targets_changed", 0)
        for row in rows
        if row.get("relative_path") != "index.html" and classify(metadata_by_slug[Path(str(row["relative_path"])).parent.name])["entity_type"] == "school"
    ) if False else 0
    # Link target invariance already covers school pages; retain a separately named aggregate.
    school_slugs = {str(item["slug"]) for item in metadata if item.get("school_name")}
    school_connection_changes = sum(
        int(row.get("internal_link_targets_changed", 0))
        for row in rows if Path(str(row["relative_path"])).parent.name in school_slugs
    )
    summary = {
        "source_html": len(source_paths), "conversion_target_html": len(source_paths),
        "generated_html": len(target_paths), "changed_pages": sum(
            not row.get("read_error") and (
                row["title_changed"] == 0 and row["description_changed"] == 0
            ) for row in rows
        ),
        "region_pages": classes["entity:region"], "school_pages": classes["entity:school"],
        "general_pages": classes["subject:general"], "math_pages": classes["subject:math"],
        "english_pages": classes["subject:english"], "elementary_pages": classes["grade:elementary"],
        "middle_pages": classes["grade:middle"], "high_pages": classes["grade:high"],
        **dict(counts), "broken_links": len(broken), "orphan_pages": len(orphans),
        "home_unreachable_pages": len(unreachable), "favicon_errors": favicon_error,
        "manifest_errors": manifest_error, "slug_changes": slug_changes,
        "sitemap_changes": sitemap_changed, "school_connection_changes": school_connection_changes,
        "page_count_change": page_count_change,
    }
    required_zero = [
        "read_errors", "zero_byte", "h1_errors", "duplicate_h1_h2", "empty_sections",
        "duplicate_card_hrefs", "broken_links", "orphan_pages", "home_unreachable_pages",
        "css_missing", "favicon_errors", "manifest_errors", "title_changed", "description_changed",
        "slug_changes", "canonical_changed", "sitemap_changes", "jsonld_changed",
        "internal_link_targets_changed", "school_connection_changes", "page_count_change",
        "body_content_text_changed",
    ]
    passed = len(source_paths) == len(target_paths) and all(summary.get(key, 0) == 0 for key in required_zero)
    report = {
        "status": "PASS" if passed else "FAIL", "source": str(SOURCE), "target": str(TARGET),
        "completed_at": datetime.now().astimezone().isoformat(), "summary": summary,
        "classification": dict(classes), "details": {
            "broken_links": broken[:200], "orphan_pages": orphans[:200],
            "home_unreachable_pages": unreachable[:200],
        },
    }
    atomic_json(OUT_JSON, report)
    lines = ["# GoodStudy 전체 구조 전수 감사", "", f"- 판정: **{report['status']}**", f"- 기준 후보: `{SOURCE}`", f"- 구조 후보: `{TARGET}`", "", "## 실제 수치", ""]
    lines.extend(f"- {key}: {value}" for key, value in summary.items())
    atomic_text(OUT_MD, "\n".join(lines) + "\n")
    atomic_text(LAYOUT, "\n".join([
        "# 전체 구조 적용 보고서", "",
        "- 승인된 header, brand, breadcrumb, title panel, content container, related card grid, footer를 전체 HTML에 적용했다.",
        "- H1과 동일한 첫 H2는 원문을 유지하고 `is-duplicate-heading` 클래스로 화면에서 숨긴다.",
        "- 지역 페이지 순서: 과목별 → 학교 → 하위 지역 → 학년별 → 인근 지역.",
        "- 학교 페이지 순서: 학교 과목별 → 소속 지역 → 같은 지역 학교 → 관련 학습.",
        "- 기존 고유 내부 href는 관계 그룹으로 재배치하며 카드 내 중복 href를 제거한다.",
        "- 모바일 1열, 태블릿 2열, 데스크톱 3열이며 1180px 컨테이너와 860px 읽기 영역을 사용한다.",
        "- 실제 이미지는 추가하지 않았고 빈 이미지 슬롯은 공간을 차지하지 않는다.",
    ]) + "\n")
    with DUP_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, ["relative_path", "href"]); writer.writeheader(); writer.writerows(duplicates)
    for source_url, target_url in broken:
        errors.append({"relative_path": source_url, "code": "broken_link", "detail": target_url})
    with ERROR_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, ["relative_path", "code", "detail"]); writer.writeheader(); writer.writerows(errors)
    if passed:
        atomic_json(CURRENT, {
            "candidate_path": str(TARGET), "status": "PASS",
            "reason": "Full structure conversion audit passed", "html_count": len(target_paths),
        })
    print(json.dumps({"status": report["status"], "summary": summary}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
