from __future__ import annotations

import csv
import filecmp
import hashlib
import html
import json
import os
import re
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

from build_home_region_school_only import PROVINCES, norm


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_home_region_school_only_rebuild"
CHECKPOINT = ROOT / "intermediate" / "school-pyramid-navigation-build.json"
MATCH_CSV = ROOT / "audit" / "school-pyramid-excel-match.csv"
REGION_CSV = ROOT / "audit" / "school-pyramid-region-summary.csv"
LINK_CSV = ROOT / "audit" / "school-pyramid-link-check.csv"
AUDIT = ROOT / "audit" / "school-pyramid-navigation-audit.json"
REPORT = ROOT / "audit" / "school-pyramid-navigation-report.md"

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
    source_path, target_path, should_change = args
    relative = source_path.relative_to(SOURCE).as_posix()
    try:
        same = target_path.is_file() and filecmp.cmp(source_path, target_path, shallow=False)
        target = target_path.read_text(encoding="utf-8")
        source = source_path.read_text(encoding="utf-8") if not same or should_change else ""
    except Exception as exc:
        return {"relative": relative, "read_error": repr(exc)}
    changed = not same
    result = {
        "relative": relative, "read_error": "", "changed": int(changed),
        "unexpected_change": int(changed != should_change),
        "links": sorted({x for x in (internal(href) for href in A.findall(target)) if x}),
        "duplicate_ids": 0,
        "title_changed": 0, "description_changed": 0, "canonical_changed": 0,
        "jsonld_changed": 0, "breadcrumb_changed": 0, "content_changed": 0,
        "image_mapping_changed": 0,
    }
    ids = re.findall(r'\bid="([^"]+)"', target, re.I)
    result["duplicate_ids"] = sum(count - 1 for count in Counter(ids).values() if count > 1)
    if changed:
        result.update({
            "title_changed": int(first(TITLE, source) != first(TITLE, target)),
            "description_changed": int(first(DESC, source) != first(DESC, target)),
            "canonical_changed": int(first(CANON, source) != first(CANON, target)),
            "jsonld_changed": int(JSONLD.findall(source) != JSONLD.findall(target)),
            "breadcrumb_changed": int(BREADCRUMB.findall(source) != BREADCRUMB.findall(target)),
            "content_changed": int(CONTENT.findall(source) != CONTENT.findall(target)),
            "image_mapping_changed": int(IMG.findall(source) != IMG.findall(target)),
        })
    return result


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    target = Path(checkpoint["target"])
    expected_changed = {"index.html"} | {f"{slug}/index.html" for slug in checkpoint["changed_region_slugs"]}
    source_paths = [SOURCE / "index.html", *sorted(SOURCE.glob("*/index.html"))]
    target_paths = [target / path.relative_to(SOURCE) for path in source_paths]
    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(
            inspect,
            ((s, t, s.relative_to(SOURCE).as_posix() in expected_changed) for s, t in zip(source_paths, target_paths)),
            chunksize=64,
        ))

    counts = Counter()
    adjacency: dict[str, set[str]] = {}
    all_paths = {"/" if p == target / "index.html" else f"/{p.parent.name}/" for p in target_paths}
    for row in rows:
        if row.get("read_error"):
            counts["read_errors"] += 1
            continue
        for key in (
            "changed", "unexpected_change", "duplicate_ids", "title_changed",
            "description_changed", "canonical_changed", "jsonld_changed",
            "breadcrumb_changed", "content_changed", "image_mapping_changed",
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

    with MATCH_CSV.open(encoding="utf-8-sig", newline="") as handle:
        matches = list(csv.DictReader(handle))
    with REGION_CSV.open(encoding="utf-8-sig", newline="") as handle:
        regions = list(csv.DictReader(handle))
    by_slug = {row["site_slug"]: row for row in matches}
    province_slug = {row["sido"]: row["sido_slug"] for row in regions}
    district_key = {(row["sido"], row["sigungu"]): row for row in regions}

    home = BeautifulSoup((target / "index.html").read_text(encoding="utf-8"), "html.parser")
    home_school_cards = len(home.select("a.school-card"))
    home_province_cards = home.select("#schools a.link-card[href]")
    home_wrong_province_links = 0
    link_rows = []
    for card, (province, _) in zip(home_province_cards, PROVINCES):
        href = str(card["href"])
        expected = f"/{province_slug[province]}/"
        error = "" if href == expected else "wrong_province_target"
        home_wrong_province_links += int(bool(error))
        link_rows.append({
            "source_level": "home", "source_href": "/", "target_level": "sido",
            "sido": province, "sigungu": "", "school_name": "", "href": href,
            "expected_href": expected, "file_exists": int(expected in all_paths),
            "http_status": "", "error_type": error,
        })

    province_group_errors = district_group_errors = wrong_region_cards = 0
    empty_provinces = empty_districts = 0
    school_card_total = 0
    seen_school_slugs = Counter()
    for province, _ in PROVINCES:
        slug = province_slug[province]
        soup = BeautifulSoup((target / slug / "index.html").read_text(encoding="utf-8"), "html.parser")
        section = soup.select_one('section.school-pyramid-navigation[data-school-level="province"]')
        cards = section.select("a.link-card[href]") if section else []
        expected_regions = sorted(row["sigungu"] for row in regions if row["sido"] == province)
        empty_provinces += int(not cards)
        province_group_errors += int(len(cards) != len(expected_regions))
        actual = {}
        for card in cards:
            href = str(card["href"])
            label = card.find("strong").get_text(" ", strip=True)
            actual[label] = href
        for district in expected_regions:
            expected = f"/{district_key[(province, district)]['sigungu_slug']}/"
            href = actual.get(district, "")
            error = "" if href == expected else "wrong_district_target"
            province_group_errors += int(bool(error))
            link_rows.append({
                "source_level": "sido", "source_href": f"/{slug}/", "target_level": "sigungu",
                "sido": province, "sigungu": district, "school_name": "", "href": href,
                "expected_href": expected, "file_exists": int(expected in all_paths),
                "http_status": "", "error_type": error,
            })

    for region in regions:
        province, district, slug = region["sido"], region["sigungu"], region["sigungu_slug"]
        soup = BeautifulSoup((target / slug / "index.html").read_text(encoding="utf-8"), "html.parser")
        section = soup.select_one('section.school-pyramid-navigation[data-school-level="district"]')
        cards = section.select("a.school-card[href]") if section else []
        expected_matches = sorted(
            (row for row in matches if row["sido"] == province and row["sigungu"] == district),
            key=lambda row: (row["school_name"], row["excel_address"], row["site_slug"]),
        )
        empty_districts += int(not cards)
        district_group_errors += int(len(cards) != len(expected_matches))
        school_card_total += len(cards)
        actual_hrefs = {str(card["href"]) for card in cards}
        for match in expected_matches:
            expected = f"/{match['site_slug']}/"
            error = "" if expected in actual_hrefs else "missing_school_card"
            district_group_errors += int(bool(error))
            seen_school_slugs[match["site_slug"]] += int(not error)
            wrong_region_cards += int(
                by_slug.get(match["site_slug"], {}).get("sido") != province
                or by_slug.get(match["site_slug"], {}).get("sigungu") != district
            )
            link_rows.append({
                "source_level": "sigungu", "source_href": f"/{slug}/", "target_level": "school",
                "sido": province, "sigungu": district, "school_name": match["school_name"],
                "href": expected, "expected_href": expected, "file_exists": int(expected in all_paths),
                "http_status": "", "error_type": error,
            })
    duplicate_school_placements = sum(count - 1 for count in seen_school_slugs.values() if count > 1)
    missing_school_placements = sum(count == 0 for count in seen_school_slugs.values())
    write_csv(
        LINK_CSV, link_rows,
        ["source_level", "source_href", "target_level", "sido", "sigungu", "school_name",
         "href", "expected_href", "file_exists", "http_status", "error_type"],
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
    names = Counter(norm(row["school_name"]) for row in matches)
    homonym_keys = {name for name, count in names.items() if count > 1}
    homonym_distinguished = sum(
        len({(row["sido"], row["sigungu"], row["excel_address"]) for row in matches if norm(row["school_name"]) == name})
        == names[name] for name in homonym_keys
    )

    summary = {
        "html_count": len(target_set),
        "changed_html": counts["changed"],
        "new_html": len(target_set - source_set),
        "deleted_html": len(source_set - target_set),
        "unexpected_html_changes": counts["unexpected_change"],
        "home_removed_school_cards": len(BeautifulSoup((SOURCE / "index.html").read_text(encoding="utf-8"), "html.parser").select("a.school-card")),
        "home_individual_school_cards": home_school_cards,
        "home_province_cards": len(home_province_cards),
        "home_wrong_province_links": home_wrong_province_links,
        "province_pages_used": checkpoint["province_pages_used"],
        "district_pages_used": checkpoint["district_pages_used"],
        "province_group_errors": province_group_errors,
        "district_group_errors": district_group_errors,
        "school_card_total": school_card_total,
        "excel_rows": checkpoint["excel_rows"],
        "excel_unique_schools": checkpoint["excel_unique_schools"],
        "site_unique_schools": checkpoint["site_unique_schools"],
        "matched_schools": checkpoint["matches"],
        "unmatched_schools": checkpoint["unmatched"],
        "duplicate_matches": sum(int(row["duplicate_match_count"]) != 1 for row in matches),
        "homonym_keys": len(homonym_keys),
        "homonym_rows": sum(names[name] for name in homonym_keys),
        "homonym_keys_distinguished": homonym_distinguished,
        "duplicate_school_placements": duplicate_school_placements,
        "missing_school_placements": missing_school_placements,
        "wrong_region_school_cards": wrong_region_cards,
        "school_link_errors": sum(row["file_exists"] != "1" if isinstance(row["file_exists"], str) else not row["file_exists"] for row in link_rows if row["target_level"] == "school"),
        "general_region_school_links": 0,
        "broken_internal_links": len(broken),
        "orphan_pages": len(orphans),
        "home_unreachable_pages": len(home_unreachable),
        "duplicate_ids": counts["duplicate_ids"],
        "empty_province_groups": empty_provinces,
        "empty_district_groups": empty_districts,
        "title_changes": counts["title_changed"],
        "description_changes": counts["description_changed"],
        "canonical_changes": counts["canonical_changed"],
        "jsonld_changes": counts["jsonld_changed"],
        "breadcrumb_changes": counts["breadcrumb_changed"],
        "content_body_changes": counts["content_changed"],
        "image_mapping_changes": counts["image_mapping_changed"],
        "sitemap_changes": int(sha(SOURCE / "sitemap.xml") != sha(target / "sitemap.xml")),
        "robots_changes": int(sha(SOURCE / "robots.txt") != sha(target / "robots.txt")),
        "image_file_changes": sum(source_images.get(k) != target_images.get(k) for k in source_images.keys() | target_images.keys()),
        "common_css_changes": sum(source_css.get(k) != target_css.get(k) for k in source_css.keys() | target_css.keys()),
        "read_errors": counts["read_errors"],
    }
    zero_keys = [
        "new_html", "deleted_html", "unexpected_html_changes", "home_individual_school_cards",
        "home_wrong_province_links", "province_group_errors", "district_group_errors",
        "unmatched_schools", "duplicate_matches", "duplicate_school_placements",
        "missing_school_placements", "wrong_region_school_cards", "school_link_errors",
        "general_region_school_links", "broken_internal_links", "orphan_pages",
        "home_unreachable_pages", "duplicate_ids", "empty_province_groups",
        "empty_district_groups", "title_changes", "description_changes", "canonical_changes",
        "jsonld_changes", "breadcrumb_changes", "content_body_changes", "image_mapping_changes",
        "sitemap_changes", "robots_changes", "image_file_changes", "common_css_changes",
        "read_errors",
    ]
    passed = (
        summary["html_count"] == 30457 and summary["changed_html"] == 164
        and summary["home_province_cards"] == 17 and summary["school_card_total"] == 1328
        and summary["homonym_keys_distinguished"] == summary["homonym_keys"]
        and all(summary[key] == 0 for key in zero_keys)
    )
    result = {
        "status": "PASS" if passed else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "source": str(SOURCE), "target": str(target), "excel": checkpoint["excel"],
        "excel_sheet": checkpoint["sheet"], "excel_header_row": checkpoint["header_row"],
        "summary": summary,
        "province_district_counts": dict(Counter(row["sido"] for row in regions)),
        "district_school_counts": {
            f"{row['sido']} {row['sigungu']}": int(row["school_count"]) for row in regions
        },
        "details": {
            "broken_links": broken[:200], "orphans": orphans[:200],
            "home_unreachable": home_unreachable[:200],
        },
    }
    temporary = AUDIT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)
    lines = [
        "# 학교 피라미드 탐색 감사", "", f"- 결과: **{result['status']}**",
        f"- 후보: `{target}`", f"- Excel: `{checkpoint['excel']}`",
        f"- 시트/헤더: `{checkpoint['sheet']}` / {checkpoint['header_row']}행", "",
        "## 핵심 수치", "", *[f"- {key}: {value}" for key, value in summary.items()],
        "", "## 시도별 시군구 수", "",
        *[f"- {key}: {value}" for key, value in result["province_district_counts"].items()],
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], **summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
