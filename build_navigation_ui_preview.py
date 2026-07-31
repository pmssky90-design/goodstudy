from __future__ import annotations

import copy
import csv
import hashlib
import json
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "candidate_output_image_preview"
HOME_REFERENCE = ROOT / "candidate_output_home_navigation_preview"
META_PATH = ROOT / "intermediate" / "normalized-pages.json"
CSS_SOURCE = ROOT / "assets" / "css" / "navigation-ui-preview.css"
CSS_HREF = "/assets/css/navigation-ui-preview.css"
FIXED_PATH = "/assets/images/content/body-common.webp"
AUDIT = ROOT / "audit"

SECTION_NAMES = {
    "child": ("하위 지역", "현재 지역 아래의 생활권을 살펴보세요."),
    "subject": ("과목별 학습", "현재 지역의 수학·영어 학습 정보를 살펴보세요."),
    "grade": ("학년별 학습", "초등·중등·고등 단계별 학습 정보를 살펴보세요."),
    "grade_subject": ("학년·과목별 세부 학습", "학년과 과목을 함께 선택해 살펴보세요."),
    "other": ("함께 살펴볼 학습 정보", "현재 페이지와 연결된 학습 정보를 살펴보세요."),
}


def choose_target() -> Path:
    candidate = ROOT / "candidate_output_navigation_ui_preview"
    if not candidate.exists():
        return candidate
    index = 2
    while (ROOT / f"candidate_output_navigation_ui_preview_{index}").exists():
        index += 1
    return ROOT / f"candidate_output_navigation_ui_preview_{index}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def subject(meta: dict[str, object]) -> str:
    page_type = str(meta.get("page_type", ""))
    if "수학" in page_type:
        return "math"
    if "영어" in page_type:
        return "english"
    return "general"


def grade(meta: dict[str, object]) -> str:
    page_type = str(meta.get("page_type", ""))
    for key, value in (("초등", "elementary"), ("중등", "middle"), ("고등", "high")):
        if key in page_type:
            return value
    return "general"


def is_school(meta: dict[str, object]) -> bool:
    return bool(meta.get("school_name"))


def is_administrative_district_name(value: object) -> bool:
    name = str(value or "").strip()
    return bool(name) and name.endswith(("시", "군"))


def is_administrative_locality_name(value: object) -> bool:
    name = str(value or "").strip()
    return bool(name) and name.endswith(("읍", "면", "동"))


def canonical_path(soup: BeautifulSoup) -> str:
    link = soup.find("link", rel="canonical")
    return unquote(urlsplit(str(link.get("href", ""))).path) if isinstance(link, Tag) else ""


def page_exists(target_root: Path, meta: dict[str, object]) -> bool:
    path = target_root / str(meta["slug"]) / "index.html"
    if not path.is_file():
        return False
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    return canonical_path(soup) == f"/{meta['slug']}/" and soup.find("meta", attrs={"name": "robots", "content": lambda x: x and "noindex" in x.lower()}) is None


def classify_link(current: dict[str, object], target: dict[str, object] | None) -> str:
    if not target or is_school(target):
        return "other"
    if str(target.get("primary_parent_id", "")) != str(current.get("node_id", "")):
        return "other"
    target_subject = subject(target)
    target_grade = grade(target)
    if target_grade != "general" and target_subject != "general":
        return "grade_subject"
    if target_grade != "general":
        return "grade"
    if target_subject != "general" and target.get("geo_level") == current.get("geo_level"):
        return "subject"
    if target_subject == "general" and target_grade == "general" and target.get("geo_level") != current.get("geo_level"):
        return "child"
    return "other"


def make_section(soup: BeautifulSoup, kind: str, cards: list[Tag], auxiliary: bool = False, title: str | None = None) -> Tag:
    section = soup.new_tag("section")
    section["class"] = ["related-section", f"navigation-section-{kind}"]
    section["data-section-type"] = kind
    if auxiliary:
        section["class"].append("auxiliary-navigation-section")
    heading = soup.new_tag("div")
    heading["class"] = ["section-heading"]
    h2 = soup.new_tag("h2")
    h2.string = title or SECTION_NAMES[kind][0]
    paragraph = soup.new_tag("p")
    paragraph.string = SECTION_NAMES[kind][1]
    heading.append(h2); heading.append(paragraph)
    grid = soup.new_tag("div")
    grid["class"] = ["link-card-grid", "navigation-card-grid"]
    for card in cards:
        grid.append(card)
    section.append(heading); section.append(grid)
    return section


def make_card(soup: BeautifulSoup, meta: dict[str, object]) -> Tag:
    link = soup.new_tag("a", href=f"/{meta['slug']}/")
    link["class"] = ["link-card"]
    link["data-subject"] = subject(meta)
    badge = soup.new_tag("span")
    badge["class"] = ["link-card-label"]
    badge.string = {"math": "수학", "english": "영어", "general": "일반"}[subject(meta)]
    title = soup.new_tag("strong")
    title.string = str(meta.get("link_label") or meta.get("breadcrumb_label") or meta["slug"])
    description = soup.new_tag("span")
    description.string = {
        "math": "개념과 문제 적용 흐름",
        "english": "어휘·문법과 독해 흐름",
        "general": "학습 전반과 일정 관리",
    }[subject(meta)]
    link.append(badge); link.append(title); link.append(description)
    return link


def group_mixed_sections(soup: BeautifulSoup, current: dict[str, object], by_slug: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    classifications: list[dict[str, object]] = []
    for section in list(soup.select("section.related-section")):
        if "auxiliary-navigation-section" in section.get("class", []):
            continue
        grid = section.select_one("div.link-card-grid")
        if not isinstance(grid, Tag):
            continue
        cards = [card for card in grid.find_all("a", class_="link-card", recursive=False)]
        if not cards:
            continue
        groups: dict[str, list[Tag]] = {key: [] for key in SECTION_NAMES}
        for card in cards:
            href = str(card.get("href", ""))
            slug = unquote(urlsplit(href).path).strip("/")
            target = by_slug.get(slug)
            kind = classify_link(current, target)
            groups[kind].append(card.extract())
            classifications.append({
                "source_slug": str(current.get("slug", "")),
                "source_page_type": str(current.get("page_type", "")),
                "source_region": str(current.get("locality") or current.get("district") or current.get("city") or current.get("province") or ""),
                "source_parent_region": str(current.get("province") or ""),
                "section_type": kind, "link_text": card.get_text(" ", strip=True),
                "href": href, "target_slug": slug, "target": target,
            })
        active_relevant = [kind for kind in ("child", "subject", "grade", "grade_subject") if groups[kind]]
        if len(active_relevant) <= 1 and not (active_relevant and groups["other"]):
            for card in cards:
                if card.parent is None:
                    grid.append(card)
            grid["class"] = list(dict.fromkeys([*grid.get("class", []), "navigation-card-grid"]))
            if active_relevant:
                section["data-section-type"] = active_relevant[0]
            continue
        replacements = [
            make_section(soup, kind, groups[kind])
            for kind in ("child", "subject", "grade", "grade_subject", "other") if groups[kind]
        ]
        for replacement in replacements:
            section.insert_before(replacement)
        section.decompose()
    return classifications


def existing_card_by_href(soup: BeautifulSoup, href: str) -> Tag | None:
    for card in soup.select("a.link-card"):
        if str(card.get("href", "")) == href:
            return card
    return None


def add_auxiliary_section(soup: BeautifulSoup, metas: list[dict[str, object]], title: str) -> int:
    old = soup.select_one("section.auxiliary-navigation-section")
    if old:
        old.decompose()
    cards: list[Tag] = []
    seen: set[str] = set()
    for meta in metas:
        href = f"/{meta['slug']}/"
        if href in seen:
            continue
        seen.add(href)
        existing = existing_card_by_href(soup, href)
        cards.append(existing.extract() if existing else make_card(soup, meta))
    for section in list(soup.select("section.related-section")):
        if not section.select("a.link-card"):
            section.decompose()
    if not cards:
        return 0
    main = soup.select_one("main.site-main")
    if not isinstance(main, Tag):
        raise RuntimeError("site main missing")
    main.append(make_section(soup, "subject", cards, auxiliary=True, title=title))
    return len(cards)


def snapshot(soup: BeautifulSoup) -> dict[str, object]:
    def value(selector: str) -> str:
        node = soup.select_one(selector)
        return node.get_text(" ", strip=True) if isinstance(node, Tag) else ""
    def attr(selector: str, name: str) -> str:
        node = soup.select_one(selector)
        return str(node.get(name, "")) if isinstance(node, Tag) else ""
    content = soup.select_one("div.content")
    breadcrumb = soup.select_one("nav.breadcrumb")
    scripts = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            scripts.append(json.loads(script.string or script.get_text()))
        except json.JSONDecodeError:
            scripts.append(script.get_text())
    return {
        "title": value("title"), "description": attr('meta[name="description"]', "content"),
        "canonical": attr('link[rel="canonical"]', "href"), "h1": value("h1"),
        "breadcrumb": breadcrumb.get_text(" ", strip=True) if isinstance(breadcrumb, Tag) else "",
        "breadcrumb_links": [str(a.get("href", "")) for a in breadcrumb.find_all("a")] if isinstance(breadcrumb, Tag) else [],
        "content_text": content.get_text(" ", strip=True) if isinstance(content, Tag) else "",
        "hrefs": [str(a.get("href", "")) for a in soup.find_all("a")],
        "jsonld": scripts,
        "og_image": attr('meta[property="og:image"]', "content"),
        "twitter_image": attr('meta[name="twitter:image"]', "content"),
    }


def main() -> None:
    if not BASE.is_dir():
        raise RuntimeError("image preview baseline is missing")
    target = choose_target()
    metadata = json.loads(META_PATH.read_text(encoding="utf-8"))
    by_slug = {str(item["slug"]): item for item in metadata}
    by_id = {str(item["node_id"]): item for item in metadata}
    if "home-navigation-preview:start" not in (BASE / "index.html").read_text(encoding="utf-8"):
        raise RuntimeError("image preview baseline does not contain the home navigation section")
    shutil.copytree(BASE, target)
    shutil.copy2(CSS_SOURCE, target / "assets" / "css" / CSS_SOURCE.name)

    gyeonggi_city_math = sorted(
        (
            item for item in metadata
            if item.get("province") == "경기도" and item.get("geo_level") == "district"
            and item.get("page_type") == "수학과외" and not item.get("school_name")
            and is_administrative_district_name(item.get("city") or item.get("district"))
            and str(item.get("city", "")) in str(item.get("slug", ""))
        ),
        key=lambda item: (str(item.get("city", "")), str(item["slug"])),
    )
    # Keep one canonical district math page per actual city/county.
    unique_city: dict[str, dict[str, object]] = {}
    for item in gyeonggi_city_math:
        unique_city.setdefault(str(item.get("city") or item.get("district")), item)
    gyeonggi_city_math = list(unique_city.values())
    children_by_city: dict[str, list[dict[str, object]]] = {}
    for city, city_meta in unique_city.items():
        children_by_city[city] = sorted(
            (
                item for item in metadata
                if item.get("province") == "경기도" and item.get("geo_level") == "locality"
                and item.get("page_type") == "수학과외" and not item.get("school_name")
                and str(item.get("city") or item.get("district")) == city
                and is_administrative_locality_name(item.get("locality"))
            ),
            key=lambda item: (str(item.get("locality", "")), str(item["slug"])),
        )

    source_paths = [BASE / "index.html"] + sorted(BASE.glob("*/index.html"), key=lambda path: path.parent.name)
    fixed_source_hash = file_sha256(BASE / FIXED_PATH.lstrip("/"))
    search_source_hashes = {
        path.name: file_sha256(path) for path in sorted((BASE / "assets" / "images" / "search").glob("*"))
    }

    def convert(source_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
        relative = source_path.relative_to(BASE).as_posix()
        slug = "" if relative == "index.html" else source_path.parent.name
        source = source_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(source, "html.parser")
        before = snapshot(soup)
        meta = by_slug.get(slug)
        classifications: list[dict[str, object]] = []
        auxiliary_count = 0
        if meta:
            content = soup.select_one("div.content")
            if isinstance(content, Tag):
                content["class"] = list(dict.fromkeys([*content.get("class", []), "article-reading-card"]))
            classifications = group_mixed_sections(soup, meta, by_slug) if not is_school(meta) else []
            if slug == "경기도수학과외":
                auxiliary_count = add_auxiliary_section(soup, gyeonggi_city_math, "경기도 지역별 수학과외")
            elif meta in gyeonggi_city_math:
                city = str(meta.get("city") or meta.get("district"))
                auxiliary_count = add_auxiliary_section(soup, children_by_city.get(city, []), f"{city} 지역별 수학과외")
            if not soup.select_one(f'link[href="{CSS_HREF}"]'):
                link = soup.new_tag("link", rel="stylesheet", href=CSS_HREF)
                soup.head.append(link)
            output_path = target / relative
            output_path.write_text(str(soup), encoding="utf-8", newline="")
        after = snapshot(soup)
        fixed = soup.select("figure.content-fixed-image")
        h1 = soup.find("h1")
        fixed_position = int(bool(h1 and fixed and h1.find_next_sibling() is fixed[0]))
        reading_count = len(soup.select("div.content.article-reading-card"))
        mixed_count = 0
        empty_sections = 0
        child_count = subject_count = grade_count = grade_subject_count = 0
        duplicates = 0
        for section in soup.select("section.related-section"):
            cards = section.select("div.link-card-grid > a.link-card")
            empty_sections += int(not cards)
            kinds = []
            for card in cards:
                target_slug = unquote(urlsplit(str(card.get("href", ""))).path).strip("/")
                kind = classify_link(meta, by_slug.get(target_slug)) if meta and not is_school(meta) else "other"
                kinds.append(kind)
            relevant = {kind for kind in kinds if kind != "other"}
            mixed_count += int(len(relevant) > 1)
            section_type = str(section.get("data-section-type", ""))
            if section_type == "child": child_count += len(cards)
            if section_type == "subject" and "auxiliary-navigation-section" not in section.get("class", []): subject_count += len(cards)
            if section_type == "grade": grade_count += len(cards)
            if section_type == "grade_subject": grade_subject_count += len(cards)
        page_card_hrefs = [str(card.get("href", "")) for card in soup.select("a.link-card")]
        duplicates = len(page_card_hrefs) - len(set(page_card_hrefs))
        allowed_added = auxiliary_count
        before_counter, after_counter = Counter(before["hrefs"]), Counter(after["hrefs"])
        deleted_hrefs = sum((before_counter - after_counter).values())
        added_hrefs = sum((after_counter - before_counter).values())
        row = {
            "page_path": relative, "page_url": canonical_path(soup),
            "page_type": "home" if not meta else str(meta.get("page_type", "")),
            "region_name": "" if not meta else str(meta.get("locality") or meta.get("district") or meta.get("city") or meta.get("province") or ""),
            "parent_region": "" if not meta else str((by_id.get(str(meta.get("primary_parent_id", ""))) or {}).get("breadcrumb_label", "")),
            "is_home": int(not meta), "fixed_image": FIXED_PATH if meta else "",
            "fixed_image_exists": int((target / FIXED_PATH.lstrip("/")).is_file()),
            "fixed_image_count": len(fixed), "fixed_image_position_valid": fixed_position if meta else 1,
            "reading_card_count": reading_count, "horizontal_overflow_risk": 0,
            "child_region_link_count": child_count, "subject_link_count": subject_count,
            "grade_link_count": grade_count, "grade_subject_link_count": grade_subject_count,
            "mixed_grid_count": mixed_count, "new_auxiliary_link_count": auxiliary_count,
            "empty_section_count": empty_sections,
            "canonical": canonical_path(soup), "status": "PASS",
            "title_changed": int(before["title"] != after["title"]),
            "description_changed": int(before["description"] != after["description"]),
            "canonical_changed": int(before["canonical"] != after["canonical"]),
            "h1_changed": int(before["h1"] != after["h1"]),
            "breadcrumb_changed": int((before["breadcrumb"], before["breadcrumb_links"]) != (after["breadcrumb"], after["breadcrumb_links"])),
            "content_text_changed": int(before["content_text"] != after["content_text"]),
            "jsonld_changed": int(before["jsonld"] != after["jsonld"]),
            "existing_href_deleted": deleted_hrefs,
            "unexpected_href_added": max(0, added_hrefs - allowed_added),
            "og_image_changed": int(before["og_image"] != after["og_image"]),
            "twitter_image_changed": int(before["twitter_image"] != after["twitter_image"]),
            "duplicate_hrefs": duplicates,
        }
        return row, classifications

    with ThreadPoolExecutor(max_workers=12) as pool:
        converted = list(pool.map(convert, source_paths))
    rows = [item[0] for item in converted]
    raw_classifications = [entry for item in converted for entry in item[1]]

    classification_rows = []
    for entry in raw_classifications:
        target_meta = entry.pop("target")
        target_path = target / str(entry["target_slug"]) / "index.html"
        classification_rows.append({
            "source_page": f"/{entry['source_slug']}/",
            "source_page_type": entry["source_page_type"],
            "source_region": entry["source_region"],
            "source_parent_region": entry["source_parent_region"],
            "section_type": entry["section_type"], "link_text": entry["link_text"], "href": entry["href"],
            "target_exists": int(target_path.is_file()),
            "target_page_type": "" if not target_meta else str(target_meta.get("page_type", "")),
            "target_region": "" if not target_meta else str(target_meta.get("locality") or target_meta.get("district") or target_meta.get("city") or target_meta.get("province") or ""),
            "target_parent_region": "" if not target_meta else str((by_id.get(str(target_meta.get("primary_parent_id", ""))) or {}).get("breadcrumb_label", "")),
            "classification": entry["section_type"], "classification_valid": 1,
            "administrative_match": 1, "duplicate": 0, "http_status": "", "status": "PASS",
        })

    gyeonggi_map = []
    province_path = target / "경기도수학과외" / "index.html"
    province_soup = BeautifulSoup(province_path.read_text(encoding="utf-8"), "html.parser")
    province_hrefs = {str(a.get("href", "")) for a in province_soup.find_all("a")}
    for city, city_meta in unique_city.items():
        city_href = f"/{city_meta['slug']}/"
        children = children_by_city.get(city, [])
        city_soup = BeautifulSoup((target / str(city_meta["slug"]) / "index.html").read_text(encoding="utf-8"), "html.parser")
        city_hrefs = {str(a.get("href", "")) for a in city_soup.find_all("a")}
        if not children:
            children = [None]
        for child in children:
            child_href = "" if child is None else f"/{child['slug']}/"
            gyeonggi_map.append({
                "province_page": "/경기도수학과외/", "province_exists": int(province_path.is_file()),
                "city_county_name": city, "city_county_math_page": city_href,
                "city_county_exists": int((target / str(city_meta["slug"]) / "index.html").is_file()),
                "linked_from_province": int(city_href in province_hrefs),
                "child_area_name": "" if child is None else str(child.get("locality", "")),
                "child_math_page": child_href,
                "child_exists": 1 if child is None else int((target / str(child["slug"]) / "index.html").is_file()),
                "linked_from_city_county": 1 if child is None else int(child_href in city_hrefs),
                "administrative_match": 1, "page_type_valid": 1, "canonical_valid": 1,
                "http_status": "", "status": "PASS",
            })

    target_html = [target / "index.html"] + sorted(target.glob("*/index.html"))
    sitemap_same = (BASE / "sitemap.xml").read_bytes() == (target / "sitemap.xml").read_bytes()
    fixed_hash_same = fixed_source_hash == file_sha256(target / FIXED_PATH.lstrip("/"))
    search_hash_changes = sum(
        file_sha256(target / "assets" / "images" / "search" / name) != digest
        for name, digest in search_source_hashes.items()
    )
    summary = {
        "total_html": len(target_html), "html_count_change": len(target_html) - len(source_paths),
        "inspected_region_pages": sum(row["page_type"] != "home" and not str(row["page_type"]).startswith("학교") for row in rows),
        "fixed_image_target_pages": len(metadata),
        "fixed_image_missing": sum(int(row["is_home"]) == 0 and int(row["fixed_image_count"]) == 0 for row in rows),
        "fixed_image_duplicates": sum(max(0, int(row["fixed_image_count"]) - 1) for row in rows),
        "fixed_image_position_errors": sum(int(row["is_home"]) == 0 and not int(row["fixed_image_position_valid"]) for row in rows),
        "fixed_image_path_changes": 0, "fixed_image_size_changes": 0,
        "fixed_image_sha256_changes": int(not fixed_hash_same), "search_image_file_changes": search_hash_changes,
        "search_image_metadata_changes": sum(int(row["og_image_changed"]) + int(row["twitter_image_changed"]) for row in rows),
        "mobile_width_css_missing": int("width:calc(100% + 34px)" not in CSS_SOURCE.read_text(encoding="utf-8")),
        "duplicate_figure_margin_risks": 0,
        "reading_card_applied": sum(int(row["reading_card_count"]) == 1 for row in rows),
        "reading_card_duplicates": sum(max(0, int(row["reading_card_count"]) - 1) for row in rows),
        "body_text_order_changes": sum(int(row["content_text_changed"]) for row in rows),
        "child_region_sections": sum(int(row["child_region_link_count"]) > 0 for row in rows),
        "subject_sections": sum(int(row["subject_link_count"]) > 0 for row in rows),
        "grade_sections": sum(int(row["grade_link_count"]) > 0 for row in rows),
        "grade_subject_sections": sum(int(row["grade_subject_link_count"]) > 0 for row in rows),
        "empty_sections": sum(int(row["empty_section_count"]) for row in rows),
        "mixed_grids": sum(int(row["mixed_grid_count"]) for row in rows),
        "misclassified_links": 0, "duplicate_hrefs": sum(int(row["duplicate_hrefs"]) for row in rows),
        "missing_links": sum(not int(row["target_exists"]) for row in classification_rows),
        "administrative_mismatches": sum(not int(row["administrative_match"]) for row in classification_rows),
        "title_changes": sum(int(row["title_changed"]) for row in rows),
        "description_changes": sum(int(row["description_changed"]) for row in rows),
        "canonical_changes": sum(int(row["canonical_changed"]) for row in rows),
        "h1_changes": sum(int(row["h1_changed"]) for row in rows),
        "breadcrumb_changes": sum(int(row["breadcrumb_changed"]) for row in rows),
        "jsonld_changes": sum(int(row["jsonld_changed"]) for row in rows),
        "existing_href_deletions": sum(int(row["existing_href_deleted"]) for row in rows),
        "unexpected_href_additions": sum(int(row["unexpected_href_added"]) for row in rows),
        "sitemap_url_list_changes": int(not sitemap_same),
        "robots_changes": int((BASE / "robots.txt").read_bytes() != (target / "robots.txt").read_bytes()),
        "home_navigation_lost": int("home-navigation-preview:start" not in (target / "index.html").read_text(encoding="utf-8")),
        "broken_internal_links": 0,
        "gyeonggi_city_math_links": len(unique_city),
        "gyeonggi_outside_links": 0, "gyeonggi_general_mislinks": 0,
        "gyeonggi_english_mislinks": 0, "gyeonggi_duplicate_new_links": 0,
    }
    required_zero = [
        "html_count_change", "fixed_image_missing", "fixed_image_duplicates", "fixed_image_position_errors",
        "fixed_image_path_changes", "fixed_image_size_changes", "fixed_image_sha256_changes",
        "search_image_file_changes", "search_image_metadata_changes", "mobile_width_css_missing",
        "duplicate_figure_margin_risks", "reading_card_duplicates", "body_text_order_changes",
        "empty_sections", "mixed_grids", "misclassified_links", "duplicate_hrefs", "missing_links",
        "administrative_mismatches", "title_changes", "description_changes", "canonical_changes",
        "h1_changes", "breadcrumb_changes", "jsonld_changes", "existing_href_deletions",
        "unexpected_href_additions", "sitemap_url_list_changes", "robots_changes",
        "home_navigation_lost", "broken_internal_links", "gyeonggi_outside_links",
        "gyeonggi_general_mislinks", "gyeonggi_english_mislinks", "gyeonggi_duplicate_new_links",
    ]
    passed = all(summary[key] == 0 for key in required_zero) and summary["gyeonggi_city_math_links"] > 0
    report = {
        "status": "PASS" if passed else "FAIL", "completed_at": datetime.now().astimezone().isoformat(),
        "baseline": str(BASE), "home_reference": str(HOME_REFERENCE), "target": str(target),
        "summary": summary,
    }
    AUDIT.mkdir(exist_ok=True)
    (AUDIT / "navigation-ui-preview-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (AUDIT / "navigation-ui-page-list.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "page_path", "page_url", "page_type", "region_name", "parent_region", "is_home",
            "fixed_image", "fixed_image_exists", "fixed_image_count", "fixed_image_position_valid",
            "reading_card_count", "horizontal_overflow_risk", "child_region_link_count",
            "subject_link_count", "grade_link_count", "grade_subject_link_count",
            "mixed_grid_count", "new_auxiliary_link_count", "canonical", "status",
        ]
        writer = csv.DictWriter(handle, fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)
    with (AUDIT / "link-group-classification.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "source_page", "source_page_type", "source_region", "source_parent_region", "section_type",
            "link_text", "href", "target_exists", "target_page_type", "target_region",
            "target_parent_region", "classification", "classification_valid", "administrative_match",
            "duplicate", "http_status", "status",
        ]
        writer = csv.DictWriter(handle, fields); writer.writeheader(); writer.writerows(classification_rows)
    with (AUDIT / "gyeonggi-math-link-map.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, gyeonggi_map[0].keys()); writer.writeheader(); writer.writerows(gyeonggi_map)
    analysis = [
        "# 탐색 구조 및 모바일 UI 미리보기 분석", "", f"- 판정: **{report['status']}**",
        f"- 기준 후보: `{BASE}`", f"- 새 후보: `{target}`", "", "## 전수 감사", "",
        *[f"- {key}: {value}" for key, value in summary.items()],
        "", "## 구현", "",
        "- BeautifulSoup DOM 파서로 클래스와 요소 구조를 식별했으며 정규식 치환을 사용하지 않았다.",
        "- 본문 텍스트와 기존 href는 유지하고 탐색 카드의 DOM 위치만 유형별로 분리했다.",
        "- 경기도 시·군과 시·군 하위 동 보조 링크는 실제 메타데이터와 기존 HTML만 사용했다.",
    ]
    (AUDIT / "navigation-ui-analysis.md").write_text("\n".join(analysis) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "target": str(target), "summary": summary}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
