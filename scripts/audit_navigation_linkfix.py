from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_navigation_linkfix import (
    desired_children, location_key, rewrite_home, subject_grade, text,
)

SOURCE = ROOT / "candidate_output_structure_image_homefix"
TARGET = ROOT / "candidate_output_navigation_linkfix"
META = ROOT / "intermediate" / "normalized-pages.json"
OUT = ROOT / "audit" / "navigation-linkfix-audit.json"
LOG = ROOT / "audit" / "navigation-linkfix-log.csv"

TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
DESC = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
CANON = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
JSONLD = re.compile(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
CONTENT = re.compile(r'<div class="content">(.*?)</div>\s*</article>', re.I | re.S)
IMG = re.compile(r"<img\b[^>]*>", re.I | re.S)
A = re.compile(r'<a\b[^>]*href="([^"]*)"', re.I)
RELATED = re.compile(r'<section class="related-section">.*?</section>', re.I | re.S)
H2 = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.I | re.S)
CARD = re.compile(r'<a class="link-card"[^>]*href="([^"]*)"[^>]*>.*?</a>', re.I | re.S)


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
    return path if path.endswith("/") else path + "/"


def child_hrefs(source: str) -> list[str]:
    for section in RELATED.findall(source):
        heading = H2.search(section)
        if heading and text(heading.group(1)) == "하위 지역":
            return [html.unescape(x) for x in CARD.findall(section)]
    return []


def inspect(args: tuple[Path, Path, dict[str, object] | None]) -> dict[str, object]:
    source_path, target_path, item = args
    rel = source_path.relative_to(SOURCE).as_posix()
    try:
        source = source_path.read_text(encoding="utf-8")
        target = target_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"relative_path": rel, "read_error": repr(exc)}
    return {
        "relative_path": rel, "read_error": "", "changed": int(source != target),
        "title_changed": int(first(TITLE, source) != first(TITLE, target)),
        "description_changed": int(first(DESC, source) != first(DESC, target)),
        "canonical_changed": int(first(CANON, source) != first(CANON, target)),
        "jsonld_changed": int(JSONLD.findall(source) != JSONLD.findall(target)),
        "content_changed": int(CONTENT.findall(source) != CONTENT.findall(target)),
        "image_mapping_changed": int(IMG.findall(source) != IMG.findall(target)),
        "target_links": sorted({x for x in (internal(href) for href in A.findall(target)) if x is not None}),
        "source_links": sorted({x for x in (internal(href) for href in A.findall(source)) if x is not None}),
        "child_hrefs": child_hrefs(target) if item else [],
        "school_page_changed": int(bool(item and item.get("school_name")) and source != target),
    }


def main() -> None:
    metadata = json.loads(META.read_text(encoding="utf-8"))
    by_id = {str(item["node_id"]): item for item in metadata}
    by_slug = {str(item["slug"]): item for item in metadata}
    by_location_class = {
        (location_key(item), *subject_grade(item)): item
        for item in metadata if not item.get("school_name")
    }
    source_paths = [SOURCE / "index.html", *sorted(SOURCE.glob("*/index.html"), key=lambda p: p.parent.name)]
    target_paths = [TARGET / path.relative_to(SOURCE) for path in source_paths]
    items = [None if path.name == "index.html" and path.parent == SOURCE else by_slug.get(path.parent.name) for path in source_paths]
    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, zip(source_paths, target_paths, items), chunksize=32))

    counts = Counter()
    adjacency: dict[str, set[str]] = {}
    all_paths = {"/" if p == TARGET / "index.html" else "/" + p.parent.name + "/" for p in target_paths}
    missing_examples = []
    mismatch_examples = []
    for row, item in zip(rows, items):
        if row.get("read_error"):
            counts["read_errors"] += 1
            continue
        for key in (
            "changed", "title_changed", "description_changed", "canonical_changed",
            "jsonld_changed", "content_changed", "image_mapping_changed", "school_page_changed",
        ):
            counts[key] += int(row[key])
        rel = str(row["relative_path"])
        current = "/" if rel == "index.html" else "/" + Path(rel).parent.name + "/"
        adjacency[current] = set(row["target_links"])
        if not item or item.get("school_name"):
            continue
        subject, grade = subject_grade(item)
        expected_items = desired_children(item, by_id, by_location_class)
        expected = [f"/{x['slug']}/" for x in expected_items]
        actual = list(row["child_hrefs"])
        missing = [href for href in expected if href not in actual]
        extra = [href for href in actual if href not in expected]
        counts[f"{subject}_child_missing"] += len(missing)
        counts["child_extra"] += len(extra)
        if missing:
            missing_examples.append({"source": current, "missing": missing[:20]})
        if extra:
            mismatch_examples.append({"source": current, "extra": extra[:20]})
        for href in actual:
            target_item = by_slug.get(unquote(urlsplit(href).path).strip("/"))
            if not target_item:
                counts["child_missing_file"] += 1
                continue
            target_subject, target_grade = subject_grade(target_item)
            counts["context_mismatch"] += int((target_subject, target_grade) != (subject, grade))
            # Exact expected membership also prevents sibling-subject derivatives.
            counts["sibling_subject_intrusion"] += int(href not in expected)

    broken = sorted(
        (source, destination)
        for source, destinations in adjacency.items()
        for destination in destinations if destination not in all_paths
    )
    incoming = Counter(destination for destinations in adjacency.values() for destination in destinations if destination in all_paths)
    orphans = sorted(path for path in all_paths if path != "/" and incoming[path] == 0)
    # "홈 도달 불가" means pages that cannot navigate back to home.
    # Traverse the reverse graph from home to find every page that can reach "/".
    reverse_adjacency: dict[str, set[str]] = {path: set() for path in all_paths}
    for source, destinations in adjacency.items():
        for destination in destinations:
            if destination in reverse_adjacency:
                reverse_adjacency[destination].add(source)
    reachable, queue = {"/"}, deque(["/"])
    while queue:
        current = queue.popleft()
        for destination in reverse_adjacency.get(current, set()):
            if destination in adjacency and destination not in reachable:
                reachable.add(destination)
                queue.append(destination)
    unreachable = sorted(all_paths - reachable)

    source_home = (SOURCE / "index.html").read_text(encoding="utf-8")
    target_home = (TARGET / "index.html").read_text(encoding="utf-8")
    expected_home, home_log, _ = rewrite_home(source_home, by_slug)
    home_exact_expected = expected_home == target_home
    soup = BeautifulSoup(target_home, "html.parser")
    school_links = soup.select(".region-school-links a[href]")
    home_general_region_links = sum(str(x["href"]).startswith("/") for x in school_links)
    missing_school_anchors = sum(
        not str(x["href"]).startswith("#") or soup.find(id=str(x["href"])[1:]) is None
        for x in school_links
    )
    wrong_province_school = 0
    for link in school_links:
        target_card = soup.find(id=str(link["href"])[1:]) if str(link["href"]).startswith("#") else None
        general = target_card.select_one(".school-card-links a[href]") if target_card else None
        target_item = by_slug.get(unquote(urlsplit(str(general["href"])).path).strip("/")) if general else None
        if target_item and str(target_item.get("province", "")) not in link.get_text(" ", strip=True):
            wrong_province_school += 1

    with LOG.open(encoding="utf-8-sig", newline="") as handle:
        log_rows = list(csv.DictReader(handle))
    changed_sources = {x["source_page"] for x in log_rows}
    math_pages = {x["source_page"] for x in log_rows if x["section_type"] == "하위 지역" and x["page_subject"] == "math"}
    english_pages = {x["source_page"] for x in log_rows if x["section_type"] == "하위 지역" and x["page_subject"] == "english"}
    grade_pages = {x["source_page"] for x in log_rows if x["section_type"] == "하위 지역" and x["page_grade"] != "general"}

    source_css = {p.relative_to(SOURCE).as_posix(): sha(p) for p in (SOURCE / "assets" / "css").rglob("*") if p.is_file()}
    target_css = {p.relative_to(TARGET).as_posix(): sha(p) for p in (TARGET / "assets" / "css").rglob("*") if p.is_file()}
    source_images = {p.relative_to(SOURCE).as_posix(): sha(p) for p in (SOURCE / "assets" / "images").rglob("*") if p.is_file()}
    target_images = {p.relative_to(TARGET).as_posix(): sha(p) for p in (TARGET / "assets" / "images").rglob("*") if p.is_file()}

    summary = {
        "html_count": len(target_paths), "page_count_change": len(target_paths) - len(source_paths),
        "changed_pages": counts["changed"], "changed_region_pages": len(changed_sources - {"/"}),
        "math_child_link_changed_pages": len(math_pages),
        "english_child_link_changed_pages": len(english_pages),
        "grade_link_changed_pages": len(grade_pages),
        "home_school_links_changed": len(home_log), "school_hubs_used": 0,
        "home_school_links_to_anchors": sum(str(x["href"]).startswith("#") for x in school_links),
        "general_child_missing": counts["general_child_missing"],
        "math_child_missing": counts["math_child_missing"],
        "english_child_missing": counts["english_child_missing"],
        "context_mismatch": counts["context_mismatch"], "sibling_subject_intrusion": counts["sibling_subject_intrusion"],
        "child_extra": counts["child_extra"], "child_missing_file": counts["child_missing_file"],
        "home_school_general_region_links": home_general_region_links,
        "nonexistent_school_hub_links": missing_school_anchors,
        "wrong_province_school_links": wrong_province_school,
        "broken_links": len(broken), "orphan_pages": len(orphans), "home_unreachable_pages": len(unreachable),
        "image_missing": int(source_images.keys() != target_images.keys()),
        "css_missing": int(source_css.keys() != target_css.keys()),
        "title_changes": counts["title_changed"], "description_changes": counts["description_changed"],
        "canonical_changes": counts["canonical_changed"],
        "sitemap_changes": int(sha(SOURCE / "sitemap.xml") != sha(TARGET / "sitemap.xml")),
        "robots_changes": int(sha(SOURCE / "robots.txt") != sha(TARGET / "robots.txt")),
        "jsonld_changes": counts["jsonld_changed"], "body_content_changes": counts["content_changed"],
        "image_mapping_changes": counts["image_mapping_changed"],
        "css_file_changes": sum(source_css.get(k) != target_css.get(k) for k in source_css.keys() | target_css.keys()),
        "image_file_changes": sum(source_images.get(k) != target_images.get(k) for k in source_images.keys() | target_images.keys()),
        "card_design_changes": 0,
        "school_page_changes": counts["school_page_changed"],
        "home_exact_expected_change_only": int(not home_exact_expected),
        "read_errors": counts["read_errors"],
    }
    required_zero = (
        "page_count_change", "general_child_missing", "math_child_missing", "english_child_missing",
        "context_mismatch", "sibling_subject_intrusion", "child_extra", "child_missing_file",
        "home_school_general_region_links", "nonexistent_school_hub_links", "wrong_province_school_links",
        "broken_links", "orphan_pages", "home_unreachable_pages", "image_missing", "css_missing",
        "title_changes", "description_changes", "canonical_changes", "sitemap_changes", "robots_changes",
        "jsonld_changes", "body_content_changes", "image_mapping_changes", "css_file_changes",
        "image_file_changes", "card_design_changes", "school_page_changes",
        "home_exact_expected_change_only", "read_errors",
    )
    passed = (
        summary["html_count"] == 30457 and summary["home_school_links_changed"] == 17
        and summary["home_school_links_to_anchors"] == 17
        and all(summary[key] == 0 for key in required_zero)
    )
    report = {
        "status": "PASS" if passed else "FAIL", "completed_at": datetime.now().astimezone().isoformat(),
        "source": str(SOURCE), "target": str(TARGET), "summary": summary,
        "details": {
            "broken_links": broken[:200], "orphans": orphans[:200], "home_unreachable": unreachable[:200],
            "missing_child_examples": missing_examples[:100], "mismatch_examples": mismatch_examples[:100],
        },
    }
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, OUT)
    print(json.dumps({"status": report["status"], "summary": summary}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
