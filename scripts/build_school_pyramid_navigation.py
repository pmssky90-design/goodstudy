from __future__ import annotations

import csv
import html
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from build_home_region_school_only import (
    EXCEL, META, PROVINCES, balanced_section, load_excel, match_site, norm,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_home_region_school_only_rebuild"
TARGET_BASE = ROOT / "candidate_output_school_pyramid_navigation"
CHECKPOINT = ROOT / "intermediate" / "school-pyramid-navigation-build.json"
MATCH_CSV = ROOT / "audit" / "school-pyramid-excel-match.csv"
UNMATCHED_CSV = ROOT / "audit" / "school-pyramid-unmatched.csv"
DUPLICATE_CSV = ROOT / "audit" / "school-pyramid-duplicate-schools.csv"
REGION_CSV = ROOT / "audit" / "school-pyramid-region-summary.csv"


def target_path() -> Path:
    if not TARGET_BASE.exists() or not any(TARGET_BASE.iterdir()):
        return TARGET_BASE
    index = 2
    while True:
        candidate = TARGET_BASE.with_name(f"{TARGET_BASE.name}_{index}")
        if not candidate.exists() or not any(candidate.iterdir()):
            return candidate
        index += 1


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def insert_before_main_end(source: str, block: str) -> str:
    location = source.rfind("</main>")
    if location < 0:
        raise RuntimeError("missing </main>")
    return source[:location] + block + source[location:]


def navigation_heading(title: str, description: str) -> str:
    return (
        '<div class="section-heading">'
        f'<h2>{html.escape(title)}</h2><p>{html.escape(description)}</p></div>'
    )


def upper_links(province: dict[str, object] | None = None) -> str:
    links = ['<a href="/">홈으로 이동</a>', '<a href="/#schools">전국 지역 보기</a>']
    if province:
        links.insert(0, f'<a href="/{html.escape(str(province["slug"]), quote=True)}/">'
                        f'{html.escape(str(province["province"]))}로 돌아가기</a>')
    return '<nav class="region-school-links" aria-label="상위 학교 탐색">' + "".join(links) + "</nav>"


def province_home_section(province_pages: dict[str, dict[str, object]]) -> str:
    cards = []
    for province, _ in PROVINCES:
        page = province_pages[province]
        cards.append(
            f'<a class="link-card" href="/{html.escape(str(page["slug"]), quote=True)}/">'
            '<span class="link-card-label">시도</span>'
            f'<strong>{html.escape(province)}</strong><span>시군구별 학교 살펴보기</span></a>'
        )
    return (
        '<section class="home-explore-section school-explore" id="schools" aria-labelledby="school-explore-title">'
        '<div class="home-explore-heading"><div><p class="home-explore-kicker">학교 탐색</p>'
        '<h2 id="school-explore-title">지역별 학교 찾기</h2></div>'
        '<p>시도를 선택한 뒤 시군구별 학교를 단계적으로 살펴보세요.</p></div>'
        f'<div class="link-card-grid">{"".join(cards)}</div></section>'
    )


def province_section(
    province: str, districts: list[str], district_pages: dict[tuple[str, str], dict[str, object]],
) -> str:
    cards = "".join(
        f'<a class="link-card" href="/{html.escape(str(district_pages[(province, district)]["slug"]), quote=True)}/">'
        '<span class="link-card-label">시군구</span>'
        f'<strong>{html.escape(district)}</strong><span>학교 목록 보기</span></a>'
        for district in districts
    )
    return (
        '<section class="related-section school-pyramid-navigation" data-school-level="province">'
        f'{navigation_heading(f"{province} 시군구별 학교", "학교가 있는 시군구만 표시합니다.")}'
        f'{upper_links()}<div class="link-card-grid">{cards}</div></section>'
    )


def district_section(
    province: str, district: str, schools: list[dict[str, object]], province_page: dict[str, object],
) -> str:
    cards = []
    for match in schools:
        excel, site = match["excel"], match["site"]
        cards.append(
            f'<a class="school-card" href="/{html.escape(str(site["slug"]), quote=True)}/">'
            f'<strong class="school-name">{html.escape(excel["학교명"])}</strong>'
            f'<span class="school-location">{html.escape(excel["_level"])} · {html.escape(district)}</span>'
            '<small>학교별 과외 정보 보기</small></a>'
        )
    return (
        '<section class="related-section school-pyramid-navigation" data-school-level="district">'
        f'{navigation_heading(f"{district} 학교", f"{district}에 있는 학교별 과외 정보를 살펴보세요.")}'
        f'{upper_links(province_page)}<div class="school-explore-grid">{"".join(cards)}</div></section>'
    )


def main() -> None:
    target = target_path()
    metadata = json.loads(META.read_text(encoding="utf-8"))
    excel_rows = load_excel()
    matches, unmatched = match_site(excel_rows, metadata)
    if unmatched or len(matches) != 1328:
        raise RuntimeError(f"school matching incomplete: matches={len(matches)} unmatched={len(unmatched)}")

    general_regions = [
        x for x in metadata
        if not x.get("school_name") and x.get("page_type") == "과외"
    ]
    province_pages = {
        str(x["province"]): x for x in general_regions if x.get("geo_level") == "province"
    }
    district_index: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for item in general_regions:
        if item.get("geo_level") == "district":
            district_index[(str(item["province"]), str(item["city"]))].append(item)

    schools_by_region: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for match in matches:
        schools_by_region[(match["excel"]["_province"], match["excel"]["_district"])].append(match)
    district_pages = {}
    mapping_errors = []
    for key in schools_by_region:
        pages = district_index.get(key, [])
        if len(pages) != 1:
            mapping_errors.append({"province": key[0], "district": key[1], "page_matches": len(pages)})
        else:
            district_pages[key] = pages[0]
    if len(province_pages) != 17 or mapping_errors:
        raise RuntimeError({"province_pages": len(province_pages), "mapping_errors": mapping_errors})

    shutil.copytree(SOURCE, target)
    source_home = (SOURCE / "index.html").read_text(encoding="utf-8")
    start, end, _ = balanced_section(source_home, '<section class="home-explore-section school-explore"')
    home = source_home[:start] + province_home_section(province_pages) + source_home[end:]
    (target / "index.html").write_text(home, encoding="utf-8", newline="")

    changed_region_slugs = []
    for province, _ in PROVINCES:
        page = province_pages[province]
        districts = sorted(district for p, district in schools_by_region if p == province)
        path = target / str(page["slug"]) / "index.html"
        source = path.read_text(encoding="utf-8")
        output = insert_before_main_end(source, province_section(province, districts, district_pages))
        path.write_text(output, encoding="utf-8", newline="")
        changed_region_slugs.append(str(page["slug"]))

    for (province, district), schools in sorted(schools_by_region.items()):
        page = district_pages[(province, district)]
        schools = sorted(
            schools, key=lambda x: (x["excel"]["학교명"], x["excel"]["주소"], x["site"]["slug"])
        )
        path = target / str(page["slug"]) / "index.html"
        source = path.read_text(encoding="utf-8")
        output = insert_before_main_end(
            source, district_section(province, district, schools, province_pages[province])
        )
        path.write_text(output, encoding="utf-8", newline="")
        changed_region_slugs.append(str(page["slug"]))

    match_rows = []
    for match in matches:
        row, site = match["excel"], match["site"]
        match_rows.append({
            "excel_row": row["_row"], "school_code": row.get("학교코드 (KEDI)", ""),
            "school_name": row["학교명"], "normalized_school_name": norm(row["학교명"]),
            "sido": row["_province"], "sigungu": row["_district"], "school_level": row["_level"],
            "excel_address": row["주소"], "site_school_name": site["school_name"],
            "site_slug": site["slug"], "site_href": f'/{site["slug"]}/',
            "match_type": match["match_type"], "duplicate_match_count": 1,
        })
    write_csv(MATCH_CSV, match_rows, list(match_rows[0]))
    write_csv(
        UNMATCHED_CSV, unmatched,
        ["site_school_name", "site_province", "site_sigungu", "site_address",
         "site_slug", "candidate_count", "reason"],
    )
    name_counts = Counter(norm(row["학교명"]) for row in excel_rows)
    duplicate_rows = [
        {
            "normalized_school_name": norm(row["학교명"]), "school_name": row["학교명"],
            "sido": row["_province"], "sigungu": row["_district"], "address": row["주소"],
            "school_code": row.get("학교코드 (KEDI)", ""), "same_name_count": name_counts[norm(row["학교명"])],
        }
        for row in excel_rows if name_counts[norm(row["학교명"])] > 1
    ]
    write_csv(
        DUPLICATE_CSV, duplicate_rows,
        ["normalized_school_name", "school_name", "sido", "sigungu", "address",
         "school_code", "same_name_count"],
    )
    region_rows = []
    for province, code in PROVINCES:
        for district in sorted(district for p, district in schools_by_region if p == province):
            page = district_pages[(province, district)]
            region_rows.append({
                "sido": province, "sido_code": code, "sido_slug": province_pages[province]["slug"],
                "sigungu": district, "sigungu_slug": page["slug"],
                "school_count": len(schools_by_region[(province, district)]),
                "sido_href": f'/{province_pages[province]["slug"]}/',
                "sigungu_href": f'/{page["slug"]}/',
            })
    write_csv(
        REGION_CSV, region_rows,
        ["sido", "sido_code", "sido_slug", "sigungu", "sigungu_slug",
         "school_count", "sido_href", "sigungu_href"],
    )
    checkpoint = {
        "status": "complete", "source": str(SOURCE), "target": str(target),
        "excel": str(EXCEL), "sheet": "학교별 주요통계", "header_row": 17,
        "excel_rows": len(excel_rows),
        "excel_unique_schools": len({(x["_province"], x["_district"], norm(x["학교명"])) for x in excel_rows}),
        "site_unique_schools": len(matches), "matches": len(matches), "unmatched": len(unmatched),
        "exact_matches": sum(x["match_type"] != "address_corrected" for x in matches),
        "corrected_matches": sum(x["match_type"] == "address_corrected" for x in matches),
        "province_pages_used": len(province_pages), "district_pages_used": len(district_pages),
        "school_cards": len(matches), "changed_html_expected": 1 + len(province_pages) + len(district_pages),
        "changed_region_slugs": changed_region_slugs,
    }
    CHECKPOINT.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(checkpoint, ensure_ascii=False))


if __name__ == "__main__":
    main()
