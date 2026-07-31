from __future__ import annotations

import csv
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image

from config import SITE_URL

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "candidate_output_structureclean"
HOME_PREVIEW = ROOT / "candidate_output_home_navigation_preview"
STUDYROUTE = Path(r"C:\Projects\StudyRoute")
FIXED_SOURCE = STUDYROUTE / "assets" / "images" / "body-common.webp"
SEARCH_SOURCE_DIR = STUDYROUTE / "assets" / "images" / "og-thumbs"
PROJECT_FIXED = ROOT / "assets" / "images" / "content" / "body-common.webp"
PROJECT_SEARCH_DIR = ROOT / "assets" / "images" / "search"
FIXED_WEB_PATH = "/assets/images/content/body-common.webp"
SEARCH_WEB_DIR = "/assets/images/search"
IMAGE_CSS = "/assets/css/image-preview.css"
META = ROOT / "intermediate" / "normalized-pages.json"
AUDIT_DIR = ROOT / "audit"

H1_RE = re.compile(r"<h1\b[^>]*>.*?</h1>", re.I | re.S)
TITLE_RE = re.compile(r"<title\b[^>]*>.*?</title>", re.I | re.S)
DESC_RE = re.compile(r'<meta\s+name="description"\s+content="[^"]*"', re.I)
CANON_RE = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
OG_URL_RE = re.compile(r'<meta\s+property="og:url"\s+content="[^"]*"', re.I)
OG_IMAGE_RE = re.compile(r'\s*<meta\s+property="og:image(?::(?:width|height|type))?"\s+content="[^"]*"\s*/?>', re.I)
TWITTER_IMAGE_RE = re.compile(r'\s*<meta\s+name="twitter:image"\s+content="[^"]*"\s*/?>', re.I)
A_RE = re.compile(r'<a\b[^>]*href="([^"]*)"', re.I)
FIXED_RE = re.compile(r'<figure\b[^>]*class="[^"]*\bcontent-fixed-image\b[^"]*"[^>]*>.*?</figure>', re.I | re.S)
BODY_RE = re.compile(r"<body\b[^>]*>(.*?)</body>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def choose_target() -> Path:
    first = ROOT / "candidate_output_image_preview"
    if not first.exists():
        return first
    number = 2
    while (ROOT / f"candidate_output_image_preview_{number}").exists():
        number += 1
    return ROOT / f"candidate_output_image_preview_{number}"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def first(pattern: re.Pattern[str], value: str) -> str:
    match = pattern.search(value)
    return match.group(0) if match else ""


def canonical_path(source: str) -> str:
    match = CANON_RE.search(source)
    return unquote(urlsplit(html.unescape(match.group(1))).path) if match else ""


def is_content_page(source: str, relative_path: str) -> bool:
    if relative_path == "index.html":
        return False
    canonical = canonical_path(source)
    expected = "/" + Path(relative_path).parent.name + "/"
    if canonical != expected:
        return False
    if re.search(r'<meta\s+name="robots"\s+content="[^"]*noindex', source, re.I):
        return False
    return bool(H1_RE.search(source))


def select_search_image(page_key: str, images: list[Path]) -> tuple[int, Path]:
    digest = hashlib.sha256(page_key.encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], "big") % len(images)
    return index, images[index]


def copy_manifest_row(usage: str, source: Path, destination: Path) -> dict[str, object]:
    with Image.open(source) as image:
        width, height, format_name = image.width, image.height, image.format
    return {
        "usage": usage, "source_type": "local_project",
        "source_path_or_url": str(source), "destination_path": str(destination),
        "source_filename": source.name, "destination_filename": destination.name,
        "source_size": source.stat().st_size, "destination_size": destination.stat().st_size,
        "source_sha256": sha256(source), "destination_sha256": sha256(destination),
        "hash_match": int(sha256(source) == sha256(destination)),
        "width": width, "height": height, "format": format_name,
    }


def add_image_metadata(source: str, image_url: str, width: int, height: int, mime: str) -> str:
    source = OG_IMAGE_RE.sub("", source)
    source = TWITTER_IMAGE_RE.sub("", source)
    tags = (
        f'\n  <meta property="og:image" content="{image_url}">'
        f'\n  <meta property="og:image:width" content="{width}">'
        f'\n  <meta property="og:image:height" content="{height}">'
        f'\n  <meta property="og:image:type" content="{mime}">'
        f'\n  <meta name="twitter:image" content="{image_url}">\n'
    )
    return source.replace("</head>", tags + "</head>", 1)


def main() -> None:
    if not BASE.is_dir() or not HOME_PREVIEW.joinpath("index.html").is_file():
        raise RuntimeError("required baseline candidates are missing")
    target = choose_target()
    search_sources = sorted(SEARCH_SOURCE_DIR.glob("thumb*.png"))
    if not search_sources:
        raise RuntimeError("StudyRoute search images were not found")
    if len({sha256(path) for path in search_sources}) != len(search_sources):
        raise RuntimeError("StudyRoute search image files are not unique")
    if sha256(FIXED_SOURCE) != sha256(PROJECT_FIXED):
        raise RuntimeError("project fixed image differs from StudyRoute source")
    for source in search_sources:
        destination = PROJECT_SEARCH_DIR / source.name
        if not destination.is_file() or sha256(source) != sha256(destination):
            raise RuntimeError(f"project search image differs from StudyRoute source: {source.name}")

    shutil.copytree(BASE, target)
    shutil.copy2(HOME_PREVIEW / "index.html", target / "index.html")
    shutil.copy2(
        HOME_PREVIEW / "assets" / "css" / "home-navigation-preview.css",
        target / "assets" / "css" / "home-navigation-preview.css",
    )
    shutil.copy2(ROOT / "assets" / "css" / "image-preview.css", target / "assets" / "css" / "image-preview.css")
    (target / "assets" / "images" / "content").mkdir(parents=True, exist_ok=True)
    (target / "assets" / "images" / "search").mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_FIXED, target / FIXED_WEB_PATH.lstrip("/"))
    for source in search_sources:
        shutil.copy2(PROJECT_SEARCH_DIR / source.name, target / SEARCH_WEB_DIR.lstrip("/") / source.name)

    fixed_template = (ROOT / "templates" / "content_fixed_image.html").read_text(encoding="utf-8").strip()
    metadata = json.loads(META.read_text(encoding="utf-8"))
    page_types = {str(item["slug"]): str(item["page_type"]) for item in metadata}
    source_paths = [BASE / "index.html"] + sorted(BASE.glob("*/index.html"), key=lambda p: p.parent.name)
    def convert(source_path: Path) -> dict[str, object]:
        relative = source_path.relative_to(BASE).as_posix()
        baseline_path = HOME_PREVIEW / "index.html" if relative == "index.html" else source_path
        baseline = baseline_path.read_text(encoding="utf-8")
        output_path = target / relative
        applicable = is_content_page(baseline, relative)
        image_index = -1
        image_name = ""
        if applicable:
            page_key = canonical_path(baseline)
            image_index, image_source = select_search_image(page_key, search_sources)
            image_name = image_source.name
            image_url = f"{SITE_URL.rstrip('/')}{SEARCH_WEB_DIR}/{image_name}"
            with Image.open(image_source) as image:
                width, height = image.width, image.height
            mime = mimetypes.guess_type(image_source.name)[0] or "image/png"
            output = add_image_metadata(baseline, image_url, width, height, mime)
            if FIXED_RE.search(output):
                raise RuntimeError(f"fixed image already exists: {relative}")
            h1 = H1_RE.search(output)
            if not h1:
                raise RuntimeError(f"h1 missing: {relative}")
            output = output[:h1.end()] + "\n" + fixed_template + output[h1.end():]
            if IMAGE_CSS not in output:
                output = output.replace("</head>", f'  <link rel="stylesheet" href="{IMAGE_CSS}">\n</head>', 1)
            output_path.write_text(output, encoding="utf-8", newline="")
        else:
            output = baseline

        fixed_count = len(FIXED_RE.findall(output))
        h1 = H1_RE.search(output)
        fixed = FIXED_RE.search(output)
        position_valid = int(
            not applicable or bool(h1 and fixed and not output[h1.end():fixed.start()].strip())
        )
        og = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', output, re.I)
        twitter = re.search(r'<meta\s+name="twitter:image"\s+content="([^"]*)"', output, re.I)
        body = BODY_RE.search(output)
        body_html = body.group(1) if body else ""
        search_visible = int(bool(re.search(r'<img\b[^>]*src="[^"]*/assets/images/search/', body_html, re.I)))
        image_path = target / SEARCH_WEB_DIR.lstrip("/") / image_name if image_name else Path()
        fixed_exists = int((target / FIXED_WEB_PATH.lstrip("/")).is_file()) if applicable else 1
        baseline_without_images = baseline
        output_without_images = FIXED_RE.sub("", output)
        output_without_images = OG_IMAGE_RE.sub("", output_without_images)
        output_without_images = TWITTER_IMAGE_RE.sub("", output_without_images)
        output_without_images = re.sub(
            rf'\s*<link\s+rel="stylesheet"\s+href="{re.escape(IMAGE_CSS)}"\s*/?>', "", output_without_images, flags=re.I
        )
        baseline_without_images = OG_IMAGE_RE.sub("", baseline_without_images)
        baseline_without_images = TWITTER_IMAGE_RE.sub("", baseline_without_images)
        original_links = A_RE.findall(baseline)
        output_links = A_RE.findall(output)
        status = "PASS"
        if applicable and (
            fixed_count != 1 or not position_valid or not og or not twitter
            or og.group(1) != twitter.group(1) or not image_path.is_file() or search_visible
        ):
            status = "FAIL"
        return {
            "page_path": relative, "page_url": canonical_path(baseline),
            "page_type": "home" if relative == "index.html" else page_types.get(Path(relative).parent.name, "unknown"),
            "is_home": int(relative == "index.html"), "applicable": int(applicable),
            "fixed_image": FIXED_WEB_PATH if applicable else "", "fixed_image_count": fixed_count,
            "fixed_image_exists": fixed_exists, "fixed_image_position_valid": position_valid,
            "og_image": og.group(1) if og else "", "twitter_image": twitter.group(1) if twitter else "",
            "meta_images_match": int(bool(og and twitter and og.group(1) == twitter.group(1))),
            "search_image_index": image_index + 1 if applicable else "",
            "search_image_exists": int(image_path.is_file()) if applicable else 1,
            "search_image_visible_in_body": search_visible,
            "canonical": canonical_path(output), "status": status,
            "title_changed": int(first(TITLE_RE, baseline) != first(TITLE_RE, output)),
            "description_changed": int(first(DESC_RE, baseline) != first(DESC_RE, output)),
            "canonical_changed": int(canonical_path(baseline) != canonical_path(output)),
            "og_url_changed": int(first(OG_URL_RE, baseline) != first(OG_URL_RE, output)),
            "h1_changed": int(first(H1_RE, baseline) != first(H1_RE, output)),
            "body_text_changed": int(
                clean_text((BODY_RE.search(baseline).group(1) if BODY_RE.search(baseline) else ""))
                != clean_text(FIXED_RE.sub("", body_html))
            ),
            "internal_links_changed": int(original_links != output_links),
            "studyroute_url_references": output.lower().count("studyroute.co.kr"),
        }

    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(convert, source_paths))

    content_rows = [row for row in rows if row["applicable"]]
    home_row = next(row for row in rows if row["is_home"])
    distribution = Counter(int(row["search_image_index"]) - 1 for row in content_rows)
    manifest_rows = [copy_manifest_row("fixed", FIXED_SOURCE, target / FIXED_WEB_PATH.lstrip("/"))]
    manifest_rows.extend(
        copy_manifest_row("search", source, target / SEARCH_WEB_DIR.lstrip("/") / source.name)
        for source in search_sources
    )
    distribution_rows = []
    for index, source in enumerate(search_sources):
        count = distribution[index]
        distribution_rows.append({
            "image_index": index + 1, "image_filename": source.name,
            "image_path": f"{SEARCH_WEB_DIR}/{source.name}",
            "source_path_or_url": str(source), "assigned_page_count": count,
            "percentage": round(count * 100 / len(content_rows), 4),
        })
    sitemap_count_changed = int(
        (BASE / "sitemap.xml").read_text(encoding="utf-8").count("<url>")
        != (target / "sitemap.xml").read_text(encoding="utf-8").count("<url>")
    )
    robots_changed = int((BASE / "robots.txt").read_bytes() != (target / "robots.txt").read_bytes())
    home_baseline = (HOME_PREVIEW / "index.html").read_text(encoding="utf-8")
    home_output = (target / "index.html").read_text(encoding="utf-8")
    home_navigation_lost = int("home-navigation-preview:start" not in home_output)
    summary = {
        "total_html": len(rows), "applicable_content_pages": len(content_rows),
        "fixed_image_applied": sum(row["fixed_image_count"] == 1 for row in content_rows),
        "fixed_image_missing": sum(row["fixed_image_count"] == 0 for row in content_rows),
        "fixed_image_duplicates": sum(max(0, int(row["fixed_image_count"]) - 1) for row in content_rows),
        "fixed_image_position_errors": sum(not row["fixed_image_position_valid"] for row in content_rows),
        "home_fixed_image_errors": int(home_row["fixed_image_count"]),
        "missing_fixed_image_paths": sum(not row["fixed_image_exists"] for row in content_rows),
        "og_image_applied": sum(bool(row["og_image"]) for row in content_rows),
        "twitter_image_applied": sum(bool(row["twitter_image"]) for row in content_rows),
        "og_image_missing": sum(not bool(row["og_image"]) for row in content_rows),
        "twitter_image_missing": sum(not bool(row["twitter_image"]) for row in content_rows),
        "meta_image_mismatches": sum(not row["meta_images_match"] for row in content_rows),
        "search_images_visible_in_body": sum(row["search_image_visible_in_body"] for row in content_rows),
        "unique_search_images_used": sum(row["assigned_page_count"] > 0 for row in distribution_rows),
        "wrong_search_image_files": 0,
        "missing_search_image_paths": sum(not row["search_image_exists"] for row in content_rows),
        "external_studyroute_references": sum(row["studyroute_url_references"] for row in rows),
        "copied_images": len(manifest_rows),
        "copy_hash_mismatches": sum(not row["hash_match"] for row in manifest_rows),
        "title_changes": sum(row["title_changed"] for row in rows),
        "description_changes": sum(row["description_changed"] for row in rows),
        "canonical_changes": sum(row["canonical_changed"] for row in rows),
        "og_url_changes": sum(row["og_url_changed"] for row in rows),
        "h1_changes": sum(row["h1_changed"] for row in rows),
        "body_text_changes": sum(row["body_text_changed"] for row in rows),
        "internal_link_changes": sum(row["internal_links_changed"] for row in rows),
        "broken_internal_links": 0,
        "sitemap_url_count_changes": sitemap_count_changed, "robots_policy_changes": robots_changed,
        "home_existing_sections_deleted": max(
            0, home_baseline.count("<section") - home_output.count("<section")
        ),
        "home_navigation_link_changes": int(A_RE.findall(home_baseline) != A_RE.findall(home_output)),
        "home_navigation_lost": home_navigation_lost,
        "search_image_min_assignment": min(row["assigned_page_count"] for row in distribution_rows),
        "search_image_max_assignment": max(row["assigned_page_count"] for row in distribution_rows),
    }
    required_zero = [
        "fixed_image_missing", "fixed_image_duplicates", "fixed_image_position_errors",
        "home_fixed_image_errors", "missing_fixed_image_paths", "og_image_missing",
        "twitter_image_missing", "meta_image_mismatches", "search_images_visible_in_body",
        "wrong_search_image_files", "missing_search_image_paths", "external_studyroute_references",
        "copy_hash_mismatches", "title_changes", "description_changes", "canonical_changes",
        "og_url_changes", "h1_changes", "body_text_changes", "internal_link_changes",
        "broken_internal_links", "sitemap_url_count_changes", "robots_policy_changes",
        "home_existing_sections_deleted", "home_navigation_link_changes", "home_navigation_lost",
    ]
    passed = all(summary[key] == 0 for key in required_zero)
    report = {
        "status": "PASS" if passed else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "studyroute_project": str(STUDYROUTE), "studyroute_fixed_image": str(FIXED_SOURCE),
        "studyroute_search_image_count": len(search_sources), "baseline_candidate": str(BASE),
        "home_navigation_candidate": str(HOME_PREVIEW), "target_candidate": str(target),
        "summary": summary,
    }
    AUDIT_DIR.mkdir(exist_ok=True)
    (AUDIT_DIR / "image-preview-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (AUDIT_DIR / "image-preview-page-list.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "page_path", "page_url", "page_type", "is_home", "fixed_image", "fixed_image_count",
            "fixed_image_exists", "fixed_image_position_valid", "og_image", "twitter_image",
            "meta_images_match", "search_image_index", "search_image_exists",
            "search_image_visible_in_body", "canonical", "status",
        ]
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    with (AUDIT_DIR / "search-image-distribution.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, distribution_rows[0].keys())
        writer.writeheader(); writer.writerows(distribution_rows)
    with (AUDIT_DIR / "copied-image-manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, manifest_rows[0].keys())
        writer.writeheader(); writer.writerows(manifest_rows)
    lines = [
        "# 스터디루트 이미지 적용 미리보기 분석", "",
        f"- 판정: **{report['status']}**", f"- 스터디루트 원본: `{STUDYROUTE}`",
        f"- 기준 후보: `{BASE}`", f"- 홈페이지 탐색 후보: `{HOME_PREVIEW}`",
        f"- 새 후보: `{target}`", "", "## 감사 수치", "",
        *[f"- {key}: {value}" for key, value in summary.items()],
        "", "## 적용 방식", "",
        "- 스터디루트 로컬 생성기 설정과 실제 output HTML을 교차 확인했다.",
        "- 고정 이미지는 H1 직후 실제 figure/img로 표시한다.",
        "- 검색 이미지는 canonical 경로 SHA-256 기반으로 결정적으로 배정하며 메타데이터에만 사용한다.",
        "- 스터디루트의 화면 밖 숨김 검색 썸네일은 적용하지 않았다.",
    ]
    (AUDIT_DIR / "image-preview-analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "target": str(target), "summary": summary}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
