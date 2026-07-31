from __future__ import annotations

import csv
import html
import json
import os
import re
import shutil
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_navigation_linkfix"
TARGET = ROOT / "candidate_output_school_excel_linkfix"
META = ROOT / "intermediate" / "normalized-pages.json"
EXCEL = next((ROOT / "data").glob("*.xlsx"))
MATCH_LOG = ROOT / "audit" / "school-excel-match-log.csv"
UNMATCHED = ROOT / "audit" / "school-excel-unmatched.csv"
RESTORE_LOG = ROOT / "audit" / "region-subject-link-restore.csv"
CHECKPOINT = ROOT / "intermediate" / "school-excel-linkfix-build-checkpoint.json"

RELATED = re.compile(r'<section class="related-section">.*?</section>', re.I | re.S)
GRID = re.compile(r'(<div class="link-card-grid">)(.*?)(</div>)', re.I | re.S)
CARD = re.compile(r'<a class="link-card"[^>]*>.*?</a>', re.I | re.S)
H2 = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")
FALLBACK_CARD = (
    '<a class="link-card" data-subject="general" href="/">'
    '<span class="link-card-label">일반</span><strong>지역 과외</strong>'
    '<span>학습 전반과 일정 관리</span></a>'
)
PROVINCE_IDS = {
    "강원특별자치도": "gangwon", "경기도": "gyeonggi", "경상남도": "gyeongnam",
    "경상북도": "gyeongbuk", "광주광역시": "gwangju", "대구광역시": "daegu",
    "대전광역시": "daejeon", "부산광역시": "busan", "서울특별시": "seoul",
    "세종특별자치시": "sejong", "울산광역시": "ulsan", "인천광역시": "incheon",
    "전라남도": "jeonnam", "전북특별자치도": "jeonbuk", "제주특별자치도": "jeju",
    "충청남도": "chungnam", "충청북도": "chungbuk",
}


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value: object) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", clean(value).lower()).replace("고등학교", "고")


def subject_grade(item: dict[str, object]) -> tuple[str, str]:
    page_type = str(item.get("page_type", ""))
    subject = "math" if "수학" in page_type else ("english" if "영어" in page_type else "general")
    grade = "elementary" if "초등" in page_type else ("middle" if "중등" in page_type else ("high" if "고등" in page_type else "general"))
    return subject, grade


def location_key(item: dict[str, object]) -> tuple[str, str, str, str, str]:
    return (
        str(item.get("geo_level", "")), str(item.get("province", "")), str(item.get("city", "")),
        str(item.get("district", "")), str(item.get("locality", "")),
    )


def visible_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", value))).strip()


def href_from_card(value: str) -> str:
    match = re.search(r'href="([^"]*)"', value, re.I)
    return html.unescape(match.group(1)) if match else ""


def label_from_card(value: str) -> str:
    match = re.search(r"<strong\b[^>]*>(.*?)</strong>", value, re.I | re.S)
    return visible_text(match.group(1)) if match else ""


def rewrite_card(template: str, target: dict[str, object], subject: str) -> str:
    label = str(target.get("link_label") or target.get("breadcrumb_label") or target["slug"])
    value = re.sub(r'href="[^"]*"', f'href="/{html.escape(str(target["slug"]), quote=True)}/"', template, count=1, flags=re.I)
    value = re.sub(r'data-subject="[^"]*"', f'data-subject="{subject}"', value, count=1, flags=re.I)
    value = re.sub(
        r"(<strong\b[^>]*>).*?(</strong>)",
        lambda m: m.group(1) + html.escape(label) + m.group(2),
        value, count=1, flags=re.I | re.S,
    )
    badge = {"general": "일반", "math": "수학", "english": "영어"}[subject]
    value = re.sub(
        r"(<span class=\"link-card-label\">).*?(</span>)",
        lambda m: m.group(1) + badge + m.group(2),
        value, count=1, flags=re.I | re.S,
    )
    return value


def restore_subject_section(
    source: str,
    item: dict[str, object],
    by_location: dict[tuple[tuple[str, str, str, str, str], str, str], dict[str, object]],
) -> tuple[str, list[dict[str, str]]]:
    current_subject, grade = subject_grade(item)
    targets = [
        by_location.get((location_key(item), subject, grade))
        for subject in ("general", "math", "english")
    ]
    targets = [target for target in targets if target and (SOURCE / str(target["slug"]) / "index.html").is_file()]
    sections = list(RELATED.finditer(source))
    subject_match = next(
        (match for match in sections if H2.search(match.group(0)) and visible_text(H2.search(match.group(0)).group(1)) == "현재 지역의 과목별 학습"),
        None,
    )
    old_cards = CARD.findall(subject_match.group(0)) if subject_match else []
    template = old_cards[0] if old_cards else next(iter(CARD.findall(source)), FALLBACK_CARD)
    if not template or len(targets) != 3:
        raise RuntimeError(f"same-location subject pages/template missing: {item['slug']} targets={len(targets)}")
    new_cards = [rewrite_card(template, target, subject_grade(target)[0]) for target in targets]
    logs = []
    for index in range(max(len(old_cards), len(new_cards))):
        old = old_cards[index] if index < len(old_cards) else ""
        new = new_cards[index] if index < len(new_cards) else ""
        target = targets[index] if index < len(targets) else None
        logs.append({
            "source_page": f"/{item['slug']}/", "page_subject": current_subject, "page_grade": grade,
            "old_label": label_from_card(old), "old_href": href_from_card(old),
            "new_label": label_from_card(new), "new_href": href_from_card(new),
            "target_subject": subject_grade(target)[0] if target else "",
            "target_grade": subject_grade(target)[1] if target else "",
            "action": "restore_same_location_subject_links",
        })
    if subject_match:
        block = GRID.sub(lambda m: m.group(1) + "".join(new_cards) + m.group(3), subject_match.group(0), count=1)
        output = source[:subject_match.start()] + block + source[subject_match.end():]
    else:
        block = (
            '<section class="related-section"><div class="section-heading"><h2>현재 지역의 과목별 학습</h2>'
            '<p>일반·수학·영어 학습을 구분해 살펴보세요.</p></div>'
            f'<div class="link-card-grid">{"".join(new_cards)}</div></section>'
        )
        insertion = sections[0].start() if sections else source.rfind("</main>")
        if insertion < 0:
            raise RuntimeError(f"main closing tag missing: {item['slug']}")
        output = source[:insertion] + block + source[insertion:]
    return output, logs


def read_excel() -> list[dict[str, str]]:
    workbook = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)
    sheet = workbook["고등학교"]
    iterator = sheet.iter_rows(values_only=True)
    headers = [clean(value) for value in next(iterator)]
    rows = []
    for values in iterator:
        row = {headers[index]: clean(value) for index, value in enumerate(values) if index < len(headers) and headers[index]}
        if row.get("학교명"):
            rows.append(row)
    return rows


def match_excel(
    excel_rows: list[dict[str, str]], by_slug: dict[str, dict[str, object]]
) -> tuple[list[dict[str, object]], list[dict[str, str]], list[dict[str, str]]]:
    matches, logs, unmatched = [], [], []
    for row in excel_rows:
        slugs = {
            "general": row.get("학교과외슬러그", ""),
            "math": row.get("학교수학과외슬러그", ""),
            "english": row.get("학교영어과외슬러그", ""),
        }
        items = {key: by_slug.get(slug) for key, slug in slugs.items()}
        candidates = [item for item in items.values() if item]
        reason = ""
        status = "unmatched"
        if len(candidates) == 3:
            names = {norm(item.get("school_name")) for item in candidates}
            provinces = {clean(item.get("province")) for item in candidates}
            cities = {clean(item.get("city") or item.get("district")) for item in candidates}
            addresses = {clean(item.get("school_address")) for item in candidates}
            excel_names = {norm(row.get("학교명")), norm(row.get("학교표시명")), norm(row.get("학교고유명"))}
            excel_names.discard("")
            if len(names) == 1 and next(iter(names)) in excel_names:
                status, reason = "exact", "정규화 학교명 완전 일치"
            elif len(provinces) == 1 and row.get("시도") in provinces and any(name in excel_names for name in names):
                status, reason = "region_corrected", "학교명 + 시도 일치"
            elif len(cities) == 1 and row.get("시군구") in cities and any(name in excel_names for name in names):
                status, reason = "region_corrected", "학교명 + 시군구 일치"
            elif len(addresses) == 1 and row.get("학교주소") in addresses and any(name in excel_names for name in names):
                status, reason = "region_corrected", "학교명 + 주소 일치"
            if status != "unmatched" and (
                len(provinces) != 1 or row.get("시도") not in provinces
                or len(cities) != 1 or row.get("시군구") not in cities
                or len(addresses) != 1 or row.get("학교주소") not in addresses
            ):
                status, reason = "unmatched", "동명이교 또는 주소·지역 불일치"
        else:
            reason = "사이트 일반·수학·영어 페이지 일부 누락"
        log = {
            "excel_school_name": row.get("학교명", ""), "display_name": row.get("학교표시명", ""),
            "province": row.get("시도", ""), "district": row.get("시군구", ""),
            "address": row.get("학교주소", ""), "general_slug": slugs["general"],
            "math_slug": slugs["math"], "english_slug": slugs["english"],
            "match_status": status, "match_reason": reason,
        }
        logs.append(log)
        if status == "unmatched":
            unmatched.append(log)
        else:
            matches.append({"excel": row, "items": items, "match_status": status})
    return matches, logs, unmatched


def select_representatives(matches: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, dict[str, deque[dict[str, object]]]] = defaultdict(lambda: defaultdict(deque))
    for match in sorted(matches, key=lambda x: (x["excel"]["시도"], x["excel"]["시군구"], x["excel"]["학교표시명"])):
        grouped[str(match["excel"]["시도"])][str(match["excel"]["시군구"])].append(match)
    selected = {}
    for province in PROVINCE_IDS:
        districts = grouped.get(province, {})
        chosen = []
        queues = [districts[key] for key in sorted(districts)]
        while queues and len(chosen) < 12:
            next_queues = []
            for queue in queues:
                if queue and len(chosen) < 12:
                    chosen.append(queue.popleft())
                if queue:
                    next_queues.append(queue)
            queues = next_queues
        selected[province] = chosen
    return selected


def school_card(match: dict[str, object]) -> str:
    row = match["excel"]
    links = []
    for key, label in (("general", "일반"), ("math", "수학"), ("english", "영어")):
        item = match["items"].get(key)
        if item and (SOURCE / str(item["slug"]) / "index.html").is_file():
            links.append(f'<a href="/{html.escape(str(item["slug"]), quote=True)}/">{label}</a>')
    location = " ".join(dict.fromkeys(x for x in (row.get("시군구", ""), row.get("공식주소동읍", "")) if x))
    name = row.get("학교표시명") or row.get("학교명")
    return (
        '<article class="school-card">'
        f'<strong class="school-name">{html.escape(name)}</strong>'
        f'<span class="school-location">{html.escape(location or row.get("학교주소", ""))}</span>'
        f'<div class="school-card-links" aria-label="{html.escape(name)} 과목별 과외">{"".join(links)}</div>'
        '</article>'
    )


def rewrite_home(source: str, selected: dict[str, list[dict[str, object]]]) -> str:
    start = source.index('<section class="home-explore-section school-explore"')
    end = source.index("</section>", start) + len("</section>")
    section = source[start:end]
    grid_start = section.index('<div class="school-explore-grid">')
    nav_start = section.index('<div class="region-school-navigation">')
    prefix = section[:grid_start]
    suffix = section[nav_start:]
    groups = []
    for province, code in PROVINCE_IDS.items():
        cards = "".join(school_card(match) for match in selected.get(province, []))
        groups.append(
            f'<section class="region-school-navigation" id="schools-{code}">'
            f'<h3>{html.escape(province)} 학교</h3>'
            f'<div class="school-explore-grid">{cards}</div></section>'
        )
    output_section = prefix + "".join(groups) + suffix
    return source[:start] + output_section + source[end:]


def main() -> None:
    if TARGET.exists() and any(TARGET.iterdir()):
        source_count = sum(1 for _ in SOURCE.rglob("*.html"))
        target_count = sum(1 for _ in TARGET.rglob("*.html"))
        if source_count != target_count:
            raise RuntimeError(
                f"incomplete existing target: source_html={source_count} target_html={target_count}"
            )
    metadata = json.loads(META.read_text(encoding="utf-8"))
    by_slug = {str(item["slug"]): item for item in metadata}
    by_location = {
        (location_key(item), *subject_grade(item)): item
        for item in metadata if not item.get("school_name")
    }
    excel_rows = read_excel()
    matches, match_logs, unmatched = match_excel(excel_rows, by_slug)
    selected = select_representatives(matches)
    if any(not 1 <= len(values) <= 12 for values in selected.values()):
        raise RuntimeError({key: len(value) for key, value in selected.items()})

    if not TARGET.exists():
        shutil.copytree(SOURCE, TARGET)
    home = rewrite_home((SOURCE / "index.html").read_text(encoding="utf-8"), selected)
    (TARGET / "index.html").write_text(home, encoding="utf-8", newline="")

    region_items = [item for item in metadata if not item.get("school_name")]

    def convert(item: dict[str, object]) -> tuple[str, list[dict[str, str]]]:
        source_path = SOURCE / str(item["slug"]) / "index.html"
        source = source_path.read_text(encoding="utf-8")
        output, logs = restore_subject_section(source, item, by_location)
        if output != source:
            destination = TARGET / str(item["slug"]) / "index.html"
            temporary = destination.with_name("index.html.subject.tmp")
            temporary.write_text(output, encoding="utf-8", newline="")
            os.replace(temporary, destination)
            return str(item["slug"]), logs
        return str(item["slug"]), []

    restore_logs = []
    changed_pages = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        for slug, logs in pool.map(convert, region_items, chunksize=32):
            if logs:
                changed_pages.append(slug)
                restore_logs.extend(logs)

    match_fields = list(match_logs[0])
    with MATCH_LOG.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, match_fields)
        writer.writeheader(); writer.writerows(match_logs)
    with UNMATCHED.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, match_fields)
        writer.writeheader(); writer.writerows(unmatched)
    restore_fields = list(restore_logs[0])
    with RESTORE_LOG.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, restore_fields)
        writer.writeheader(); writer.writerows(restore_logs)
    CHECKPOINT.write_text(json.dumps({
        "status": "complete", "source": str(SOURCE), "target": str(TARGET), "excel": str(EXCEL),
        "excel_school_count": len(excel_rows), "matched": len(matches), "unmatched": len(unmatched),
        "exact_matches": sum(x["match_status"] == "exact" for x in match_logs),
        "region_corrected_matches": sum(x["match_status"] == "region_corrected" for x in match_logs),
        "changed_region_pages": len(changed_pages),
        "selected_by_province": {key: [x["excel"]["학교표시명"] for x in values] for key, values in selected.items()},
        "selected_count": sum(map(len, selected.values())),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "target": str(TARGET), "excel_schools": len(excel_rows), "matched": len(matches),
        "unmatched": len(unmatched), "changed_region_pages": len(changed_pages),
        "home_school_cards": sum(map(len, selected.values())),
        "province_counts": {key: len(value) for key, value in selected.items()},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
