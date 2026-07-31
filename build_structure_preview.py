from __future__ import annotations

import html
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "candidate_output_descriptionclean"
TARGET = ROOT / "candidate_output_structure_preview"
META = ROOT / "intermediate" / "normalized-pages.json"
CLASSIFICATION = ROOT / "audit" / "structure-page-classification.json"

HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head>", re.I | re.S)
HEADER_RE = re.compile(r"<header\b[^>]*>.*?</header>", re.I | re.S)
MAIN_RE = re.compile(r"<main\b[^>]*>.*?</main>", re.I | re.S)
FOOTER_RE = re.compile(r"<footer\b[^>]*>.*?</footer>", re.I | re.S)
BREAD_RE = re.compile(r'<nav class="breadcrumb"[^>]*>(.*?)</nav>', re.I | re.S)
ARTICLE_RE = re.compile(r"<article\b[^>]*>(.*?)</article>", re.I | re.S)
H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
CONTENT_RE = re.compile(r'<div class="content">(.*?)</div>\s*</article>', re.I | re.S)
SECTION_RE = re.compile(r"<section\b[^>]*>(.*?)</section>", re.I | re.S)
A_RE = re.compile(r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def norm(value: str) -> str:
    return "".join(ch for ch in text(value).casefold() if ch.isalnum())


def classify(meta: dict[str, object]) -> dict[str, str]:
    page_type = str(meta.get("page_type") or "과외")
    entity = "school" if meta.get("school_name") else "region"
    subject = "math" if "수학" in page_type else ("english" if "영어" in page_type else "general")
    grade = "elementary" if "초등" in page_type else ("middle" if "중등" in page_type else ("high" if "고등" in page_type else "general"))
    region_level = str(meta.get("geo_level") or ("school" if entity == "school" else "region"))
    return {
        "entity_type": entity, "subject_type": subject, "grade_type": grade,
        "region_level": region_level, "school_name": str(meta.get("school_name") or ""),
        "current_region": str(meta.get("locality") or meta.get("district") or meta.get("city") or meta.get("province") or ""),
        "parent_region": str(meta.get("district") or meta.get("city") or meta.get("province") or ""),
    }


def card(href: str, label: str, target_meta: dict[str, object] | None) -> str:
    page_type = str((target_meta or {}).get("page_type") or "")
    subject = "math" if "수학" in page_type else ("english" if "영어" in page_type else "general")
    badge = {"math": "수학", "english": "영어", "general": "일반"}[subject]
    subtitle = {"math": "개념과 문제 적용 흐름", "english": "어휘·문법과 독해 흐름", "general": "학습 전반과 일정 관리"}[subject]
    return (
        f'<a class="link-card" data-subject="{subject}" href="{html.escape(href, quote=True)}">'
        f'<span class="link-card-label">{badge}</span><strong>{html.escape(label)}</strong>'
        f'<span>{subtitle}</span></a>'
    )


def section(title_value: str, description: str, items: list[tuple[str, str, dict[str, object] | None]]) -> str:
    if not items:
        return ""
    cards = "".join(card(*item) for item in items)
    return (
        f'<section class="related-section"><div class="section-heading"><h2>{title_value}</h2>'
        f'<p>{description}</p></div><div class="link-card-grid">{cards}</div></section>'
    )


def breadcrumb(source: str, meta: dict[str, object]) -> str:
    match = BREAD_RE.search(source)
    values: list[tuple[str | None, str]] = []
    if match:
        for href, body in A_RE.findall(match.group(1)):
            values.append((href, text(body)))
        tail = re.findall(r"<span>(.*?)</span>", match.group(1), re.I | re.S)
        if tail:
            current = text(tail[-1])
            if current and current not in ("›", ">"):
                values.append((None, current))
    if not values:
        values = [("/", "홈"), (None, str(meta.get("breadcrumb_label") or meta.get("link_label") or ""))]
    items = []
    for index, (href, label) in enumerate(values):
        if index == len(values) - 1 or href is None:
            items.append(f'<li aria-current="page">{html.escape(label)}</li>')
        else:
            items.append(f'<li><a href="{html.escape(href, quote=True)}">{html.escape(label)}</a></li>')
    return f'<nav class="breadcrumb" aria-label="breadcrumb"><ol>{"".join(items)}</ol></nav>'


def related(source: str, current: dict[str, object], by_slug: dict[str, dict[str, object]], by_id: dict[str, dict[str, object]]) -> str:
    links: list[tuple[str, str, dict[str, object] | None]] = []
    seen: set[str] = set()
    for block in SECTION_RE.findall(source):
        for href, body in A_RE.findall(block):
            if not href.startswith("/") or href in seen:
                continue
            seen.add(href)
            slug = unquote(href.strip("/"))
            meta = by_slug.get(slug)
            label = str((meta or {}).get("link_label") or text(body))
            links.append((href, label, meta))
    groups: dict[str, list[tuple[str, str, dict[str, object] | None]]] = defaultdict(list)
    current_class = classify(current)
    for item in links:
        href, _, meta = item
        if not meta:
            groups["nearby"].append(item); continue
        item_class = classify(meta)
        if current_class["entity_type"] == "school":
            if meta.get("school_name") == current.get("school_name"):
                groups["subjects"].append(item)
            elif item_class["entity_type"] == "school":
                groups["schools"].append(item)
            elif item_class["entity_type"] == "region":
                groups["regions"].append(item)
            else:
                groups["nearby"].append(item)
        else:
            if item_class["entity_type"] == "school":
                groups["schools"].append(item)
            elif meta.get("primary_parent_id") == current.get("node_id"):
                groups["children"].append(item)
            elif str(meta.get("locality") or meta.get("district") or meta.get("city")) == str(current.get("locality") or current.get("district") or current.get("city")):
                if item_class["grade_type"] != "general":
                    groups["grades"].append(item)
                else:
                    groups["subjects"].append(item)
            else:
                groups["nearby"].append(item)
    if current_class["entity_type"] == "school":
        return "".join((
            section("이 학교의 과목별 학습", "일반·수학·영어 학습 정보를 구분해 살펴보세요.", groups["subjects"]),
            section("학교가 속한 지역", "학교 주변 지역의 학습 정보를 확인하세요.", groups["regions"]),
            section("같은 지역의 다른 학교", "같은 생활권의 학교를 중심으로 표시합니다.", groups["schools"][:12]),
            section("함께 살펴볼 학습 정보", "현재 페이지와 가까운 학습 정보를 모았습니다.", groups["nearby"]),
        ))
    return "".join((
        section("현재 지역의 과목별 학습", "일반·수학·영어 학습을 구분해 살펴보세요.", groups["subjects"]),
        section("현재 지역의 학교", "지역과 연결된 학교 학습 정보입니다.", groups["schools"]),
        section("하위 지역", "현재 지역 아래의 생활권을 살펴보세요.", groups["children"]),
        section("학년별 학습", "초등·중등·고등 단계에 맞는 정보를 확인하세요.", groups["grades"]),
        section("인근 지역 살펴보기", "상위·인접 지역의 주요 정보입니다.", groups["nearby"]),
    ))


def render_content(source: str, meta: dict[str, object], by_slug: dict[str, dict[str, object]], by_id: dict[str, dict[str, object]]) -> str:
    if meta.get("node_id") == "home":
        main = MAIN_RE.search(source)
        original = main.group(0)[6:-7] if main else ""
        original = original.replace('class="hero"', 'class="home-hero" id="home"')
        original = original.replace("</section>", '<div class="hero-media" aria-hidden="true"></div></section>', 1)
        original = original.replace("<section>", '<section id="regions">', 1)
        return original
    h1_match = H1_RE.search(source)
    h1 = h1_match.group(1) if h1_match else html.escape(str(meta.get("title") or ""))
    content_match = CONTENT_RE.search(source)
    body = content_match.group(1) if content_match else ""
    first_h2 = re.search(r"<h2\b([^>]*)>(.*?)</h2>", body, re.I | re.S)
    if first_h2 and norm(first_h2.group(2)) == norm(h1):
        replacement = f'<h2{first_h2.group(1)} class="is-duplicate-heading">{first_h2.group(2)}</h2>'
        body = body[:first_h2.start()] + replacement + body[first_h2.end():]
    cls = classify(meta)
    context = " · ".join(x for x in (str(meta.get("province") or ""), str(meta.get("city") or ""), str(meta.get("locality") or ""), str(meta.get("school_name") or "")) if x)
    subject_label = {"math": "수학 학습", "english": "영어 학습", "general": "학습 정보"}[cls["subject_type"]]
    panel = (
        f'<section class="title-panel"><p class="title-kicker">{subject_label}</p><h1>{h1}</h1>'
        f'<p class="title-context">{html.escape(context)} · {subject_label}</p>'
        '<div class="page-media-slot"></div></section>'
    )
    return breadcrumb(source, meta) + panel + f'<div class="content-layout"><article><div class="content">{body}</div></article></div>' + related(source, meta, by_slug, by_id)


def main() -> None:
    metadata = json.loads(META.read_text(encoding="utf-8"))
    by_slug = {str(item["slug"]): item for item in metadata}
    by_id = {str(item["node_id"]): item for item in metadata}
    home = {"node_id": "home", "slug": "", "page_type": "home", "title": "좋은공부"}
    wanted = [
        "", "경기도과외", "동두천시과외", "흥덕동과외", "동두천시동두천시수학과외", "동두천시동두천시영어과외",
        "동두천시초등과외", "동두천시중등과외", "동두천시고등과외",
        "흥진고과외", "흥진고수학과외", "흥진고영어과외",
    ]
    missing = [slug for slug in wanted if slug and slug not in by_slug]
    if missing:
        raise RuntimeError(f"preview metadata missing: {missing}")
    TARGET.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE / "assets", TARGET / "assets", dirs_exist_ok=True)
    shutil.copy2(ROOT / "assets" / "css" / "structure-preview.css", TARGET / "assets" / "css" / "structure-preview.css")
    shutil.copy2(SOURCE / "site.webmanifest", TARGET / "site.webmanifest")
    environment = Environment(loader=FileSystemLoader(ROOT / "templates"))
    shell = environment.get_template("structure_preview.html")
    selected = []
    for slug in wanted:
        meta = home if not slug else by_slug[slug]
        source_path = SOURCE / "index.html" if not slug else SOURCE / slug / "index.html"
        source = source_path.read_text(encoding="utf-8")
        head = HEAD_RE.search(source).group(0)
        head = head.replace('</head>', '  <link rel="stylesheet" href="/assets/css/structure-preview.css">\n</head>')
        cls = {"entity_type": "home", "subject_type": "general", "grade_type": "general", "region_level": "home"} if not slug else classify(meta)
        body = shell.render(preview_content=render_content(source, meta, by_slug, by_id), **cls)
        output = re.sub(r"<head\b[^>]*>.*?</head>", head, source, count=1, flags=re.I | re.S)
        output = re.sub(r"<body\b[^>]*>.*?</body>", f"<body>{body}</body>", output, count=1, flags=re.I | re.S)
        target_path = TARGET / "index.html" if not slug else TARGET / slug / "index.html"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(output, encoding="utf-8", newline="")
        selected.append({"slug": slug, **cls, "source": str(source_path), "preview": str(target_path)})
    counts = Counter()
    for item in metadata:
        cls = classify(item)
        counts[f"entity:{cls['entity_type']}"] += 1
        counts[f"subject:{cls['subject_type']}"] += 1
        counts[f"grade:{cls['grade_type']}"] += 1
        counts[f"region_level:{cls['region_level']}"] += 1
    CLASSIFICATION.write_text(json.dumps({
        "total_content_pages": len(metadata), "classification_counts": dict(counts),
        "preview_pages": selected, "rules": {
            "entity_type": "school_name 존재 시 school, 그 외 region",
            "subject_type": "page_type의 수학/영어 키워드, 그 외 general",
            "grade_type": "page_type의 초등/중등/고등 키워드, 그 외 general",
            "region_level": "geo_level 우선, 학교는 school",
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"preview_pages": len(selected), "target": str(TARGET)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
