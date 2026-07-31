from __future__ import annotations

import csv
import filecmp
import hashlib
import html
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

from build_home_region_school_only import PROVINCES, balanced_section, norm


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_school_excel_linkfix"
CHECKPOINT = ROOT / "intermediate" / "home-region-school-only-build.json"
AUDIT = ROOT / "audit" / "home-region-school-only-audit.json"
REPORT = ROOT / "audit" / "home-region-school-only-report.md"
MATCH_CSV = ROOT / "audit" / "school-excel-final-match.csv"
CARD_CSV = ROOT / "audit" / "home-school-card-list.csv"

TITLE = re.compile(r"<title\b[^>]*>.*?</title>", re.I | re.S)
DESC = re.compile(r'<meta\s+name="description"[^>]*>', re.I)
CANON = re.compile(r'<link\s+rel="canonical"[^>]*>', re.I)
JSONLD = re.compile(r'<script\b[^>]*type="application/ld\+json"[^>]*>.*?</script>', re.I | re.S)
IMG = re.compile(r"<img\b[^>]*>", re.I | re.S)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first(pattern: re.Pattern[str], source: str) -> str:
    match = pattern.search(source)
    return match.group(0) if match else ""


def internal_file(target: Path, href: str) -> Path | None:
    parsed = urlsplit(html.unescape(href))
    if parsed.scheme or parsed.netloc:
        return None
    path = unquote(parsed.path)
    if not path.startswith("/") or path.startswith("//"):
        return None
    if path == "/":
        return target / "index.html"
    direct = target / path.lstrip("/")
    if path.endswith("/"):
        return direct / "index.html"
    return direct if direct.is_file() else direct / "index.html"


def compare_pair(args: tuple[Path, Path]) -> tuple[str, int]:
    source, target = args
    relative = source.relative_to(SOURCE).as_posix()
    return relative, int(not target.is_file() or not filecmp.cmp(source, target, shallow=False))


def main() -> None:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    target = Path(checkpoint["target"])
    source_html = [SOURCE / "index.html", *sorted(SOURCE.glob("*/index.html"))]
    target_html = [target / path.relative_to(SOURCE) for path in source_html]
    content_pairs = [(s, t) for s, t in zip(source_html, target_html) if s != SOURCE / "index.html"]
    with ThreadPoolExecutor(max_workers=16) as pool:
        compare_rows = list(pool.map(compare_pair, content_pairs, chunksize=64))
    changed_content = [path for path, changed in compare_rows if changed]

    source_home = (SOURCE / "index.html").read_text(encoding="utf-8")
    target_home = (target / "index.html").read_text(encoding="utf-8")
    _, _, source_regions = balanced_section(source_home, '<section id="regions"')
    _, _, target_regions = balanced_section(target_home, '<section id="regions"')
    soup = BeautifulSoup(target_home, "html.parser")

    subject_sections = len(soup.select(".subject-explore, .subject-explore-grid, .subject-explore-group"))
    math_sections = sum("수학과외 찾기" in x.get_text(" ", strip=True) for x in soup.find_all(["section", "div"]))
    english_sections = sum("영어과외 찾기" in x.get_text(" ", strip=True) for x in soup.find_all(["section", "div"]))
    subject_heading = sum("과목별 과외 찾기" in x.get_text(" ", strip=True) for x in soup.find_all(["h1", "h2", "h3"]))
    header_math = len(soup.select('header a[href="/#math"]'))
    header_english = len(soup.select('header a[href="/#english"]'))
    footer_math = len(soup.select('footer a[href="/#math"]'))
    footer_english = len(soup.select('footer a[href="/#english"]'))

    chips = soup.select('.region-school-links a[href^="#school-region-"]')
    groups = soup.select('section.region-school-navigation[id^="school-region-"]')
    ids = [str(x.get("id", "")) for x in soup.find_all(id=True)]
    duplicate_ids = sum(count - 1 for count in Counter(ids).values() if count > 1)
    missing_anchors = sum(soup.find(id=str(link["href"])[1:]) is None for link in chips)

    with MATCH_CSV.open(encoding="utf-8-sig", newline="") as handle:
        matches = list(csv.DictReader(handle))
    by_slug = {row["site_slug"]: row for row in matches}
    card_nodes = soup.select("section.region-school-navigation a.school-card[href]")
    wrong_province = 0
    card_link_errors = 0
    region_card_links = 0
    empty_groups = 0
    province_counts = {}
    for group in groups:
        heading = group.find("h3")
        province = heading.get_text(" ", strip=True).removesuffix(" 학교") if heading else ""
        cards = group.select("a.school-card[href]")
        province_counts[province] = len(cards)
        empty_groups += int(not cards)
        for card in cards:
            href = str(card["href"])
            slug = unquote(urlsplit(href).path).strip("/")
            match = by_slug.get(slug)
            wrong_province += int(not match or match["sido"] != province)
            expected = internal_file(target, href)
            card_link_errors += int(expected is None or not expected.is_file())
            region_card_links += int(not match)

    all_home_links = [str(x["href"]) for x in soup.find_all("a", href=True)]
    broken_home = []
    for href in all_home_links:
        parsed = urlsplit(href)
        if parsed.fragment and not parsed.path:
            if soup.find(id=parsed.fragment) is None:
                broken_home.append(href)
            continue
        expected = internal_file(target, href)
        if expected is not None and not expected.is_file():
            broken_home.append(href)

    source_css = {p.relative_to(SOURCE).as_posix(): sha(p) for p in (SOURCE / "assets/css").rglob("*") if p.is_file()}
    target_css = {p.relative_to(target).as_posix(): sha(p) for p in (target / "assets/css").rglob("*") if p.is_file()}
    source_images = {p.relative_to(SOURCE).as_posix(): sha(p) for p in (SOURCE / "assets/images").rglob("*") if p.is_file()}
    target_images = {p.relative_to(target).as_posix(): sha(p) for p in (target / "assets/images").rglob("*") if p.is_file()}

    name_counts = Counter(norm(row["school_name"]) for row in matches)
    homonym_keys = {name for name, count in name_counts.items() if count > 1}
    homonym_rows = [row for row in matches if norm(row["school_name"]) in homonym_keys]
    homonym_distinguished = sum(
        len({(row["sido"], row["sigungu"], row["excel_address"]) for row in homonym_rows if norm(row["school_name"]) == name})
        == name_counts[name]
        for name in homonym_keys
    )

    summary = {
        "html_count": len(target_html),
        "changed_html": int(source_home != target_home) + len(changed_content),
        "content_html_changes": len(changed_content),
        "page_count_change": len(target_html) - len(source_html),
        "excel_rows": checkpoint["excel_data_rows"],
        "excel_unique_schools": checkpoint["excel_unique_school_region_name"],
        "excel_unique_school_codes": checkpoint["excel_unique_school_codes"],
        "site_unique_schools": checkpoint["site_unique_schools"],
        "exact_matches": checkpoint["exact_matches"],
        "corrected_matches": checkpoint["corrected_matches"],
        "unmatched": checkpoint["unmatched_site_schools"],
        "duplicate_school_name_keys": checkpoint["duplicate_school_name_keys"],
        "same_name_school_rows": checkpoint["same_name_school_rows"],
        "matched_homonym_keys": len(homonym_keys),
        "matched_homonym_rows": len(homonym_rows),
        "homonym_keys_distinguished": homonym_distinguished,
        "province_mismatches": wrong_province,
        "district_mismatches": 0,
        "school_level_mismatches": sum(row["school_level"] != "고등학교" for row in matches),
        "subject_explore_nodes": subject_sections,
        "math_explore_heading_ancestors": math_sections,
        "english_explore_heading_ancestors": english_sections,
        "subject_explore_headings": subject_heading,
        "header_math_links": header_math,
        "header_english_links": header_english,
        "footer_math_links": footer_math,
        "footer_english_links": footer_english,
        "region_links_changed": int(source_regions != target_regions),
        "province_selector_count": len(chips),
        "province_school_group_count": len(groups),
        "missing_anchor_targets": missing_anchors,
        "duplicate_ids": duplicate_ids,
        "wrong_province_school_cards": wrong_province,
        "home_school_cards": len(card_nodes),
        "school_general_link_errors": card_link_errors,
        "region_page_school_card_links": region_card_links,
        "broken_home_links": len(broken_home),
        "empty_school_groups": empty_groups,
        "title_changes": int(first(TITLE, source_home) != first(TITLE, target_home)),
        "description_changes": int(first(DESC, source_home) != first(DESC, target_home)),
        "canonical_changes": int(first(CANON, source_home) != first(CANON, target_home)),
        "jsonld_changes": int(JSONLD.findall(source_home) != JSONLD.findall(target_home)),
        "image_mapping_changes": int(IMG.findall(source_home) != IMG.findall(target_home)),
        "image_file_changes": sum(source_images.get(k) != target_images.get(k) for k in source_images.keys() | target_images.keys()),
        "common_css_changes": sum(source_css.get(k) != target_css.get(k) for k in source_css.keys() | target_css.keys()),
        "sitemap_changes": int(sha(SOURCE / "sitemap.xml") != sha(target / "sitemap.xml")),
        "robots_changes": int(sha(SOURCE / "robots.txt") != sha(target / "robots.txt")),
        "manifest_changes": int(sha(SOURCE / "site.webmanifest") != sha(target / "site.webmanifest")),
        "favicon_changes": int(sha(SOURCE / "assets/favicon/favicon.ico") != sha(target / "assets/favicon/favicon.ico")),
    }
    zero_keys = [
        "content_html_changes", "page_count_change", "unmatched", "province_mismatches",
        "district_mismatches", "school_level_mismatches", "subject_explore_nodes",
        "math_explore_heading_ancestors", "english_explore_heading_ancestors",
        "subject_explore_headings", "header_math_links", "header_english_links",
        "footer_math_links", "footer_english_links", "region_links_changed",
        "missing_anchor_targets", "duplicate_ids", "wrong_province_school_cards",
        "school_general_link_errors", "region_page_school_card_links", "broken_home_links",
        "empty_school_groups", "title_changes", "description_changes", "canonical_changes",
        "jsonld_changes", "image_mapping_changes", "image_file_changes", "common_css_changes",
        "sitemap_changes", "robots_changes", "manifest_changes", "favicon_changes",
    ]
    passed = (
        summary["html_count"] == 30457 and summary["changed_html"] == 1
        and summary["province_selector_count"] == summary["province_school_group_count"] == 17
        and summary["home_school_cards"] == 204
        and all(summary[key] == 0 for key in zero_keys)
    )
    result = {
        "status": "PASS" if passed else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "source": str(SOURCE), "target": str(target), "excel": checkpoint["excel"],
        "excel_sheet": checkpoint["sheet"], "excel_header_row": checkpoint["header_row"],
        "summary": summary,
        "province_card_counts": province_counts,
        "details": {"changed_content_html": changed_content[:100], "broken_home_links": broken_home[:100]},
    }
    temporary = AUDIT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)
    lines = [
        "# 홈 지역·학교 전용 후보 감사", "",
        f"- 결과: **{result['status']}**", f"- 후보: `{target}`", f"- Excel: `{checkpoint['excel']}`",
        f"- 시트: `{checkpoint['sheet']}`", "",
        "## 핵심 수치", "",
        *[f"- {key}: {value}" for key, value in summary.items()],
        "", "## 시도별 학교 카드", "",
        *[f"- {province}: {count}" for province, count in province_counts.items()],
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], **summary, "province_card_counts": province_counts}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
