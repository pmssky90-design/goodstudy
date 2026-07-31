from __future__ import annotations

import csv
import html
import json
import re
import shutil
import unicodedata
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output"
TARGET = ROOT / "candidate_output_titlefix"
AUDIT = ROOT / "audit"
NORMALIZED = ROOT / "intermediate" / "normalized-pages.json"
DETAILS = AUDIT / "duplicate-title-details.csv"
FIX_LOG = AUDIT / "title-fix-log.csv"
SAMPLES = AUDIT / "title-fix-samples.txt"
REPORT = AUDIT / "title-duplicate-audit.json"
SITE_URL = "https://goodstudy.co.kr"
SITE_NAMES = ("좋은공부", "GoodStudy")
MAX_TITLE_LENGTH = 100


def normalized_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in value if character.isalnum())


def groups(pages: list[dict[str, object]], normal: bool = False) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = defaultdict(list)
    for page in pages:
        title = str(page["title"])
        result[normalized_title(title) if normal else title].append(page)
    return {key: value for key, value in result.items() if len(value) > 1}


def context_label(page: dict[str, object]) -> str:
    values = [str(page.get(key) or "").strip() for key in ("province", "city", "locality", "village")]
    compact: list[str] = []
    for value in values:
        if value and value not in compact:
            compact.append(value)
    return " ".join(compact)


def title_prefix(page: dict[str, object]) -> str:
    context = context_label(page)
    page_type = str(page["page_type"])
    return f"{context} {page_type}".strip()


def fix_title(page: dict[str, object]) -> str:
    old = str(page["title"]).strip()
    prefix = title_prefix(page)
    first_space = old.find(" ")
    suffix = old[first_space:] if first_space >= 0 else ""
    return re.sub(r"\s+", " ", prefix + suffix).strip()


def type_conflict(page: dict[str, object], title: str) -> list[str]:
    page_type = str(page["page_type"])
    issues: list[str] = []
    if "수학" in page_type and "영어과외" in title:
        issues.append("math_page_uses_english_title")
    if "영어" in page_type and "수학과외" in title:
        issues.append("english_page_uses_math_title")
    required = "과외"
    if "수학" in page_type:
        required = "수학과외"
    elif "영어" in page_type:
        required = "영어과외"
    if required not in title:
        issues.append("page_type_keyword_missing")
    return issues


def replace_title_fields(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    escaped_old = html.escape(old, quote=True)
    escaped_new = html.escape(new, quote=True)
    replacements = (
        (f"<title>{escaped_old}</title>", f"<title>{escaped_new}</title>"),
        (f'<meta property="og:title" content="{escaped_old}">', f'<meta property="og:title" content="{escaped_new}">'),
        (f'<meta name="twitter:title" content="{escaped_old}">', f'<meta name="twitter:title" content="{escaped_new}">'),
        (f"<article><h1>{escaped_old}</h1>", f"<article><h1>{escaped_new}</h1>"),
    )
    for before, after in replacements:
        if before not in text:
            raise RuntimeError(f"제목 필드를 찾을 수 없습니다: {path} / {before[:40]}")
        text = text.replace(before, after, 1)
    path.write_text(text, encoding="utf-8")


def inspect_html(root: Path) -> dict[str, object]:
    html_files = [root / "index.html"] + [
        entry / "index.html" for entry in root.iterdir() if entry.is_dir() and (entry / "index.html").is_file()
    ]
    title_re = re.compile(r"<title>(.*?)</title>", re.I | re.S)
    canonical_re = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
    description_re = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
    href_re = re.compile(r'<a\b[^>]*\bhref="([^"]+)"', re.I)

    def one(path: Path) -> tuple[str, str, bool, str, set[str], list[str]]:
        text = path.read_text(encoding="utf-8")
        current = "/" if path == root / "index.html" else f"/{path.parent.name}/"
        title_match = title_re.search(text)
        canonical_match = canonical_re.search(text)
        description_match = description_re.search(text)
        targets: set[str] = set()
        broken: list[str] = []
        for href in href_re.findall(text):
            if href.startswith(SITE_URL):
                href = unquote(urlparse(href).path)
            if not href.startswith("/") or href.startswith("//"):
                continue
            targets.add(href)
            target = root / "index.html" if href == "/" else root / href.strip("/") / "index.html"
            if not target.is_file():
                broken.append(f"{current} -> {href}")
        return (
            title_match.group(1).strip() if title_match else "",
            canonical_match.group(1) if canonical_match else "",
            not description_match or not description_match.group(1).strip(),
            current,
            targets,
            broken,
        )

    titles: list[str] = []
    canonicals: list[str] = []
    empty_descriptions = 0
    adjacency: dict[str, set[str]] = {}
    broken: list[str] = []
    with ThreadPoolExecutor(max_workers=16) as executor:
        for title, canonical, empty_description, current, targets, local_broken in executor.map(one, html_files, chunksize=64):
            titles.append(title)
            canonicals.append(canonical)
            empty_descriptions += int(empty_description)
            adjacency[current] = targets
            broken.extend(local_broken)
    reachable = {"/"}
    queue = deque(["/"])
    while queue:
        for target in adjacency.get(queue.popleft(), set()):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    sitemap_urls = re.findall(r"<loc>(.*?)</loc>", (root / "sitemap.xml").read_text(encoding="utf-8"))
    individual_titles = [title for path, title in zip(html_files, titles) if path != root / "index.html"]
    return {
        "html_count": len(html_files),
        "titles": titles,
        "canonicals": canonicals,
        "sitemap_urls": sitemap_urls,
        "duplicate_title_excess": len(titles) - len(set(titles)),
        "empty_title": sum(not title for title in titles),
        "empty_description": empty_descriptions,
        "broken_internal_links": len(broken),
        "orphan_pages": sum(
            not any(node in targets for source, targets in adjacency.items() if source != node)
            for node in adjacency if node != "/"
        ),
        "home_unreachable_pages": len(set(adjacency) - reachable),
        "duplicate_canonical": len(canonicals) - len(set(canonicals)),
        "duplicate_sitemap": len(sitemap_urls) - len(set(sitemap_urls)),
        "site_name_in_title": sum(any(name in title for name in SITE_NAMES) for title in individual_titles),
        "nationwide_in_title": sum("전국과외" in title for title in individual_titles),
        "www_urls": sum("://www." in value for value in canonicals + sitemap_urls),
        "http_urls": sum(value.startswith("http://") for value in canonicals + sitemap_urls),
        "index_urls": sum("index.html" in value for value in canonicals + sitemap_urls),
        "double_slash_paths": sum("//" in urlparse(value).path for value in canonicals + sitemap_urls),
    }


def main() -> None:
    for required in (SOURCE, NORMALIZED):
        if not required.exists():
            raise FileNotFoundError(required)
    pages: list[dict[str, object]] = json.loads(NORMALIZED.read_text(encoding="utf-8"))
    exact_before = groups(pages)
    normalized_before = groups(pages, normal=True)
    normalized_only_before = {
        key: value for key, value in normalized_before.items()
        if len({str(page["title"]) for page in value}) > 1
    }
    duplicate_pages = {str(page["node_id"]): page for values in exact_before.values() for page in values}
    page_type_collision_groups = sum(len({str(page["page_type"]) for page in values}) > 1 for values in exact_before.values())

    fixes: list[dict[str, str]] = []
    review: list[dict[str, str]] = []
    details: list[dict[str, str]] = []
    for group_id, (title, values) in enumerate(sorted(exact_before.items()), 1):
        for page in values:
            context = context_label(page)
            missing_context = bool(context and not str(title).startswith(context))
            conflicts = type_conflict(page, title)
            reasons = ["exact_duplicate"]
            if missing_context:
                reasons.append("upper_region_missing")
            reasons.extend(conflicts)
            new_title = fix_title(page) if missing_context or conflicts or title == str(page["slug"]) else title
            record = {
                "group_id": str(group_id), "node_id": str(page["node_id"]), "page_type": str(page["page_type"]),
                "slug": str(page["slug"]), "province": str(page["province"]), "city": str(page["city"]),
                "locality": str(page["locality"]), "school_name": str(page["school_name"]),
                "old_title": title, "new_title": new_title, "reasons": "|".join(reasons),
            }
            details.append(record)
            if new_title != title:
                fixes.append(record)
                page["title"] = new_title
            else:
                review.append(record)

    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(SOURCE, TARGET)
    by_node = {str(page["node_id"]): page for page in pages}
    for record in fixes:
        path = TARGET / record["slug"] / "index.html"
        replace_title_fields(path, record["old_title"], record["new_title"])

    fieldnames = ["group_id", "node_id", "page_type", "slug", "province", "city", "locality",
                  "school_name", "old_title", "new_title", "reasons"]
    with DETAILS.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(details)
    with FIX_LOG.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(fixes)
    SAMPLES.write_text(
        "\n\n".join(
            f"[{index}] {item['page_type']} / {item['province']} {item['city']} {item['locality']}\n"
            f"OLD: {item['old_title']}\nNEW: {item['new_title']}\nREASON: {item['reasons']}"
            for index, item in enumerate(fixes[:50], 1)
        ) + "\n", encoding="utf-8",
    )

    exact_after = groups(pages)
    normalized_after = groups(pages, normal=True)
    before_audit = inspect_html(SOURCE)
    after_audit = inspect_html(TARGET)
    source_slugs = {path.name for path in SOURCE.iterdir() if path.is_dir() and (path / "index.html").is_file()}
    target_slugs = {path.name for path in TARGET.iterdir() if path.is_dir() and (path / "index.html").is_file()}
    slug_changes = len(source_slugs.symmetric_difference(target_slugs))
    canonical_changes = len(set(before_audit["canonicals"]).symmetric_difference(set(after_audit["canonicals"])))
    sitemap_changes = len(set(before_audit["sitemap_urls"]).symmetric_difference(set(after_audit["sitemap_urls"])))
    title_slug_equal_after = sum(str(page["title"]) == str(page["slug"]) for page in pages)
    type_conflicts_after = sum(bool(type_conflict(page, str(page["title"]))) for page in pages)
    title_too_long = sum(len(str(page["title"])) > MAX_TITLE_LENGTH for page in pages)

    immutable_relation_keys = ("node_id", "slug", "canonical_url", "page_type", "primary_parent_id",
                               "children_ids", "school_name", "school_address", "fallback_level")
    relation_changes = 0
    school_connection_changes = 0
    for original in json.loads(NORMALIZED.read_text(encoding="utf-8")):
        fixed = by_node[str(original["node_id"])]
        relation_changes += int(any(original[key] != fixed[key] for key in immutable_relation_keys))
        if original["school_name"]:
            school_connection_changes += int(any(original[key] != fixed[key] for key in ("primary_parent_id", "fallback_level")))

    report = {
        "existing_duplicate_title_groups": len(exact_before),
        "existing_duplicate_title_pages": sum(len(values) for values in exact_before.values()),
        "existing_duplicate_title_excess": sum(len(values) - 1 for values in exact_before.values()),
        "exact_duplicate_groups": len(exact_before),
        "normalized_only_duplicate_groups": len(normalized_only_before),
        "normalized_duplicate_groups_before": len(normalized_before),
        "page_type_collision_groups_before": page_type_collision_groups,
        "no_fix_needed_pages": len(pages) - len(fixes) - len(review),
        "unchanged_pages": len(pages) - len(fixes),
        "actual_fixed_pages": len(fixes),
        "review_required_pages": len(review),
        "exact_duplicate_groups_after": len(exact_after),
        "exact_duplicate_pages_after": sum(len(values) for values in exact_after.values()),
        "normalized_duplicate_groups_after": len(normalized_after),
        "normalized_duplicate_pages_after": sum(len(values) for values in normalized_after.values()),
        "title_equals_slug_remaining": title_slug_equal_after,
        "page_type_conflicts_after": type_conflicts_after,
        "titles_over_max_length": title_too_long,
        "slug_changes": slug_changes,
        "canonical_changes": canonical_changes,
        "sitemap_url_changes": sitemap_changes,
        "page_count_change": int(after_audit["html_count"]) - int(before_audit["html_count"]),
        "node_or_relation_changes": relation_changes,
        "school_connection_changes": school_connection_changes,
        "before_audit": {key: value for key, value in before_audit.items() if key not in ("titles", "canonicals", "sitemap_urls")},
        "after_audit": {key: value for key, value in after_audit.items() if key not in ("titles", "canonicals", "sitemap_urls")},
        "target": str(TARGET),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    fatal = {
        "html_count": after_audit["html_count"] != 30457,
        "broken_internal_links": bool(after_audit["broken_internal_links"]),
        "orphan_pages": bool(after_audit["orphan_pages"]),
        "home_unreachable_pages": bool(after_audit["home_unreachable_pages"]),
        "duplicate_canonical": bool(after_audit["duplicate_canonical"]),
        "duplicate_sitemap": bool(after_audit["duplicate_sitemap"]),
        "empty_title": bool(after_audit["empty_title"]),
        "empty_description": bool(after_audit["empty_description"]),
        "slug_changes": bool(slug_changes),
        "canonical_changes": bool(canonical_changes),
        "sitemap_changes": bool(sitemap_changes),
        "school_connection_changes": bool(school_connection_changes),
        "site_name_in_title": bool(after_audit["site_name_in_title"]),
        "nationwide_in_title": bool(after_audit["nationwide_in_title"]),
        "www_urls": bool(after_audit["www_urls"]),
        "http_urls": bool(after_audit["http_urls"]),
        "index_urls": bool(after_audit["index_urls"]),
        "double_slash_paths": bool(after_audit["double_slash_paths"]),
    }
    failures = [key for key, failed in fatal.items() if failed]
    if failures:
        raise RuntimeError("titlefix 검증 실패: " + ", ".join(failures))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
