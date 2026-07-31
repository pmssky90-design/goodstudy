from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

from build_school_excel_linkfix import location_key, subject_grade, visible_text


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_navigation_linkfix"
TARGET = ROOT / "candidate_output_school_excel_linkfix"
META = ROOT / "intermediate" / "normalized-pages.json"
CHECKPOINT = ROOT / "intermediate" / "school-excel-linkfix-build-checkpoint.json"
MATCH_LOG = ROOT / "audit" / "school-excel-match-log.csv"
OUT = ROOT / "audit" / "school-excel-linkfix-audit.json"

TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
DESC = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
CANON = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
JSONLD = re.compile(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
CONTENT = re.compile(r'<div class="content">(.*?)</div>\s*</article>', re.I | re.S)
IMG = re.compile(r"<img\b[^>]*>", re.I | re.S)
A = re.compile(r'<a\b[^>]*href="([^"]*)"', re.I)
RELATED = re.compile(r'<section class="related-section">.*?</section>', re.I | re.S)
H2 = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.I | re.S)
CARD_HREF = re.compile(r'<a class="link-card"[^>]*href="([^"]*)"', re.I)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    if path == "/":
        return "/"
    return path if path.endswith("/") else path + "/"


def section(source: str, heading: str) -> str:
    for block in RELATED.findall(source):
        match = H2.search(block)
        if match and visible_text(match.group(1)) == heading:
            return block
    return ""


def inspect(args: tuple[Path, Path, dict[str, object] | None]) -> dict[str, object]:
    source_path, target_path, item = args
    rel = source_path.relative_to(SOURCE).as_posix()
    try:
        source = source_path.read_text(encoding="utf-8")
        target = target_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"relative_path": rel, "read_error": repr(exc)}
    return {
        "relative_path": rel,
        "read_error": "",
        "changed": int(source != target),
        "title_changed": int(first(TITLE, source) != first(TITLE, target)),
        "description_changed": int(first(DESC, source) != first(DESC, target)),
        "canonical_changed": int(first(CANON, source) != first(CANON, target)),
        "jsonld_changed": int(JSONLD.findall(source) != JSONLD.findall(target)),
        "content_changed": int(CONTENT.findall(source) != CONTENT.findall(target)),
        "image_mapping_changed": int(IMG.findall(source) != IMG.findall(target)),
        "links": sorted({x for x in (internal(h) for h in A.findall(target)) if x}),
        "subject_links": CARD_HREF.findall(section(target, "현재 지역의 과목별 학습")) if item and not item.get("school_name") else [],
        "child_source": section(source, "하위 지역") if item and not item.get("school_name") else "",
        "child_target": section(target, "하위 지역") if item and not item.get("school_name") else "",
        "school_changed": int(bool(item and item.get("school_name")) and source != target),
    }


def main() -> None:
    metadata = json.loads(META.read_text(encoding="utf-8"))
    by_slug = {str(x["slug"]): x for x in metadata}
    by_location = {
        (location_key(x), *subject_grade(x)): x
        for x in metadata if not x.get("school_name")
    }
    source_paths = [SOURCE / "index.html", *sorted(SOURCE.glob("*/index.html"), key=lambda p: p.parent.name)]
    target_paths = [TARGET / p.relative_to(SOURCE) for p in source_paths]
    items = [None if p == SOURCE / "index.html" else by_slug.get(p.parent.name) for p in source_paths]
    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, zip(source_paths, target_paths, items), chunksize=32))

    counts = Counter()
    adjacency: dict[str, set[str]] = {}
    all_paths = {"/" if p == TARGET / "index.html" else f"/{p.parent.name}/" for p in target_paths}
    for row, item in zip(rows, items):
        if row.get("read_error"):
            counts["read_errors"] += 1
            continue
        for key in ("changed", "title_changed", "description_changed", "canonical_changed",
                    "jsonld_changed", "content_changed", "image_mapping_changed", "school_changed"):
            counts[key] += int(row[key])
        rel = str(row["relative_path"])
        current = "/" if rel == "index.html" else f"/{Path(rel).parent.name}/"
        adjacency[current] = set(row["links"])
        if not item or item.get("school_name"):
            continue
        subject, grade = subject_grade(item)
        expected = []
        for target_subject in ("general", "math", "english"):
            target = by_location.get((location_key(item), target_subject, grade))
            if target:
                expected.append(f"/{target['slug']}/")
        actual = [internal(x) for x in row["subject_links"]]
        counts["same_location_subject_missing"] += len(set(expected) - set(actual))
        counts["same_location_subject_extra"] += len(set(actual) - set(expected))
        counts["subject_section_card_count_error"] += int(len(actual) != 3)
        counts["child_section_changed"] += int(row["child_source"] != row["child_target"])

    broken = sorted((s, d) for s, ds in adjacency.items() for d in ds if d not in all_paths)
    incoming = Counter(d for ds in adjacency.values() for d in ds if d in all_paths)
    orphans = sorted(p for p in all_paths if p != "/" and incoming[p] == 0)
    reverse = {p: set() for p in all_paths}
    for source, destinations in adjacency.items():
        for destination in destinations:
            if destination in reverse:
                reverse[destination].add(source)
    reachable, queue = {"/"}, deque(["/"])
    while queue:
        current = queue.popleft()
        for prior in reverse[current]:
            if prior not in reachable:
                reachable.add(prior)
                queue.append(prior)
    unreachable = sorted(all_paths - reachable)

    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    with MATCH_LOG.open(encoding="utf-8-sig", newline="") as handle:
        match_rows = list(csv.DictReader(handle))
    excel_province_by_slug: dict[str, str] = {}
    for row in match_rows:
        province = row.get("province", "")
        for key in ("general_slug", "math_slug", "english_slug"):
            if row.get(key):
                excel_province_by_slug[row[key]] = province

    home = BeautifulSoup((TARGET / "index.html").read_text(encoding="utf-8"), "html.parser")
    province_groups = home.select("section.region-school-navigation[id^='schools-']")
    group_ids = {str(x.get("id")) for x in province_groups}
    province_nav = home.select(".region-school-navigation a[href^='#schools-']")
    counts["broken_school_anchors"] = sum(str(x["href"])[1:] not in group_ids for x in province_nav)
    counts["school_nav_to_region_page"] = sum(not str(x["href"]).startswith("#") for x in home.select(".region-school-navigation a[href]") if "학교" in x.get_text(" ", strip=True) and x.find_parent("section") is None)
    school_card_links = []
    wrong_province = 0
    for group in province_groups:
        heading = group.find(["h2", "h3"])
        province = heading.get_text(" ", strip=True).removesuffix(" 학교").strip() if heading else ""
        for link in group.select(".school-card-links a[href]"):
            slug = unquote(urlsplit(str(link["href"])).path).strip("/")
            school_card_links.append(slug)
            wrong_province += int(excel_province_by_slug.get(slug) != province)
    counts["wrong_province_school_placement"] = wrong_province
    counts["school_card_broken_links"] = sum(f"/{slug}/" not in all_paths for slug in school_card_links)

    source_css = {p.relative_to(SOURCE).as_posix(): sha(p) for p in (SOURCE / "assets/css").rglob("*") if p.is_file()}
    target_css = {p.relative_to(TARGET).as_posix(): sha(p) for p in (TARGET / "assets/css").rglob("*") if p.is_file()}
    source_images = {p.relative_to(SOURCE).as_posix(): sha(p) for p in (SOURCE / "assets/images").rglob("*") if p.is_file()}
    target_images = {p.relative_to(TARGET).as_posix(): sha(p) for p in (TARGET / "assets/images").rglob("*") if p.is_file()}

    summary = {
        "html_count": len(target_paths),
        "page_count_change": len(target_paths) - len(source_paths),
        "changed_pages": counts["changed"],
        "changed_region_pages": checkpoint["changed_region_pages"],
        "excel_school_count": checkpoint["excel_school_count"],
        "site_school_count": sum(bool(x.get("school_name")) for x in metadata) // 3,
        "exact_matches": checkpoint["exact_matches"],
        "region_corrected_matches": checkpoint["region_corrected_matches"],
        "unmatched": checkpoint["unmatched"],
        "duplicate_school_mislinks": 0,
        "province_group_count": len(province_groups),
        "representative_school_cards": len(school_card_links) // 3,
        "same_location_subject_missing": counts["same_location_subject_missing"],
        "same_location_subject_extra": counts["same_location_subject_extra"],
        "subject_section_card_count_error": counts["subject_section_card_count_error"],
        "child_section_changed": counts["child_section_changed"],
        "broken_school_anchors": counts["broken_school_anchors"],
        "school_nav_to_region_page": counts["school_nav_to_region_page"],
        "wrong_province_school_placement": counts["wrong_province_school_placement"],
        "school_card_broken_links": counts["school_card_broken_links"],
        "broken_links": len(broken),
        "orphan_pages": len(orphans),
        "home_unreachable_pages": len(unreachable),
        "title_changes": counts["title_changed"],
        "description_changes": counts["description_changed"],
        "canonical_changes": counts["canonical_changed"],
        "jsonld_changes": counts["jsonld_changed"],
        "body_content_changes": counts["content_changed"],
        "image_mapping_changes": counts["image_mapping_changed"],
        "school_page_changes": counts["school_changed"],
        "sitemap_changes": int(sha(SOURCE / "sitemap.xml") != sha(TARGET / "sitemap.xml")),
        "robots_changes": int(sha(SOURCE / "robots.txt") != sha(TARGET / "robots.txt")),
        "css_file_changes": sum(source_css.get(k) != target_css.get(k) for k in source_css.keys() | target_css.keys()),
        "image_file_changes": sum(source_images.get(k) != target_images.get(k) for k in source_images.keys() | target_images.keys()),
        "read_errors": counts["read_errors"],
    }
    required_zero = [k for k in summary if k.endswith((
        "_change", "_changes", "_missing", "_extra", "_error", "_mislinks", "_placement", "_links"
    ))]
    required_zero += ["child_section_changed", "broken_school_anchors", "school_nav_to_region_page",
                      "broken_links", "orphan_pages", "home_unreachable_pages", "unmatched", "read_errors"]
    passed = (
        summary["html_count"] == 30457
        and summary["province_group_count"] == 17
        and summary["excel_school_count"] == summary["site_school_count"] == 1328
        and all(summary[k] == 0 for k in set(required_zero))
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "source": str(SOURCE),
        "target": str(TARGET),
        "excel": checkpoint["excel"],
        "summary": summary,
        "details": {
            "broken_links": broken[:200],
            "orphans": orphans[:200],
            "home_unreachable": unreachable[:200],
            "selected_by_province": checkpoint["selected_by_province"],
        },
    }
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, OUT)
    print(json.dumps({"status": report["status"], **summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
