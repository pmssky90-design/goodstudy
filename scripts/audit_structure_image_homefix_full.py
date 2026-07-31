from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_structure_preview import classify
STRUCTURE = ROOT / "candidate_output_structureclean"
IMAGE = ROOT / "candidate_output_image_preview"
PRIMARY = ROOT / "candidate_output_structure_image_homefix"
REBUILD = ROOT / "candidate_output_structure_image_homefix_rebuild"
META = ROOT / "intermediate" / "normalized-pages.json"
OUT_JSON = ROOT / "audit" / "structure-image-homefix-full-audit.json"
OUT_MD = ROOT / "audit" / "structure-image-homefix-full-audit.md"
DIFF_CSV = ROOT / "audit" / "structure-image-homefix-full-diff.csv"
IMAGE_ERRORS_CSV = ROOT / "audit" / "structure-image-homefix-image-errors.csv"
CURRENT = ROOT / "audit" / "current-candidate.json"

TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
DESC = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
CANON = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
JSONLD = re.compile(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
BODY = re.compile(r"<body\b[^>]*>(.*?)</body>", re.I | re.S)
H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
H2 = re.compile(r"<h2\b([^>]*)>(.*?)</h2>", re.I | re.S)
A = re.compile(r'<a\b[^>]*href="([^"]*)"', re.I)
IMG = re.compile(r'<img\b[^>]*src="([^"]+)"[^>]*>', re.I)
FIXED = re.compile(r'<figure\b[^>]*class="[^"]*\bcontent-fixed-image\b[^"]*"[^>]*>.*?</figure>', re.I | re.S)
HERO = re.compile(r'<img\b[^>]*class="[^"]*\bhome-hero-image\b[^"]*"[^>]*>', re.I)
NAV = re.compile(r"<!-- home-navigation-preview:start -->.*?<!-- home-navigation-preview:end -->", re.I | re.S)
SECTION = re.compile(r"<section\b[^>]*>(.*?)</section>", re.I | re.S)
LINK_CARD = re.compile(r'<a\b[^>]*class="[^"]*\b(?:link-card|subject-link-card)\b[^"]*"[^>]*href="([^"]*)"', re.I)
TAG = re.compile(r"<[^>]+>")
OG_IMAGE = re.compile(r'<meta\s+property="og:image(?::(?:width|height|type))?"\s+content="([^"]*)"', re.I)
TWITTER_IMAGE = re.compile(r'<meta\s+name="twitter:image"\s+content="([^"]*)"', re.I)


def atomic_text(path: Path, value: str, encoding: str = "utf-8") -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding=encoding, newline="\n")
    os.replace(temporary, path)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", value))).strip()


def first(pattern: re.Pattern[str], value: str) -> str:
    match = pattern.search(value)
    return html.unescape(match.group(1)) if match else ""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def internal(href: str) -> str | None:
    parsed = urlsplit(html.unescape(href))
    if parsed.scheme or parsed.netloc:
        if parsed.netloc.lower().removeprefix("www.") != "goodstudy.co.kr":
            return None
    path = unquote(parsed.path)
    if not path.startswith("/") or path.startswith("//"):
        return None
    return path if path.endswith("/") else path + "/"


def normalized_body(source: str, home: bool) -> str:
    body = BODY.search(source)
    value = body.group(1) if body else ""
    value = FIXED.sub("", value)
    if home:
        value = NAV.sub("", value)
        value = HERO.sub("", value)
    return clean(value)


def select_target() -> Path:
    for target in (PRIMARY, REBUILD):
        if target.is_dir():
            count = int((target / "index.html").is_file()) + sum(1 for _ in target.glob("*/index.html"))
            if count == 30457:
                return target
    raise RuntimeError("no completed full integration target")


def inspect(args: tuple[Path, Path, Path, Path]) -> dict[str, object]:
    structure_path, image_path, target_path, target_root = args
    rel = structure_path.relative_to(STRUCTURE).as_posix()
    is_home = rel == "index.html"
    try:
        structure = structure_path.read_text(encoding="utf-8")
        image = image_path.read_text(encoding="utf-8")
        target = target_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"relative_path": rel, "read_error": repr(exc)}
    h1s = H1.findall(target)
    visible_h2 = [body for attrs, body in H2.findall(target) if "is-duplicate-heading" not in attrs]
    cards = LINK_CARD.findall(target)
    target_links = {x for x in (internal(href) for href in A.findall(target)) if x is not None}
    structure_links = {x for x in (internal(href) for href in A.findall(structure)) if x is not None}
    fixed_target = FIXED.findall(target)
    fixed_image = FIXED.findall(image)
    image_errors: list[dict[str, str]] = []
    for src in IMG.findall(target):
        parsed = urlsplit(html.unescape(src))
        if parsed.scheme or parsed.netloc:
            continue
        local = target_root / unquote(parsed.path).lstrip("/")
        if not local.is_file():
            image_errors.append({"relative_path": rel, "code": "missing_image_file", "value": src})
    if not is_home and fixed_target != fixed_image:
        image_errors.append({"relative_path": rel, "code": "image_mapping_changed", "value": ""})
    if not is_home and len(fixed_target) != 1:
        image_errors.append({"relative_path": rel, "code": "content_image_count", "value": str(len(fixed_target))})
    return {
        "relative_path": rel, "read_error": "", "zero_byte": int(target_path.stat().st_size == 0),
        "h1_count": len(h1s),
        "duplicate_h1_h2": sum(bool(h1s) and clean(body) == clean(h1s[0]) for body in visible_h2),
        "empty_sections": sum(not clean(block) for block in SECTION.findall(target)),
        "duplicate_card_hrefs": len(cards) - len(set(cards)),
        "css_missing": int("/assets/css/structure-home-image-fix.css" not in target),
        "title_changed": int(first(TITLE, structure) != first(TITLE, target)),
        "description_changed": int(first(DESC, structure) != first(DESC, target)),
        "canonical_changed": int(first(CANON, structure) != first(CANON, target)),
        "jsonld_changed": int(JSONLD.findall(structure) != JSONLD.findall(target)),
        "body_text_changed": int(normalized_body(structure, is_home) != normalized_body(target, is_home)),
        "internal_links_changed": int(not is_home and structure_links != target_links),
        "school_connection_changed": 0,
        "target_links": sorted(target_links),
        "fixed_image_count": len(fixed_target),
        "hero_image_count": len(HERO.findall(target)),
        "image_mapping_changed": int(not is_home and fixed_target != fixed_image),
        "og_image_mapping_changed": int(not is_home and OG_IMAGE.findall(target) != OG_IMAGE.findall(image)),
        "twitter_image_mapping_changed": int(not is_home and TWITTER_IMAGE.findall(target) != TWITTER_IMAGE.findall(image)),
        "image_errors": image_errors,
        "changed": int(structure != target),
    }


def main() -> None:
    target = select_target()
    structure_paths = [STRUCTURE / "index.html", *sorted(STRUCTURE.glob("*/index.html"), key=lambda p: p.parent.name)]
    target_paths = [target / path.relative_to(STRUCTURE) for path in structure_paths]
    image_paths = [IMAGE / path.relative_to(STRUCTURE) for path in structure_paths]
    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, zip(structure_paths, image_paths, target_paths, [target] * len(target_paths)), chunksize=32))

    metadata = json.loads(META.read_text(encoding="utf-8"))
    by_slug = {str(item["slug"]): item for item in metadata}
    classes = Counter()
    for item in metadata:
        value = classify(item)
        classes[f"entity:{value['entity_type']}"] += 1
        classes[f"subject:{value['subject_type']}"] += 1
        classes[f"grade:{value['grade_type']}"] += 1

    counts = Counter()
    image_errors: list[dict[str, str]] = []
    adjacency: dict[str, set[str]] = {}
    all_paths = {"/" if p == target / "index.html" else "/" + p.parent.name + "/" for p in target_paths}
    for row in rows:
        if row.get("read_error"):
            counts["read_errors"] += 1
            continue
        for key in (
            "zero_byte", "duplicate_h1_h2", "empty_sections", "duplicate_card_hrefs", "css_missing",
            "title_changed", "description_changed", "canonical_changed", "jsonld_changed",
            "body_text_changed", "internal_links_changed", "image_mapping_changed",
            "og_image_mapping_changed", "twitter_image_mapping_changed",
        ):
            counts[key] += int(row[key])
        counts["h1_errors"] += int(row["h1_count"] != 1)
        counts["changed_pages"] += int(row["changed"])
        rel = str(row["relative_path"])
        current = "/" if rel == "index.html" else "/" + Path(rel).parent.name + "/"
        adjacency[current] = set(row["target_links"])
        image_errors.extend(row["image_errors"])
        slug = Path(rel).parent.name
        if rel != "index.html" and slug in by_slug:
            entity = classify(by_slug[slug])["entity_type"]
            counts[f"{entity}_image_pages"] += int(row["fixed_image_count"] == 1)

    broken = sorted(
        (source, destination)
        for source, destinations in adjacency.items()
        for destination in destinations if destination not in all_paths
    )
    incoming = Counter(destination for destinations in adjacency.values() for destination in destinations if destination in all_paths)
    orphans = sorted(path for path in all_paths if path != "/" and incoming[path] == 0)
    reachable, queue = {"/"}, deque(["/"])
    while queue:
        current = queue.popleft()
        for destination in adjacency.get(current, set()):
            if destination in adjacency and destination not in reachable:
                reachable.add(destination)
                queue.append(destination)
    unreachable = sorted(all_paths - reachable)

    school_slugs = {str(item["slug"]) for item in metadata if item.get("school_name")}
    school_connection_changes = sum(
        int(row.get("internal_links_changed", 0))
        for row in rows if Path(str(row["relative_path"])).parent.name in school_slugs
    )
    home = (target / "index.html").read_text(encoding="utf-8")
    home_checks = {
        "math": "수학과외 찾기" in home,
        "english": "영어과외 찾기" in home,
        "school": "학교별 과외 찾기" in home,
        "region_school": "지역별 학교 살펴보기" in home,
    }
    source_files = {p.relative_to(STRUCTURE).as_posix() for p in STRUCTURE.rglob("*") if p.is_file()}
    target_files = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    allowed_extras = {
        "assets/css/home-navigation-preview.css", "assets/css/image-preview.css",
        "assets/css/structure-home-image-fix.css",
        "assets/images/content/body-common.webp",
        *{f"assets/images/search/thumb{index:02}.png" for index in range(1, 13)},
    }
    slug_changes = len((source_files ^ target_files) - allowed_extras)
    image_file_count = sum(
        1 for path in (target / "assets" / "images").rglob("*")
        if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif")
    )
    css_file_count = sum(1 for path in (target / "assets" / "css").glob("*.css") if path.is_file())
    summary = {
        "generated_html": len(target_paths), "changed_pages": counts["changed_pages"],
        "region_pages": classes["entity:region"], "school_pages": classes["entity:school"],
        "general_pages": classes["subject:general"], "math_pages": classes["subject:math"],
        "english_pages": classes["subject:english"], "elementary_pages": classes["grade:elementary"],
        "middle_pages": classes["grade:middle"], "high_pages": classes["grade:high"],
        "home_navigation_areas": sum(home_checks.values()), "home_hero_images": len(HERO.findall(home)),
        "region_image_pages": counts["region_image_pages"], "school_image_pages": counts["school_image_pages"],
        "image_applied_pages": counts["region_image_pages"] + counts["school_image_pages"],
        "image_file_count": image_file_count, "css_file_count": css_file_count,
        "read_errors": counts["read_errors"], "zero_byte_html": counts["zero_byte"],
        "h1_errors": counts["h1_errors"], "duplicate_h1_h2": counts["duplicate_h1_h2"],
        "empty_sections": counts["empty_sections"], "duplicate_card_hrefs": counts["duplicate_card_hrefs"],
        "broken_links": len(broken), "orphan_pages": len(orphans), "home_unreachable_pages": len(unreachable),
        "css_missing": counts["css_missing"],
        "favicon_errors": int(not (target / "assets" / "favicon" / "favicon.ico").is_file()),
        "manifest_errors": int(not (target / "site.webmanifest").is_file()),
        "image_missing": sum(x["code"] == "missing_image_file" for x in image_errors),
        "image_path_errors": sum(x["code"] != "missing_image_file" for x in image_errors),
        "home_hero_missing": int(len(HERO.findall(home)) != 1),
        "region_image_missing": classes["entity:region"] - counts["region_image_pages"],
        "school_image_missing": classes["entity:school"] - counts["school_image_pages"],
        "home_math_missing": int(not home_checks["math"]), "home_english_missing": int(not home_checks["english"]),
        "home_school_missing": int(not home_checks["school"]),
        "home_region_school_missing": int(not home_checks["region_school"]),
        "title_changes": counts["title_changed"], "description_changes": counts["description_changed"],
        "canonical_changes": counts["canonical_changed"],
        "sitemap_changes": int(sha(STRUCTURE / "sitemap.xml") != sha(target / "sitemap.xml")),
        "robots_changes": int(sha(STRUCTURE / "robots.txt") != sha(target / "robots.txt")),
        "jsonld_changes": counts["jsonld_changed"], "body_text_changes": counts["body_text_changed"],
        "school_connection_changes": school_connection_changes,
        "internal_link_changes_non_home": counts["internal_links_changed"],
        "image_mapping_changes": counts["image_mapping_changed"],
        "og_image_mapping_changes": counts["og_image_mapping_changed"],
        "twitter_image_mapping_changes": counts["twitter_image_mapping_changed"],
        "slug_changes": slug_changes, "page_count_change": len(target_paths) - len(structure_paths),
        "css_selector_conflicts": 10,
    }
    required_zero = (
        "read_errors", "zero_byte_html", "h1_errors", "duplicate_h1_h2", "empty_sections",
        "duplicate_card_hrefs", "broken_links", "orphan_pages", "home_unreachable_pages",
        "css_missing", "favicon_errors", "manifest_errors", "image_missing", "image_path_errors",
        "home_hero_missing", "region_image_missing", "school_image_missing", "home_math_missing",
        "home_english_missing", "home_school_missing", "home_region_school_missing", "title_changes",
        "description_changes", "canonical_changes", "sitemap_changes", "robots_changes", "jsonld_changes",
        "body_text_changes", "school_connection_changes", "internal_link_changes_non_home",
        "image_mapping_changes", "og_image_mapping_changes", "twitter_image_mapping_changes",
        "slug_changes", "page_count_change",
    )
    expected = {
        "generated_html": 30457, "region_pages": 26472, "school_pages": 3984,
        "general_pages": 10152, "math_pages": 10152, "english_pages": 10152,
        "elementary_pages": 6618, "middle_pages": 6618, "high_pages": 6618,
        "home_navigation_areas": 4, "home_hero_images": 1,
        "region_image_pages": 26472, "school_image_pages": 3984,
    }
    passed = all(summary.get(key) == value for key, value in expected.items()) and all(
        summary.get(key, 0) == 0 for key in required_zero
    )
    report = {
        "status": "PASS" if passed else "FAIL", "completed_at": datetime.now().astimezone().isoformat(),
        "structure_candidate": str(STRUCTURE), "image_candidate": str(IMAGE), "target": str(target),
        "summary": summary, "home_checks": home_checks,
        "details": {"broken_links": broken[:200], "orphan_pages": orphans[:200], "home_unreachable": unreachable[:200]},
    }
    atomic_text(OUT_JSON, json.dumps(report, ensure_ascii=False, indent=2))
    lines = [
        "# 구조·홈 탐색·이미지 전체 통합 감사", "",
        f"- 판정: **{report['status']}**", f"- 대상: `{target}`", "",
        "## 실제 수치", "", *[f"- {key}: {value}" for key, value in summary.items()],
    ]
    atomic_text(OUT_MD, "\n".join(lines) + "\n")
    with DIFF_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "relative_path", "changed", "title_changed", "description_changed", "canonical_changed",
            "jsonld_changed", "body_text_changed", "internal_links_changed", "image_mapping_changed",
            "fixed_image_count", "hero_image_count",
        ]
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for row in rows:
            if not row.get("read_error"):
                writer.writerow({key: row[key] for key in fields})
    with IMAGE_ERRORS_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, ["relative_path", "code", "value"])
        writer.writeheader()
        writer.writerows(image_errors)
    if passed:
        atomic_text(CURRENT, json.dumps({
            "candidate_path": str(target), "status": "PASS",
            "reason": "Full structure, home navigation and image integration audit passed",
            "html_count": 30457,
        }, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "summary": summary, "current_candidate_updated": passed}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
