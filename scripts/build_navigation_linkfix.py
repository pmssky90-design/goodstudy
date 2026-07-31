from __future__ import annotations

import copy
import csv
import html
import json
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_structure_image_homefix"
TARGET = ROOT / "candidate_output_navigation_linkfix"
META = ROOT / "intermediate" / "normalized-pages.json"
LOG = ROOT / "audit" / "navigation-linkfix-log.csv"
SAMPLES = ROOT / "audit" / "navigation-linkfix-samples.txt"
CHECKPOINT = ROOT / "intermediate" / "navigation-linkfix-build-checkpoint.json"

RELATED = re.compile(r'<section class="related-section">.*?</section>', re.I | re.S)
GRID = re.compile(r'(<div class="link-card-grid">)(.*?)(</div>)', re.I | re.S)
CARD = re.compile(r'<a class="link-card"[^>]*>.*?</a>', re.I | re.S)
H2 = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")

PROVINCE_IDS = {
    "강원특별자치도": "gangwon", "경기도": "gyeonggi", "경상남도": "gyeongnam",
    "경상북도": "gyeongbuk", "광주광역시": "gwangju", "대구광역시": "daegu",
    "대전광역시": "daejeon", "부산광역시": "busan", "서울특별시": "seoul",
    "세종특별자치시": "sejong", "울산광역시": "ulsan", "인천광역시": "incheon",
    "전라남도": "jeonnam", "전북특별자치도": "jeonbuk", "제주특별자치도": "jeju",
    "충청남도": "chungnam", "충청북도": "chungbuk",
}


def text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", value))).strip()


def subject_grade(item: dict[str, object]) -> tuple[str, str]:
    page_type = str(item.get("page_type", ""))
    subject = "math" if "수학" in page_type else ("english" if "영어" in page_type else "general")
    grade = "elementary" if "초등" in page_type else ("middle" if "중등" in page_type else ("high" if "고등" in page_type else "general"))
    return subject, grade


def location_key(item: dict[str, object]) -> tuple[str, str, str, str, str]:
    return (
        str(item.get("geo_level", "")), str(item.get("province", "")),
        str(item.get("city", "")), str(item.get("district", "")), str(item.get("locality", "")),
    )


def href_from_card(value: str) -> str:
    match = re.search(r'href="([^"]*)"', value, re.I)
    return html.unescape(match.group(1)) if match else ""


def label_from_card(value: str) -> str:
    match = re.search(r"<strong\b[^>]*>(.*?)</strong>", value, re.I | re.S)
    return text(match.group(1)) if match else ""


def desired_children(
    current: dict[str, object],
    by_id: dict[str, dict[str, object]],
    by_location_class: dict[tuple[tuple[str, str, str, str, str], str, str], dict[str, object]],
) -> list[dict[str, object]]:
    subject, grade = subject_grade(current)
    # Every subject/grade variant points to the general page for the same location.
    base = current if str(current.get("page_type")) == "과외" else by_id.get(str(current.get("primary_parent_id", "")))
    if not base or str(base.get("page_type")) != "과외":
        base = by_location_class.get((location_key(current), "general", "general"))
    if not base:
        return []
    level = str(base.get("geo_level", ""))
    parent_name = str(
        base.get("province") if level == "province"
        else base.get("district") or base.get("city") if level == "district"
        else base.get("locality") or ""
    )
    parent_short = re.sub(r"(특별자치도|특별자치시|광역시|특별시|도)$", "", parent_name)
    derived_suffixes = ("수학", "영어", "초등", "중등", "고등")

    def is_sibling_derivative(item: dict[str, object]) -> bool:
        item_level = str(item.get("geo_level", ""))
        child_name = str(
            item.get("district") or item.get("city") if item_level == "district"
            else item.get("locality") or ""
        )
        return any(child_name in (parent_name + suffix, parent_short + suffix) for suffix in derived_suffixes)

    direct_general = sorted(
        (
            item for item in by_id.values()
            if not item.get("school_name")
            and str(item.get("page_type")) == "과외"
            and str(item.get("primary_parent_id", "")) == str(base.get("node_id"))
            and str(item.get("geo_level")) != str(base.get("geo_level"))
            and not is_sibling_derivative(item)
        ),
        key=lambda item: (str(item.get("link_label", "")), str(item.get("slug", ""))),
    )
    result = []
    for child in direct_general:
        target = by_location_class.get((location_key(child), subject, grade))
        if target and (SOURCE / str(target["slug"]) / "index.html").is_file():
            result.append(target)
    return result


def rewrite_card(template: str, target: dict[str, object], subject: str) -> str:
    href = f"/{target['slug']}/"
    label = str(target.get("link_label") or target.get("breadcrumb_label") or target["slug"])
    value = re.sub(r'href="[^"]*"', f'href="{html.escape(href, quote=True)}"', template, count=1, flags=re.I)
    value = re.sub(r'data-subject="[^"]*"', f'data-subject="{subject}"', value, count=1, flags=re.I)
    value = re.sub(
        r"(<strong\b[^>]*>).*?(</strong>)",
        lambda m: m.group(1) + html.escape(label) + m.group(2),
        value,
        count=1,
        flags=re.I | re.S,
    )
    return value


def replace_child_section(
    source: str, current: dict[str, object], targets: list[dict[str, object]]
) -> tuple[str, list[dict[str, object]]]:
    subject, grade = subject_grade(current)
    sections = list(RELATED.finditer(source))
    child_match = next((match for match in sections if text(H2.search(match.group(0)).group(1)) == "하위 지역"), None)
    old_cards = CARD.findall(child_match.group(0)) if child_match else []
    template = old_cards[0] if old_cards else next(iter(CARD.findall(source)), "")
    if targets and not template:
        raise RuntimeError(f"card template missing: {current['slug']}")
    new_cards = [rewrite_card(template, target, subject) for target in targets]
    logs = []
    for index in range(max(len(old_cards), len(new_cards))):
        old = old_cards[index] if index < len(old_cards) else ""
        new = new_cards[index] if index < len(new_cards) else ""
        target = targets[index] if index < len(targets) else None
        logs.append({
            "source_page": f"/{current['slug']}/", "section_type": "하위 지역",
            "page_subject": subject, "page_grade": grade,
            "old_label": label_from_card(old), "old_href": href_from_card(old),
            "new_label": label_from_card(new), "new_href": href_from_card(new),
            "target_subject": subject if target else "", "target_grade": grade if target else "",
            "change_reason": "직접 하위 지역의 동일 과목·학년 페이지로 교체" if target else "직접 하위 지역이 없어 잘못된 카드 제거",
        })
    if child_match:
        if targets:
            block = child_match.group(0)
            block = GRID.sub(lambda m: m.group(1) + "".join(new_cards) + m.group(3), block, count=1)
            output = source[:child_match.start()] + block + source[child_match.end():]
        else:
            output = source[:child_match.start()] + source[child_match.end():]
    elif targets:
        block = (
            '<section class="related-section"><div class="section-heading"><h2>하위 지역</h2>'
            '<p>현재 지역 아래의 생활권을 살펴보세요.</p></div>'
            f'<div class="link-card-grid">{"".join(new_cards)}</div></section>'
        )
        insertion = next((match.start() for match in sections if text(H2.search(match.group(0)).group(1)) in ("학년별 학습", "인근 지역 살펴보기")), len(source))
        output = source[:insertion] + block + source[insertion:]
    else:
        output = source
    return output, logs


def rewrite_home(source: str, by_slug: dict[str, dict[str, object]]) -> tuple[str, list[dict[str, object]], int]:
    soup = BeautifulSoup(source, "html.parser")
    cards = soup.select(".school-explore-grid .school-card")
    province_to_id: dict[str, str] = {}
    card_ids: list[str] = []
    for card in cards:
        first_link = card.select_one(".school-card-links a[href]")
        if not first_link:
            continue
        slug = unquote(urlsplit(str(first_link["href"])).path).strip("/")
        item = by_slug.get(slug)
        if not item:
            continue
        province = str(item.get("province", ""))
        code = PROVINCE_IDS.get(province)
        if code:
            anchor_id = f"schools-{code}"
            province_to_id[province] = anchor_id
            card_ids.append(anchor_id)
    article_pattern = re.compile(r'<article class="school-card">.*?</article>', re.I | re.S)
    article_matches = list(article_pattern.finditer(source))
    if len(article_matches) != len(card_ids):
        raise RuntimeError(f"home school card count mismatch: html={len(article_matches)}, mapped={len(card_ids)}")
    pieces = []
    cursor = 0
    for match, anchor_id in zip(article_matches, card_ids):
        pieces.append(source[cursor:match.start()])
        pieces.append(match.group(0).replace(
            '<article class="school-card">',
            f'<article class="school-card" id="{anchor_id}">',
            1,
        ))
        cursor = match.end()
    pieces.append(source[cursor:])
    output = "".join(pieces)

    logs = []
    changed = 0
    for anchor in soup.select(".region-school-links a[href]"):
        old_href = str(anchor["href"])
        slug = unquote(urlsplit(old_href).path).strip("/")
        item = by_slug.get(slug)
        province = str(item.get("province", "")) if item else ""
        anchor_id = province_to_id.get(province)
        if not anchor_id:
            continue
        new_href = f"#{anchor_id}"
        if old_href != new_href:
            old_markup = f'href="{html.escape(old_href, quote=True)}"'
            new_markup = f'href="{new_href}"'
            region_block = re.search(r'<div class="region-school-links">.*?</div>', output, re.I | re.S)
            if not region_block or old_markup not in region_block.group(0):
                raise RuntimeError(f"home region-school href not found: {old_href}")
            replacement = region_block.group(0).replace(old_markup, new_markup, 1)
            output = output[:region_block.start()] + replacement + output[region_block.end():]
            changed += 1
        logs.append({
            "source_page": "/", "section_type": "지역별 학교 살펴보기",
            "page_subject": "general", "page_grade": "general",
            "old_label": anchor.get_text(" ", strip=True), "old_href": old_href,
            "new_label": anchor.get_text(" ", strip=True), "new_href": new_href,
            "target_subject": "school_anchor", "target_grade": "general",
            "change_reason": "학교 허브가 없어 동일 시도 대표 학교 카드 앵커로 교체",
        })
    return output, logs, changed


def main() -> None:
    target_exists = TARGET.exists() and any(TARGET.iterdir())
    metadata = json.loads(META.read_text(encoding="utf-8"))
    by_id = {str(item["node_id"]): item for item in metadata}
    by_slug = {str(item["slug"]): item for item in metadata}
    by_location_class = {
        (location_key(item), *subject_grade(item)): item
        for item in metadata if not item.get("school_name")
    }
    if "--home-only" in sys.argv:
        home_output, _, home_changed = rewrite_home((SOURCE / "index.html").read_text(encoding="utf-8"), by_slug)
        (TARGET / "index.html").write_text(home_output, encoding="utf-8", newline="")
        print(json.dumps({"target": str(TARGET), "home_links_changed": home_changed, "mode": "home-only"}, ensure_ascii=False))
        return

    pilots = []
    for province, geo_level in (("서울특별시", "district"), ("대전광역시", "province"), ("부산광역시", "province")):
        for subject in ("math", "english"):
            match = next(
                item for item in metadata
                if not item.get("school_name") and item.get("province") == province
                and item.get("geo_level") == geo_level
                and subject_grade(item) == (subject, "general")
                and (province != "서울특별시" or item.get("district") == "구로구")
            )
            targets = desired_children(match, by_id, by_location_class)
            output, _ = replace_child_section((SOURCE / str(match["slug"]) / "index.html").read_text(encoding="utf-8"), match, targets)
            if any(subject_grade(target) != (subject, "general") for target in targets):
                raise RuntimeError(f"pilot context mismatch: {match['slug']}")
            if any(f'/{target["slug"]}/' not in output for target in targets):
                raise RuntimeError(f"pilot link missing: {match['slug']}")
            pilots.append({"source": match, "targets": targets})

    if not target_exists:
        shutil.copytree(SOURCE, TARGET)
    home_output, home_logs, home_changed = rewrite_home((SOURCE / "index.html").read_text(encoding="utf-8"), by_slug)
    (TARGET / "index.html").write_text(home_output, encoding="utf-8", newline="")

    region_items = [item for item in metadata if not item.get("school_name")]

    def convert(item: dict[str, object]) -> tuple[str, list[dict[str, object]]]:
        path = SOURCE / str(item["slug"]) / "index.html"
        source = path.read_text(encoding="utf-8")
        targets = desired_children(item, by_id, by_location_class)
        output, logs = replace_child_section(source, item, targets)
        if output != source:
            destination = TARGET / str(item["slug"]) / "index.html"
            temporary = destination.with_name("index.html.linkfix.tmp")
            temporary.write_text(output, encoding="utf-8", newline="")
            os.replace(temporary, destination)
        return str(item["slug"]), logs if output != source else []

    all_logs = list(home_logs)
    changed_region_pages = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        for slug, logs in pool.map(convert, region_items, chunksize=32):
            if logs:
                changed_region_pages.append(slug)
                all_logs.extend(logs)

    fields = [
        "source_page", "section_type", "page_subject", "page_grade", "old_label", "old_href",
        "new_label", "new_href", "target_subject", "target_grade", "change_reason",
    ]
    with LOG.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(all_logs)

    sample_groups: dict[str, list[dict[str, object]]] = {
        "수학 상위 지역 → 하위 지역": [],
        "영어 상위 지역 → 하위 지역": [],
        "학년별 수학": [],
        "학년별 영어": [],
    }
    for row in all_logs:
        if row["section_type"] != "하위 지역" or not row["new_href"]:
            continue
        if row["page_subject"] == "math" and row["page_grade"] == "general":
            sample_groups["수학 상위 지역 → 하위 지역"].append(row)
        elif row["page_subject"] == "english" and row["page_grade"] == "general":
            sample_groups["영어 상위 지역 → 하위 지역"].append(row)
        elif row["page_subject"] == "math" and row["page_grade"] != "general":
            sample_groups["학년별 수학"].append(row)
        elif row["page_subject"] == "english" and row["page_grade"] != "general":
            sample_groups["학년별 영어"].append(row)
    limits = {"수학 상위 지역 → 하위 지역": 20, "영어 상위 지역 → 하위 지역": 20, "학년별 수학": 10, "학년별 영어": 10}
    lines = ["대표 링크 샘플", ""]
    for title, values in sample_groups.items():
        lines.extend([f"[{title}]", *[f"{x['source_page']} -> {x['new_href']} ({x['new_label']})" for x in values[:limits[title]]], ""])
    lines.append("[홈페이지 학교 링크 전체]")
    lines.extend(f"{x['old_label']}: {x['old_href']} -> {x['new_href']}" for x in home_logs)
    SAMPLES.write_text("\n".join(lines) + "\n", encoding="utf-8")
    CHECKPOINT.write_text(json.dumps({
        "status": "complete", "source": str(SOURCE), "target": str(TARGET),
        "html_count": int((TARGET / "index.html").is_file()) + sum(1 for _ in TARGET.glob("*/index.html")),
        "changed_region_pages": len(changed_region_pages), "home_links_changed": home_changed,
        "log_rows": len(all_logs), "pilot_pages": [
            {"slug": x["source"]["slug"], "children": [y["slug"] for y in x["targets"]]} for x in pilots
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "target": str(TARGET), "changed_region_pages": len(changed_region_pages),
        "home_links_changed": home_changed, "log_rows": len(all_logs),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
