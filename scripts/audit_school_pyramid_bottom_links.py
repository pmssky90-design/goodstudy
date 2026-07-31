from __future__ import annotations

import csv
import filecmp
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

from build_school_pyramid_bottom_links import normalized_href


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_school_pyramid_navigation"
CHECKPOINT = ROOT / "intermediate" / "school-pyramid-bottom-links-build.json"
PAGES_CSV = ROOT / "audit" / "school-pyramid-bottom-links-pages.csv"
DUPLICATES_CSV = ROOT / "audit" / "school-pyramid-bottom-links-duplicates.csv"
CHECK_CSV = ROOT / "audit" / "school-pyramid-bottom-links-check.csv"
AUDIT = ROOT / "audit" / "school-pyramid-bottom-links-audit.json"
REPORT = ROOT / "audit" / "school-pyramid-bottom-links-report.md"

TITLE = re.compile(r"<title\b[^>]*>.*?</title>", re.I | re.S)
DESC = re.compile(r'<meta\s+name="description"[^>]*>', re.I)
CANON = re.compile(r'<link\s+rel="canonical"[^>]*>', re.I)
JSONLD = re.compile(r'<script\b[^>]*type="application/ld\+json"[^>]*>.*?</script>', re.I | re.S)
BREADCRUMB = re.compile(r'<nav class="breadcrumb".*?</nav>', re.I | re.S)
CONTENT = re.compile(r'<div class="content">.*?</div>\s*</article>', re.I | re.S)
IMG = re.compile(r"<img\b[^>]*>", re.I | re.S)
A = re.compile(r'<a\b[^>]*href="([^"]*)"', re.I)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first(pattern: re.Pattern[str], source: str) -> str:
    match = pattern.search(source)
    return match.group(0) if match else ""


def internal(href: str) -> str | None:
    parsed = urlsplit(html.unescape(href))
    if parsed.scheme or parsed.netloc:
        return None
    path = unquote(parsed.path)
    if not path.startswith("/") or path.startswith("//"):
        return None
    if path == "/":
        return "/"
    return path if path.endswith("/") else path + "/"


def inspect(args: tuple[Path, Path, bool]) -> dict[str, object]:
    source_path, target_path, expected_change = args
    relative = source_path.relative_to(SOURCE).as_posix()
    try:
        same = target_path.is_file() and filecmp.cmp(source_path, target_path, shallow=False)
        target = target_path.read_text(encoding="utf-8")
        source = source_path.read_text(encoding="utf-8") if not same else ""
    except Exception as exc:
        return {"relative": relative, "read_error": repr(exc)}
    changed = not same
    ids = re.findall(r'\bid="([^"]+)"', target, re.I)
    row = {
        "relative": relative, "read_error": "", "changed": int(changed),
        "unexpected_change": int(changed != expected_change),
        "links": sorted({x for x in (internal(href) for href in A.findall(target)) if x}),
        "duplicate_ids": sum(count - 1 for count in Counter(ids).values() if count > 1),
        "title_changed": 0, "description_changed": 0, "canonical_changed": 0,
        "jsonld_changed": 0, "breadcrumb_changed": 0, "content_changed": 0,
        "image_mapping_changed": 0, "card_links_changed": 0,
    }
    if changed:
        row.update({
            "title_changed": int(first(TITLE, source) != first(TITLE, target)),
            "description_changed": int(first(DESC, source) != first(DESC, target)),
            "canonical_changed": int(first(CANON, source) != first(CANON, target)),
            "jsonld_changed": int(JSONLD.findall(source) != JSONLD.findall(target)),
            "breadcrumb_changed": int(BREADCRUMB.findall(source) != BREADCRUMB.findall(target)),
            "content_changed": int(CONTENT.findall(source) != CONTENT.findall(target)),
            "image_mapping_changed": int(IMG.findall(source) != IMG.findall(target)),
            "card_links_changed": int(
                re.findall(r'<a class="(?:link-card|school-card)"[^>]*href="([^"]*)"', source, re.I)
                != re.findall(r'<a class="(?:link-card|school-card)"[^>]*href="([^"]*)"', target, re.I)
            ),
        })
    return row


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    target = Path(checkpoint["target"])
    expected = {f"{slug}/index.html" for slug in checkpoint["changed_slugs"]}
    source_paths = [SOURCE / "index.html", *sorted(SOURCE.glob("*/index.html"))]
    target_paths = [target / path.relative_to(SOURCE) for path in source_paths]
    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(
            inspect,
            ((s, t, s.relative_to(SOURCE).as_posix() in expected) for s, t in zip(source_paths, target_paths)),
            chunksize=64,
        ))

    counts = Counter()
    adjacency = {}
    all_paths = {"/" if p == target / "index.html" else f"/{p.parent.name}/" for p in target_paths}
    for row in rows:
        if row.get("read_error"):
            counts["read_errors"] += 1
            continue
        for key in (
            "changed", "unexpected_change", "duplicate_ids", "title_changed",
            "description_changed", "canonical_changed", "jsonld_changed",
            "breadcrumb_changed", "content_changed", "image_mapping_changed",
            "card_links_changed",
        ):
            counts[key] += int(row[key])
        relative = str(row["relative"])
        current = "/" if relative == "index.html" else f"/{Path(relative).parent.name}/"
        adjacency[current] = set(row["links"])

    broken = sorted(
        (source, destination)
        for source, destinations in adjacency.items()
        for destination in destinations if destination not in all_paths
    )
    incoming = Counter(
        destination for destinations in adjacency.values()
        for destination in destinations if destination in all_paths
    )
    orphans = sorted(path for path in all_paths if path != "/" and incoming[path] == 0)
    reverse = {path: set() for path in all_paths}
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
    home_unreachable = sorted(all_paths - reachable)

    with PAGES_CSV.open(encoding="utf-8-sig", newline="") as handle:
        page_logs = list(csv.DictReader(handle))
    source_log = {row["page"].strip("/"): row for row in page_logs}
    top_blocks = bottom_blocks = top_home_national = 0
    bottom_home = bottom_national = bottom_parent = 0
    href_changes = duplicate_moved_hrefs = wrong_bottom = 0
    check_rows = []
    for slug in checkpoint["changed_slugs"]:
        soup = BeautifulSoup((target / slug / "index.html").read_text(encoding="utf-8"), "html.parser")
        pyramid = soup.select_one("section.school-pyramid-navigation")
        top_nav = pyramid.select_one('nav[aria-label="상위 학교 탐색"]') if pyramid else None
        top_blocks += int(top_nav is not None)
        if top_nav:
            top_home_national += len(top_nav.select('a[href="/"], a[href="/#schools"]'))
        bottoms = soup.select("main > section.region-bottom-navigation")
        bottom_blocks += len(bottoms)
        if len(bottoms) != 1:
            wrong_bottom += 1
            continue
        anchors = bottoms[0].select("a[href]")
        hrefs = [str(anchor["href"]) for anchor in anchors]
        normalized = [normalized_href(href) for href in hrefs]
        duplicate_moved_hrefs += len(normalized) - len(set(normalized))
        bottom_home += sum(value == "/" for value in normalized)
        bottom_national += sum(value == "/#schools" for value in normalized)
        bottom_parent += sum(value not in ("/", "/#schools") for value in normalized)
        source_hrefs = source_log[slug]["source_hrefs"].split("|")
        href_changes += int(hrefs != source_hrefs)
        for anchor, href in zip(anchors, hrefs):
            path = internal(href)
            exists = int(path in all_paths if path else False)
            check_rows.append({
                "page": f"/{slug}/", "page_level": source_log[slug]["page_level"],
                "link_text": anchor.get_text(" ", strip=True), "href": href,
                "normalized_href": normalized_href(href), "location": "bottom",
                "file_exists": exists, "http_status": "",
                "error_type": "" if exists else "missing_file",
            })
    write_csv(
        CHECK_CSV, check_rows,
        ["page", "page_level", "link_text", "href", "normalized_href",
         "location", "file_exists", "http_status", "error_type"],
    )

    source_set = {p.relative_to(SOURCE).as_posix() for p in source_paths}
    target_set = {
        ("index.html" if p == target / "index.html" else p.relative_to(target).as_posix())
        for p in [target / "index.html", *target.glob("*/index.html")]
    }
    source_css = {p.relative_to(SOURCE).as_posix(): sha(p) for p in (SOURCE / "assets/css").rglob("*") if p.is_file()}
    target_css = {p.relative_to(target).as_posix(): sha(p) for p in (target / "assets/css").rglob("*") if p.is_file()}
    source_images = {p.relative_to(SOURCE).as_posix(): sha(p) for p in (SOURCE / "assets/images").rglob("*") if p.is_file()}
    target_images = {p.relative_to(target).as_posix(): sha(p) for p in (target / "assets/images").rglob("*") if p.is_file()}

    summary = {
        "html_count": len(target_set), "changed_html": counts["changed"],
        "new_html": len(target_set - source_set), "deleted_html": len(source_set - target_set),
        "unexpected_html_changes": counts["unexpected_change"],
        "target_province_pages": checkpoint["province_pages"],
        "target_district_pages": checkpoint["district_pages"],
        "top_blocks_removed": checkpoint["top_blocks_removed"],
        "bottom_blocks_moved": checkpoint["bottom_blocks_added"],
        "integrated_existing_bottom_pages": checkpoint["integrated_existing_bottom"],
        "links_moved": checkpoint["links_moved"],
        "links_not_added_due_to_duplicate": checkpoint["links_skipped_as_duplicate"],
        "duplicate_links_removed": checkpoint["duplicate_links_removed"],
        "top_navigation_blocks_remaining": top_blocks,
        "top_home_national_links_remaining": top_home_national,
        "bottom_navigation_blocks": bottom_blocks,
        "bottom_home_links": bottom_home,
        "bottom_national_links": bottom_national,
        "bottom_parent_links": bottom_parent,
        "duplicate_bottom_destination_links": duplicate_moved_hrefs,
        "wrong_bottom_block_count_pages": wrong_bottom,
        "href_changes": href_changes,
        "wrong_links": sum(not int(row["file_exists"]) for row in check_rows),
        "broken_internal_links": len(broken), "orphan_pages": len(orphans),
        "home_unreachable_pages": len(home_unreachable),
        "duplicate_ids": counts["duplicate_ids"],
        "title_changes": counts["title_changed"], "description_changes": counts["description_changed"],
        "canonical_changes": counts["canonical_changed"], "jsonld_changes": counts["jsonld_changed"],
        "breadcrumb_changes": counts["breadcrumb_changed"], "content_body_changes": counts["content_changed"],
        "image_mapping_changes": counts["image_mapping_changed"],
        "school_region_card_link_changes": counts["card_links_changed"],
        "sitemap_changes": int(sha(SOURCE / "sitemap.xml") != sha(target / "sitemap.xml")),
        "robots_changes": int(sha(SOURCE / "robots.txt") != sha(target / "robots.txt")),
        "image_file_changes": sum(source_images.get(k) != target_images.get(k) for k in source_images.keys() | target_images.keys()),
        "common_css_changes": sum(source_css.get(k) != target_css.get(k) for k in source_css.keys() | target_css.keys()),
        "read_errors": counts["read_errors"],
    }
    zero_keys = [
        "new_html", "deleted_html", "unexpected_html_changes",
        "top_navigation_blocks_remaining", "top_home_national_links_remaining",
        "duplicate_bottom_destination_links", "wrong_bottom_block_count_pages",
        "href_changes", "wrong_links", "broken_internal_links", "orphan_pages",
        "home_unreachable_pages", "duplicate_ids", "title_changes", "description_changes",
        "canonical_changes", "jsonld_changes", "breadcrumb_changes", "content_body_changes",
        "image_mapping_changes", "school_region_card_link_changes", "sitemap_changes",
        "robots_changes", "image_file_changes", "common_css_changes", "read_errors",
    ]
    passed = (
        summary["html_count"] == 30457 and summary["changed_html"] == 163
        and summary["bottom_navigation_blocks"] == 163
        and summary["bottom_home_links"] == 163
        and summary["bottom_national_links"] == 163
        and summary["bottom_parent_links"] == 146
        and all(summary[key] == 0 for key in zero_keys)
    )
    result = {
        "status": "PASS" if passed else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "source": str(SOURCE), "target": str(target), "summary": summary,
        "scope_note": "Duplicate navigation audit excludes immutable header, footer, and breadcrumb links.",
        "details": {
            "broken_links": broken[:200], "orphans": orphans[:200],
            "home_unreachable": home_unreachable[:200],
        },
    }
    temporary = AUDIT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)
    lines = [
        "# 학교 피라미드 하단 링크 감사", "", f"- 결과: **{result['status']}**",
        f"- 후보: `{target}`", "", "## 핵심 수치", "",
        *[f"- {key}: {value}" for key, value in summary.items()],
        "", f"> {result['scope_note']}",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], **summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
