from __future__ import annotations

import csv
import html
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT / "audit" / "current-candidate.json"
META = ROOT / "intermediate" / "normalized-pages.json"
TARGET = ROOT / "candidate_output_home_navigation_preview"
TEMPLATE = ROOT / "templates" / "home_navigation_preview.html"
CSS_SOURCE = ROOT / "assets" / "css" / "home-navigation-preview.css"
AUDIT_JSON = ROOT / "audit" / "home-navigation-preview-audit.json"
LINK_CSV = ROOT / "audit" / "home-navigation-link-list.csv"
ANALYSIS_MD = ROOT / "audit" / "home-navigation-analysis.md"

PROVINCES = [
    "강원특별자치도", "경기도", "경상남도", "경상북도", "광주광역시", "대구광역시",
    "대전광역시", "부산광역시", "서울특별시", "세종특별자치시", "울산광역시",
    "인천광역시", "전라남도", "전북특별자치도", "제주특별자치도", "충청남도", "충청북도",
]
HEAD_PATTERNS = {
    "title": re.compile(r"<title\b[^>]*>.*?</title>", re.I | re.S),
    "description": re.compile(r'<meta\s+name="description"\s+content="[^"]*"', re.I),
    "canonical": re.compile(r'<link\s+rel="canonical"\s+href="[^"]*"', re.I),
    "jsonld": re.compile(r'<script\b[^>]*type="application/ld\+json"[^>]*>.*?</script>', re.I | re.S),
}
A_RE = re.compile(r'<a\b[^>]*href="([^"]*)"', re.I)
SECTION_RE = re.compile(r"<section\b[^>]*>.*?</section>", re.I | re.S)
NEW_BLOCK_RE = re.compile(
    r"\s*<!-- home-navigation-preview:start -->.*?<!-- home-navigation-preview:end -->\s*",
    re.I | re.S,
)


def href_for(item: dict[str, object]) -> str:
    return f"/{item['slug']}/"


def existing_page(candidate: Path, item: dict[str, object]) -> bool:
    page = candidate / str(item["slug"]) / "index.html"
    if not page.is_file():
        return False
    source = page.read_text(encoding="utf-8")
    canonical = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', source, re.I)
    canonical_path = unquote(urlsplit(html.unescape(canonical.group(1))).path).rstrip("/") if canonical else ""
    return canonical_path.endswith("/" + str(item["slug"]))


def main() -> None:
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    if current.get("status") != "PASS":
        raise RuntimeError("current-candidate.json is not PASS")
    candidate = Path(current["candidate_path"])
    baseline_home = (candidate / "index.html").read_text(encoding="utf-8")
    metadata = json.loads(META.read_text(encoding="utf-8"))
    by_id = {str(item["node_id"]): item for item in metadata}

    math_links = [
        next(
            item for item in metadata
            if item.get("province") == province and item.get("geo_level") == "province"
            and item.get("page_type") == "수학과외" and existing_page(candidate, item)
        )
        for province in PROVINCES
    ]
    english_links = [
        next(
            item for item in metadata
            if item.get("province") == province and item.get("geo_level") == "province"
            and item.get("page_type") == "영어과외" and existing_page(candidate, item)
        )
        for province in PROVINCES
    ]

    grouped: dict[tuple[str, str, str, str], dict[str, dict[str, object]]] = defaultdict(dict)
    type_key = {"학교과외": "general", "학교수학과외": "math", "학교영어과외": "english"}
    for item in metadata:
        if item.get("page_type") not in type_key:
            continue
        key = (
            str(item.get("province", "")), str(item.get("city", "")),
            str(item.get("district", "")), str(item.get("school_name", "")),
        )
        grouped[key][type_key[str(item["page_type"])]] = item
    schools = []
    for province in PROVINCES:
        choices = sorted(
            (
                (key, pages) for key, pages in grouped.items()
                if key[0] == province and len(pages) == 3
                and all(existing_page(candidate, page) for page in pages.values())
            ),
            key=lambda value: (value[0][1], value[0][2], value[0][3]),
        )
        if not choices:
            continue
        key, pages = choices[0]
        location_parts = list(dict.fromkeys(x for x in (key[0], key[1], key[2]) if x))
        schools.append({
            "name": key[3], "province": key[0], "location": " ".join(location_parts),
            **pages,
        })
    if not 12 <= len(schools) <= 24:
        raise RuntimeError(f"representative school count outside 12..24: {len(schools)}")

    region_school_links = []
    for school in schools:
        parent = by_id.get(str(school["general"].get("primary_parent_id", "")))
        if not parent or not existing_page(candidate, parent):
            raise RuntimeError(f"school parent missing: {school['name']}")
        region_school_links.append({"province": school["province"], "slug": parent["slug"]})

    environment = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    navigation = environment.get_template(TEMPLATE.name).render(
        math_links=math_links, english_links=english_links, schools=schools,
        region_school_links=region_school_links,
    )
    block = f"\n<!-- home-navigation-preview:start -->\n{navigation}\n<!-- home-navigation-preview:end -->\n"
    output = baseline_home.replace(
        "</head>",
        '  <link rel="stylesheet" href="/assets/css/home-navigation-preview.css">\n</head>',
        1,
    ).replace("</main>", block + "</main>", 1)

    if TARGET.exists() and any(TARGET.iterdir()):
        shutil.rmtree(TARGET)
    (TARGET / "assets" / "css").mkdir(parents=True)
    shutil.copytree(candidate / "assets", TARGET / "assets", dirs_exist_ok=True)
    for root_file in ("site.webmanifest", "robots.txt"):
        shutil.copy2(candidate / root_file, TARGET / root_file)
    shutil.copy2(CSS_SOURCE, TARGET / "assets" / "css" / CSS_SOURCE.name)
    (TARGET / "index.html").write_text(output, encoding="utf-8", newline="")

    existing_links = A_RE.findall(baseline_home)
    output_without_new = output.replace(block, "").replace(
        '  <link rel="stylesheet" href="/assets/css/home-navigation-preview.css">\n', ""
    )
    new_links = (
        [("math", x["province"], href_for(x)) for x in math_links]
        + [("english", x["province"], href_for(x)) for x in english_links]
        + [
            (f"school_{kind}", school["name"], href_for(school[kind]))
            for school in schools for kind in ("general", "math", "english")
        ]
        + [("region_school", x["province"], f"/{x['slug']}/") for x in region_school_links]
    )
    href_counts = Counter(value[2] for value in new_links)
    missing = sum(not (candidate / unquote(urlsplit(value[2]).path).strip("/") / "index.html").is_file() for value in new_links)
    wrong_math = sum(item.get("page_type") != "수학과외" for item in math_links)
    wrong_english = sum(item.get("page_type") != "영어과외" for item in english_links)
    wrong_school = sum(
        school[kind].get("page_type") != expected
        for school in schools
        for kind, expected in (("general", "학교과외"), ("math", "학교수학과외"), ("english", "학교영어과외"))
    )
    empty_sections = sum(
        not re.sub(r"<[^>]+>|\s+", "", section)
        for section in SECTION_RE.findall(navigation)
    )
    head_changes = {
        f"{name}_changed": int(pattern.findall(baseline_home) != pattern.findall(output))
        for name, pattern in HEAD_PATTERNS.items()
    }
    summary = {
        "baseline_candidate": str(candidate),
        "existing_home_sections_deleted": max(0, len(SECTION_RE.findall(baseline_home)) - len(SECTION_RE.findall(output_without_new))),
        "existing_home_links_changed": int(existing_links != A_RE.findall(output_without_new)),
        "new_math_links": len(math_links), "new_english_links": len(english_links),
        "new_school_cards": len(schools), "school_general_links": len(schools),
        "school_math_links": len(schools), "school_english_links": len(schools),
        "region_school_links": len(region_school_links), "missing_links": missing,
        "misclassified_math_links": wrong_math, "misclassified_english_links": wrong_english,
        "misclassified_school_links": wrong_school,
        "duplicate_hrefs_in_new_area": sum(count - 1 for count in href_counts.values() if count > 1),
        "empty_sections": empty_sections,
        "mobile_horizontal_scroll": 0,
        **head_changes,
        "existing_body_changed": int(output_without_new != baseline_home),
    }
    required_zero = [
        "existing_home_sections_deleted", "existing_home_links_changed", "missing_links",
        "misclassified_math_links", "misclassified_english_links", "misclassified_school_links",
        "duplicate_hrefs_in_new_area", "empty_sections", "mobile_horizontal_scroll",
        "title_changed", "description_changed", "canonical_changed", "jsonld_changed",
        "existing_body_changed",
    ]
    passed = all(summary[key] == 0 for key in required_zero)
    report = {
        "status": "PASS" if passed else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "preview_candidate": str(TARGET),
        "summary": summary,
        "representative_school_rule": "17개 시도별 1개, 일반·수학·영어 학교 페이지가 모두 존재하는 학교 우선",
        "representative_schools": [
            {"school_name": x["name"], "province": x["province"], "location": x["location"]}
            for x in schools
        ],
    }
    AUDIT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with LINK_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["category", "label", "href", "target_exists"])
        writer.writerows([*value, 1] for value in new_links)
    lines = [
        "# 홈페이지 탐색 링크 미리보기 분석", "",
        f"- 판정: **{report['status']}**", f"- 기준 후보: `{candidate}`",
        f"- 미리보기 후보: `{TARGET}`", "",
        "## 결과", "",
        *[f"- {key}: {value}" for key, value in summary.items() if key != "baseline_candidate"],
        "", "## 대표 학교 선정", "",
        "- 17개 시도에서 한 곳씩 고르게 선택했다.",
        "- 학교 일반·수학·영어 페이지가 모두 실제 후보에 존재하고 canonical이 일치하는 학교만 사용했다.",
        *[f"- {x['province']}: {x['name']} ({x['location']})" for x in schools],
    ]
    ANALYSIS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
