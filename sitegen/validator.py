from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
import re
from urllib.parse import unquote, urlparse

from config import CANDIDATE_OUTPUT_DIR, SITE_NAME, SITE_NAME_EN, SITE_URL
from sitegen.models import Page


class ValidationError(RuntimeError):
    pass


def preflight(pages: list[Page]) -> dict[str, object]:
    ids = {p.node_id for p in pages}
    slugs = [p.slug for p in pages]
    canonicals = [SITE_URL + "/" + p.slug + "/" for p in pages]
    errors: list[str] = []
    tests = {
        "empty_slugs": sum(not p.slug for p in pages),
        "empty_titles": sum(not p.title for p in pages),
        "empty_bodies": sum(not p.body_html for p in pages),
        "duplicate_slugs": len(slugs) - len(set(slugs)),
        "duplicate_canonicals": len(canonicals) - len(set(canonicals)),
        "duplicate_node_ids": len(pages) - len(ids),
        "missing_parents": sum(p.primary_parent_id != "home" and p.primary_parent_id not in ids for p in pages),
        "missing_related": sum(node not in ids for p in pages for node in p.related_nodes),
        "site_name_in_title": sum(SITE_NAME in p.title or SITE_NAME_EN in p.title for p in pages),
        "forbidden_nationwide": sum("전국과외" in (p.title + p.body_html) for p in pages),
        "school_failure_reason_missing": 0,
    }
    parent = {p.node_id: p.primary_parent_id for p in pages}
    cycle_count = 0
    for node_id in ids:
        seen: set[str] = set()
        current = node_id
        while current != "home" and current in parent:
            if current in seen:
                cycle_count += 1
                break
            seen.add(current)
            current = parent[current]
    tests["parent_cycles"] = cycle_count
    errors.extend(key for key, value in tests.items() if value)
    return {"passed": not errors, "errors": errors, "checks": tests}


def audit_output(pages: list[Page]) -> dict[str, object]:
    html_files = sorted(CANDIDATE_OUTPUT_DIR.rglob("*.html"))
    canonical_values: list[str] = []
    titles: list[str] = []
    page_titles: list[str] = []
    broken: list[str] = []
    empty_descriptions = 0
    adjacency: dict[str, set[str]] = {}
    title_re = re.compile(r"<title>(.*?)</title>", re.I | re.S)
    canonical_re = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
    description_re = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
    href_re = re.compile(r'<a\b[^>]*\bhref="([^"]+)"', re.I)
    def inspect(path):
        text = path.read_text(encoding="utf-8")
        canonical_match = canonical_re.search(text)
        title_match = title_re.search(text)
        description_match = description_re.search(text)
        current = "/" if path == CANDIDATE_OUTPUT_DIR / "index.html" else "/" + path.parent.name + "/"
        targets: set[str] = set()
        local_broken: list[str] = []
        for href in href_re.findall(text):
            if href.startswith(SITE_URL):
                parsed = urlparse(href)
                href = unquote(parsed.path)
            if not href.startswith("/") or href.startswith("//"):
                continue
            targets.add(href)
            target = CANDIDATE_OUTPUT_DIR / href.strip("/") / "index.html" if href != "/" else CANDIDATE_OUTPUT_DIR / "index.html"
            if not target.is_file():
                local_broken.append(f"{current} -> {href}")
        return (canonical_match.group(1) if canonical_match else "",
                title_match.group(1).strip() if title_match else "",
                int(not description_match or not description_match.group(1).strip()),
                current, targets, local_broken)
    with ThreadPoolExecutor(max_workers=16) as executor:
        for canonical_value, title, empty_description, current, targets, local_broken in executor.map(inspect, html_files, chunksize=64):
            canonical_values.append(canonical_value)
            titles.append(title)
            if current != "/":
                page_titles.append(title)
            empty_descriptions += empty_description
            adjacency[current] = targets
            broken.extend(local_broken)
    reachable = {"/"}
    queue = deque(["/"])
    while queue:
        for target in adjacency.get(queue.popleft(), set()):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    expected = set(adjacency)
    sitemap_text = (CANDIDATE_OUTPUT_DIR / "sitemap.xml").read_text(encoding="utf-8")
    sitemap_urls = re.findall(r"<loc>(.*?)</loc>", sitemap_text)
    return {
        "html_count": len(html_files), "sitemap_url_count": len(sitemap_urls),
        "canonical_count": len(canonical_values), "duplicate_canonical": len(canonical_values) - len(set(canonical_values)),
        "duplicate_title": len(titles) - len(set(titles)), "empty_title": sum(not t for t in titles),
        "empty_description": empty_descriptions, "site_name_in_title": sum(SITE_NAME in t or SITE_NAME_EN in t for t in page_titles),
        "forbidden_nationwide_title": sum("전국과외" in t for t in titles),
        "broken_internal_links": len(broken), "broken_samples": broken[:20],
        "orphan_pages": sum(not any(node in targets for source, targets in adjacency.items() if source != node) for node in expected if node != "/"),
        "home_unreachable_pages": len(expected - reachable), "duplicate_sitemap": len(sitemap_urls) - len(set(sitemap_urls)),
        "www_urls": sum("://www." in url for url in canonical_values + sitemap_urls),
        "http_urls": sum(url.startswith("http://") for url in canonical_values + sitemap_urls),
        "index_urls": sum("index.html" in url for url in canonical_values + sitemap_urls),
        "double_slash_paths": sum("//" in urlparse(url).path for url in canonical_values + sitemap_urls),
    }
