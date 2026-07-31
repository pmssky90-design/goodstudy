from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from config import SITE_URL
from sitegen.models import Page
from sitegen.title_rules import fix_title, link_label, normalize_text

REGION_SHEETS = ("과외", "수학과외", "영어과외", "초등과외", "중등과외", "고등과외",
                 "초등수학과외", "중등수학과외", "고등수학과외",
                 "초등영어과외", "중등영어과외", "고등영어과외")


def _id(prefix: str, *parts: str) -> str:
    return prefix + "-" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _geo(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    province = normalize_text(row.get("시도"))
    city = normalize_text(row.get("시군구"))
    locality = normalize_text(row.get("읍면동"))
    village = normalize_text(row.get("리"))
    level = "village" if village else "locality" if locality else "district" if city else "province"
    return province, city, locality, village, level


def normalize_pages(sheets: dict[str, list[dict[str, Any]]]) -> tuple[list[Page], dict[str, int]]:
    pages: list[Page] = []
    stats = {"original_equal_title_slug": 0, "titles_fixed": 0}
    for sheet in REGION_SHEETS:
        for row in sheets.get(sheet, []):
            slug = normalize_text(row.get("생성슬러그"))
            raw_title = normalize_text(row.get("제목(작성용)"))
            body = normalize_text(row.get("본문(작성용)"))
            province, city, locality, village, level = _geo(row)
            name = normalize_text(row.get("지역명")) or village or locality or city or province
            title, fixed = fix_title(raw_title, slug, sheet)
            stats["original_equal_title_slug"] += int(raw_title == slug and bool(slug))
            stats["titles_fixed"] += int(fixed)
            node_type = "geo_" + level if sheet == "과외" else ("topic_combination" if "수학" in sheet or "영어" in sheet else "topic_grade")
            pages.append(Page(
                node_id=_id("region", province, city, locality, village, sheet),
                node_type=node_type, geo_level=level, province=province, city=city, district=city,
                locality=locality, village=village, page_type=sheet, slug=slug, original_slug=slug,
                title=title, link_label=link_label(name, sheet), breadcrumb_label=name,
                body_html=body, source_sheet=sheet, source_row=int(row["_source_row"]),
            ))

    school_rows = sheets.get("고등학교", [])
    content_map = {
        "학교과외": sheets.get("고등학교 과외", []),
        "학교수학과외": sheets.get("고등학교 수학과외", []),
        "학교영어과외": sheets.get("고등학교 영어과외", []),
    }
    for index, school in enumerate(school_rows):
        school_name = normalize_text(school.get("학교표시명") or school.get("학교명"))
        province = normalize_text(school.get("시도"))
        city = normalize_text(school.get("시군구"))
        locality = normalize_text(school.get("공식주소동읍") or school.get("연결동읍"))
        address = normalize_text(school.get("학교주소"))
        for page_type, content_rows in content_map.items():
            if index >= len(content_rows):
                continue
            content = content_rows[index]
            slug_column = {"학교과외": "학교과외슬러그", "학교수학과외": "학교수학과외슬러그", "학교영어과외": "학교영어과외슬러그"}[page_type]
            slug = normalize_text(school.get(slug_column))
            title = normalize_text(content.get("제목(작성용)"))
            body = normalize_text(content.get("본문(작성용)"))
            title, fixed = fix_title(title, slug, page_type)
            stats["original_equal_title_slug"] += int(normalize_text(content.get("제목(작성용)")) == slug)
            stats["titles_fixed"] += int(fixed)
            pages.append(Page(
                node_id=_id("school", school_name, address, page_type), node_type="school_general" if page_type == "학교과외" else "school_subject",
                geo_level="school", province=province, city=city, district=city, locality=locality, village="",
                page_type=page_type, slug=slug, original_slug=slug, title=title,
                link_label=link_label(school_name, page_type, True), breadcrumb_label=school_name,
                body_html=body, source_sheet={"학교과외": "고등학교 과외", "학교수학과외": "고등학교 수학과외", "학교영어과외": "고등학교 영어과외"}[page_type],
                source_row=int(content["_source_row"]), school_name=school_name, school_address=address,
            ))
    return pages, stats
