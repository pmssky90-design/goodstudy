from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
STRUCTURE = ROOT / "candidate_output_structureclean"
HOME_NAV = ROOT / "candidate_output_home_navigation_preview"
IMAGE = ROOT / "candidate_output_image_preview"
TARGET = ROOT / "candidate_output_structure_image_homefix_preview"
META = ROOT / "intermediate" / "normalized-pages.json"
CSS_TARGET = ROOT / "assets" / "css" / "structure-home-image-fix.css"
AUDIT_JSON = ROOT / "audit" / "structure-image-homefix-preview-audit.json"
ANALYSIS_MD = ROOT / "audit" / "structure-image-homefix-analysis.md"
DIFF_CSV = ROOT / "audit" / "structure-image-homefix-file-diff.csv"

NAV_BLOCK = re.compile(
    r"<!-- home-navigation-preview:start -->.*?<!-- home-navigation-preview:end -->",
    re.I | re.S,
)
HEAD = re.compile(r"<head\b[^>]*>.*?</head>", re.I | re.S)
BODY = re.compile(r"<body\b[^>]*>(.*?)</body>", re.I | re.S)
TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
DESC = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
CANON = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
JSONLD = re.compile(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
A = re.compile(r'<a\b[^>]*href="([^"]*)"', re.I)
TAG = re.compile(r"<[^>]+>")
FIXED = re.compile(r'<figure\b[^>]*class="[^"]*\bcontent-fixed-image\b[^"]*"[^>]*>.*?</figure>', re.I | re.S)
HERO_IMAGE = re.compile(r'<img\b[^>]*class="[^"]*\bhome-hero-image\b[^"]*"[^>]*>', re.I)
CSS_LINKS = (
    "/assets/css/structure-preview.css",
    "/assets/css/home-navigation-preview.css",
    "/assets/css/image-preview.css",
)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", value))).strip()


def first(pattern: re.Pattern[str], value: str) -> str:
    found = pattern.search(value)
    return html.unescape(found.group(1)) if found else ""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_integrated_css(source: str) -> str:
    for href in CSS_LINKS:
        source = re.sub(
            rf'\s*<link\s+rel="stylesheet"\s+href="{re.escape(href)}"\s*/?>',
            "",
            source,
            flags=re.I,
        )
    return source.replace(
        "</head>",
        '  <link rel="stylesheet" href="/assets/css/structure-home-image-fix.css">\n</head>',
        1,
    )


def select(metadata: list[dict[str, object]]) -> list[dict[str, object]]:
    specs = [
        ("지역 일반", 2, lambda x: not x.get("school_name") and x.get("page_type") == "과외"),
        ("지역 수학", 2, lambda x: not x.get("school_name") and x.get("page_type") == "수학과외"),
        ("지역 영어", 2, lambda x: not x.get("school_name") and x.get("page_type") == "영어과외"),
        ("학교 일반", 2, lambda x: x.get("page_type") == "학교과외"),
        ("학교 수학", 2, lambda x: x.get("page_type") == "학교수학과외"),
        ("학교 영어", 2, lambda x: x.get("page_type") == "학교영어과외"),
    ]
    chosen: list[dict[str, object]] = []
    used: set[str] = set()
    for category, count, predicate in specs:
        matches = sorted((x for x in metadata if predicate(x)), key=lambda x: str(x["slug"]))
        picked = [x for x in matches if str(x["slug"]) not in used][:count]
        if len(picked) != count:
            raise RuntimeError(f"missing representative pages for {category}")
        for item in picked:
            used.add(str(item["slug"]))
            chosen.append({**item, "preview_category": category})
    for category, school in (("이미지 지역", False), ("이미지 학교", True)):
        matches = sorted(
            (
                x for x in metadata
                if bool(x.get("school_name")) == school
                and str(x["slug"]) not in used
                and (IMAGE / str(x["slug"]) / "index.html").is_file()
            ),
            key=lambda x: str(x["slug"]),
        )[:2]
        for item in matches:
            used.add(str(item["slug"]))
            chosen.append({**item, "preview_category": category})
    return chosen


def css_selectors(source: str) -> set[str]:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    result: set[str] = set()
    for selectors in re.findall(r"(?:^|})\s*([^@{}][^{}]*)\{", source):
        for selector in selectors.split(","):
            selector = re.sub(r"\s+", " ", selector).strip()
            if selector:
                result.add(selector)
    return result


def internal_target(href: str) -> Path | None:
    parsed = urlsplit(html.unescape(href))
    if parsed.scheme or parsed.netloc:
        if parsed.netloc.lower().removeprefix("www.") != "goodstudy.co.kr":
            return None
    path = unquote(parsed.path)
    if not path.startswith("/") or path.startswith("//"):
        return None
    if path == "/":
        return STRUCTURE / "index.html"
    return STRUCTURE / path.strip("/") / "index.html"


def main() -> None:
    if TARGET.exists():
        raise RuntimeError(f"preview already exists and will not be overwritten: {TARGET}")
    metadata = json.loads(META.read_text(encoding="utf-8"))
    selected = select(metadata)
    if len(selected) != 16:
        raise RuntimeError(f"expected 16 non-home previews, got {len(selected)}")

    structure_css = (ROOT / "assets" / "css" / "structure-preview.css").read_text(encoding="utf-8")
    home_css = (ROOT / "assets" / "css" / "home-navigation-preview.css").read_text(encoding="utf-8")
    image_css = (ROOT / "assets" / "css" / "image-preview.css").read_text(encoding="utf-8")
    integration_css = "\n\n".join([
        "/* Priority 1: approved structure */\n" + structure_css,
        "/* Priority 2: home-only exploration sections */\n" + home_css,
        "/* Priority 3: restored content images */\n" + image_css,
        """/* Priority 4: integration overrides */
.home-hero .hero-media{display:block;min-width:0}
.home-hero-image{display:block;width:100%;height:auto;aspect-ratio:1200/630;object-fit:cover;border-radius:16px}
@media(max-width:900px){.home-hero .hero-media{max-width:640px}}
@media(max-width:600px){.home-hero-image{border-radius:12px}}""",
    ]) + "\n"
    CSS_TARGET.write_text(integration_css, encoding="utf-8", newline="\n")

    shutil.copytree(IMAGE / "assets", TARGET / "assets")
    shutil.copy2(CSS_TARGET, TARGET / "assets" / "css" / CSS_TARGET.name)
    for name in ("site.webmanifest", "robots.txt", "sitemap.xml"):
        if (STRUCTURE / name).is_file():
            shutil.copy2(STRUCTURE / name, TARGET / name)

    base_home = (STRUCTURE / "index.html").read_text(encoding="utf-8")
    nav_home = (HOME_NAV / "index.html").read_text(encoding="utf-8")
    nav = NAV_BLOCK.search(nav_home)
    if not nav:
        raise RuntimeError("home navigation block missing")
    hero_markup = (
        '<img class="home-hero-image" src="/assets/images/search/thumb01.png" '
        'alt="지역과 학교별 과외 학습 정보" width="1200" height="630" '
        'loading="eager" decoding="async">'
    )
    home = base_home.replace('<div class="hero-media" aria-hidden="true"></div>', f'<div class="hero-media">{hero_markup}</div>', 1)
    home = home.replace("</main>", "\n" + nav.group(0) + "\n</main>", 1)
    home = add_integrated_css(home)
    (TARGET / "index.html").write_text(home, encoding="utf-8", newline="")

    rows: list[dict[str, object]] = []
    for item in selected:
        slug = str(item["slug"])
        baseline_path = STRUCTURE / slug / "index.html"
        image_path = IMAGE / slug / "index.html"
        output_path = TARGET / slug / "index.html"
        baseline = baseline_path.read_text(encoding="utf-8")
        image_source = image_path.read_text(encoding="utf-8")
        output = add_integrated_css(image_source)
        output_path.parent.mkdir(parents=True)
        output_path.write_text(output, encoding="utf-8", newline="")
        rows.append({
            "relative_path": f"{slug}/index.html",
            "category": item["preview_category"],
            "source_structure": str(baseline_path),
            "source_image": str(image_path),
            "output": str(output_path),
            "html_changed": int(baseline != output),
            "image_restored": len(FIXED.findall(output)),
            "title_changed": int(first(TITLE, baseline) != first(TITLE, output)),
            "description_changed": int(first(DESC, baseline) != first(DESC, output)),
            "canonical_changed": int(first(CANON, baseline) != first(CANON, output)),
            "jsonld_changed": int(JSONLD.findall(baseline) != JSONLD.findall(output)),
            "body_text_changed": int(clean(BODY.search(baseline).group(1)) != clean(FIXED.sub("", BODY.search(output).group(1)))),
        })

    # Home preservation ignores only the newly approved navigation block and hero image.
    normalized_home = NAV_BLOCK.sub("", HERO_IMAGE.sub("", home))
    normalized_home = re.sub(r'<div class="hero-media">\s*</div>', '<div class="hero-media" aria-hidden="true"></div>', normalized_home)
    normalized_home = re.sub(r'\s*<link rel="stylesheet" href="/assets/css/structure-home-image-fix.css">', "", normalized_home)
    baseline_normalized = re.sub(r'\s*<link rel="stylesheet" href="/assets/css/structure-preview.css">', "", base_home)
    home_preserved = clean(BODY.search(normalized_home).group(1)) == clean(BODY.search(baseline_normalized).group(1))

    all_outputs = [TARGET / "index.html", *(TARGET / str(x["slug"]) / "index.html" for x in selected)]
    broken: list[dict[str, str]] = []
    missing_images: list[dict[str, str]] = []
    css_missing = 0
    for path in all_outputs:
        source = path.read_text(encoding="utf-8")
        css_missing += int("/assets/css/structure-home-image-fix.css" not in source)
        for href in A.findall(source):
            target_path = internal_target(href)
            if target_path is not None and not target_path.is_file():
                broken.append({"page": path.relative_to(TARGET).as_posix(), "href": href})
        for image_src in re.findall(r'<img\b[^>]*src="([^"]+)"', source, re.I):
            local = TARGET / unquote(urlsplit(image_src).path).lstrip("/")
            if not local.is_file():
                missing_images.append({"page": path.relative_to(TARGET).as_posix(), "src": image_src})

    css_sources = {
        "style.css": (ROOT / "assets" / "css" / "style.css").read_text(encoding="utf-8"),
        "structure-preview.css": structure_css,
        "home-navigation-preview.css": home_css,
        "image-preview.css": image_css,
    }
    selector_owners: dict[str, list[str]] = defaultdict(list)
    for name, value in css_sources.items():
        for selector in css_selectors(value):
            selector_owners[selector].append(name)
    conflicts = {selector: owners for selector, owners in selector_owners.items() if len(owners) > 1}
    watched = [
        ".site-header", ".site-brand", ".home-explore-section", ".subject-explore-grid",
        ".school-explore-grid", ".content-fixed-image", ".hero", ".hero-media", ".link-card",
        ".related-section",
    ]
    watched_owners = {
        selector: [name for name, value in css_sources.items() if selector in css_selectors(value)]
        for selector in watched
    }

    home_terms = {
        term: term in home
        for term in ("수학과외 찾기", "영어과외 찾기", "학교별 과외 찾기", "지역별 학교 살펴보기")
    }
    summary = {
        "preview_html": len(all_outputs),
        "home_navigation_sections_present": sum(home_terms.values()),
        "home_hero_images": len(HERO_IMAGE.findall(home)),
        "region_preview_pages": sum(not x.get("school_name") for x in selected),
        "school_preview_pages": sum(bool(x.get("school_name")) for x in selected),
        "content_images_restored": sum(int(row["image_restored"]) for row in rows),
        "total_visible_images_restored": sum(int(row["image_restored"]) for row in rows) + len(HERO_IMAGE.findall(home)),
        "css_selector_conflicts": len(conflicts),
        "css_missing": css_missing,
        "title_changes": sum(int(row["title_changed"]) for row in rows),
        "description_changes": sum(int(row["description_changed"]) for row in rows),
        "canonical_changes": sum(int(row["canonical_changed"]) for row in rows),
        "jsonld_changes": sum(int(row["jsonld_changed"]) for row in rows),
        "body_text_changes": sum(int(row["body_text_changed"]) for row in rows) + int(not home_preserved),
        "broken_links": len(broken),
        "missing_images": len(missing_images),
        "sitemap_changes": int(sha(STRUCTURE / "sitemap.xml") != sha(TARGET / "sitemap.xml")),
        "header_missing": sum("site-header" not in p.read_text(encoding="utf-8") for p in all_outputs),
        "breadcrumb_missing_non_home": sum("breadcrumb" not in p.read_text(encoding="utf-8") for p in all_outputs[1:]),
        "footer_missing": sum("site-footer" not in p.read_text(encoding="utf-8") for p in all_outputs),
        "structure_cards_missing_non_home": sum("link-card" not in p.read_text(encoding="utf-8") for p in all_outputs[1:]),
    }
    required_zero = (
        "css_missing", "title_changes", "description_changes", "canonical_changes",
        "jsonld_changes", "body_text_changes", "broken_links", "missing_images",
        "sitemap_changes", "header_missing", "breadcrumb_missing_non_home",
        "footer_missing", "structure_cards_missing_non_home",
    )
    passed = (
        len(all_outputs) >= 15
        and all(home_terms.values())
        and summary["home_hero_images"] == 1
        and summary["content_images_restored"] == len(selected)
        and all(summary[key] == 0 for key in required_zero)
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "structure_candidate": str(STRUCTURE),
        "home_navigation_candidate": str(HOME_NAV),
        "image_candidate": str(IMAGE),
        "preview_candidate": str(TARGET),
        "summary": summary,
        "home_checks": home_terms,
        "selected_pages": [
            {"category": x["preview_category"], "slug": x["slug"], "school_name": x.get("school_name", "")}
            for x in selected
        ],
        "css": {
            "integrated_css": str(CSS_TARGET),
            "priority": ["style.css (existing base)", "structure", "home navigation", "images", "integration overrides"],
            "conflicts": conflicts,
            "watched_selector_owners": watched_owners,
        },
        "details": {"broken_links": broken, "missing_images": missing_images},
    }
    AUDIT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with DIFF_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    inventory = json.loads((ROOT / "audit" / "structure-image-homefix-source-inventory.json").read_text(encoding="utf-8"))
    lines = [
        "# 구조·이미지·홈 탐색 통합 미리보기 분석", "",
        f"- 판정: **{report['status']}**",
        f"- 구조 기준: `{STRUCTURE}`",
        f"- 홈 탐색 기준: `{HOME_NAV}`",
        f"- 이미지 기준: `{IMAGE}`",
        f"- 통합 미리보기: `{TARGET}`", "",
        "## 회귀 원인", "",
        "- 구조 전체 생성은 15:00에 완료됐고 홈 탐색(16:56)과 이미지 통합(17:27)은 별도 후속 후보로 생성됐다.",
        "- 후속 기능은 기존 PASS 구조 후보에 역병합되지 않았으므로 structureclean을 다시 기준으로 보면 최신 홈 탐색과 이미지 기능이 보이지 않는다.",
        "- 기존 후보 손상이나 삭제가 아니라 후보 계보 선택 문제다.", "",
        "## 결과", "",
        *[f"- {key}: {value}" for key, value in summary.items()],
        "", "## CSS 충돌과 우선순위", "",
        f"- 동일 selector 충돌: {len(conflicts)}개",
        *[f"- `{selector}`: {', '.join(owners)}" for selector, owners in conflicts.items()],
        "- 우선순위: 기존 style.css → 승인 구조 → 홈 탐색 → 이미지 → 통합 override",
        f"- 통합 CSS: `{CSS_TARGET}`", "",
        "## 후보·감사 인벤토리", "",
        f"- 전체 후보 기록: `{ROOT / 'audit' / 'structure-image-homefix-source-inventory.json'}`",
        f"- 조사 후보 수: {len(inventory['candidates'])}",
        f"- 조사 감사 파일 수: {len(inventory['audits'])}",
    ]
    ANALYSIS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "summary": summary, "target": str(TARGET)}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
