from __future__ import annotations

import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_school_pyramid_navigation_bottom_links_breadcrumb_bottom"
OUTPUT = ROOT / "output"
AUDIT = ROOT / "audit" / "output-promotion-audit.json"
REPORT = ROOT / "audit" / "output-promotion-audit.md"

TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
DESC = re.compile(
    r'<meta\b(?=[^>]*\bname=["\']description["\'])[^>]*\bcontent=(["\'])(.*?)\1[^>]*>',
    re.I | re.S,
)
CANON = re.compile(
    r'<link\b(?=[^>]*\brel=["\']canonical["\'])[^>]*\bhref=(["\'])(.*?)\1[^>]*>',
    re.I | re.S,
)
JSONLD = re.compile(
    r'<script\b(?=[^>]*\btype=["\']application/ld\+json["\'])[^>]*>(.*?)</script>',
    re.I | re.S,
)
BREADCRUMB = re.compile(
    r'<nav\b(?=[^>]*\bclass="[^"]*\bbreadcrumb\b[^"]*")[^>]*>.*?</nav>',
    re.I | re.S,
)
BOTTOM = re.compile(
    r'<section\b[^>]*\bclass="[^"]*\bregion-bottom-navigation\b[^"]*"[^>]*>',
    re.I,
)
ANCHOR = re.compile(r'<a\b[^>]*\bhref=(["\'])(.*?)\1', re.I | re.S)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def html_target(source_page: str, href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        if parts.netloc not in {"goodstudy.co.kr", "www.goodstudy.co.kr"}:
            return None
        path = parts.path or "/"
    else:
        base = "https://goodstudy.co.kr/" + (
            "" if source_page == "index.html" else source_page.removesuffix("index.html")
        )
        path = urlsplit(urljoin(base, href)).path
    path = unquote(path).replace("\\", "/")
    while "//" in path:
        path = path.replace("//", "/")
    if path == "/":
        return "index.html"
    relative = path.lstrip("/")
    if relative.endswith("/"):
        return relative + "index.html"
    if Path(relative).suffix:
        return None
    return relative + "/index.html"


def main() -> None:
    source_files = {
        path.relative_to(SOURCE).as_posix(): path
        for path in SOURCE.rglob("*")
        if path.is_file()
    }
    output_files = {
        path.relative_to(OUTPUT).as_posix(): path
        for path in OUTPUT.rglob("*")
        if path.is_file()
    }
    common = sorted(set(source_files) & set(output_files))

    def compare(relative: str) -> tuple[str, bool]:
        return relative, digest(source_files[relative]) == digest(output_files[relative])

    with ThreadPoolExecutor(max_workers=16) as pool:
        comparisons = dict(pool.map(compare, common, chunksize=32))

    html_paths = {
        relative: path for relative, path in output_files.items()
        if relative.lower().endswith(".html")
    }
    html_set = set(html_paths)

    def inspect(item: tuple[str, Path]) -> dict[str, object]:
        relative, path = item
        text = path.read_text(encoding="utf-8")
        titles = TITLE.findall(text)
        descriptions = [match[1] for match in DESC.findall(text)]
        canonicals = [match[1] for match in CANON.findall(text)]
        jsonld_scripts = JSONLD.findall(text)
        jsonld_error = 0
        breadcrumb_list_count = 0
        for script in jsonld_scripts:
            try:
                value = json.loads(script)
            except Exception:
                jsonld_error += 1
                continue
            nodes = value.get("@graph", []) if isinstance(value, dict) else []
            if isinstance(value, dict) and value.get("@type") == "BreadcrumbList":
                breadcrumb_list_count += 1
            breadcrumb_list_count += sum(
                isinstance(node, dict) and node.get("@type") == "BreadcrumbList"
                for node in nodes
            )
        breadcrumbs = BREADCRUMB.findall(text)
        bottom_ok = 0
        top_breadcrumb = 0
        if len(breadcrumbs) == 1:
            position = text.find(breadcrumbs[0])
            h1_position = text.find("<h1")
            top_breadcrumb = int(h1_position >= 0 and position < h1_position)
            bottom_matches = list(BOTTOM.finditer(text[:position]))
            if bottom_matches:
                close = text.find("</section>", bottom_matches[-1].end())
                main_close = text.rfind("</main>")
                footer = text.find("<footer", main_close)
                bottom_ok = int(
                    close >= position + len(breadcrumbs[0])
                    and main_close > close
                    and footer > main_close
                    and not text[close + len("</section>"):main_close].strip()
                )
        links = [match[1] for match in ANCHOR.findall(text)]
        return {
            "relative": relative,
            "title_error": int(len(titles) != 1 or not titles[0].strip()),
            "description_error": int(
                len(descriptions) != 1 or not descriptions[0].strip()
            ),
            "canonical_error": int(
                len(canonicals) != 1
                or not canonicals[0].startswith("https://goodstudy.co.kr/")
            ),
            "jsonld_error": jsonld_error + int(not jsonld_scripts),
            "breadcrumb_count": len(breadcrumbs),
            "breadcrumb_list_count": breadcrumb_list_count,
            "bottom_error": int(bool(breadcrumbs) and not bottom_ok),
            "top_breadcrumb": top_breadcrumb,
            "links": links,
        }

    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, html_paths.items(), chunksize=32))

    graph: dict[str, set[str]] = {relative: set() for relative in html_set}
    broken: list[dict[str, str]] = []
    for row in rows:
        source_page = str(row["relative"])
        for href in row["links"]:
            destination = html_target(source_page, str(href))
            if destination is None:
                continue
            if destination not in html_set:
                broken.append({"source_page": source_page, "href": str(href)})
            else:
                graph[source_page].add(destination)
    visited = {"index.html"}
    queue = deque(["index.html"])
    while queue:
        current = queue.popleft()
        for destination in graph.get(current, set()):
            if destination not in visited:
                visited.add(destination)
                queue.append(destination)
    orphans = sorted(html_set - visited)

    sitemap_path = OUTPUT / "sitemap.xml"
    sitemap_error = 0
    sitemap_urls = 0
    try:
        root = ET.parse(sitemap_path).getroot()
        sitemap_urls = len(root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url"))
    except Exception:
        sitemap_error = 1
    robots_path = OUTPUT / "robots.txt"
    robots_error = int(
        not robots_path.is_file()
        or not robots_path.read_text(encoding="utf-8").strip()
    )
    home = (OUTPUT / "index.html").read_text(encoding="utf-8")
    favicon_match = re.search(
        r'<link\b(?=[^>]*\brel=["\']icon["\'])[^>]*\bhref=(["\'])(.*?)\1',
        home, re.I,
    )
    manifest_match = re.search(
        r'<link\b(?=[^>]*\brel=["\']manifest["\'])[^>]*\bhref=(["\'])(.*?)\1',
        home, re.I,
    )
    favicon_error = int(
        not favicon_match
        or not (OUTPUT / favicon_match.group(2).lstrip("/")).is_file()
    )
    manifest_error = int(
        not manifest_match
        or not (OUTPUT / manifest_match.group(2).lstrip("/")).is_file()
    )

    def total(key: str) -> int:
        return sum(int(row[key]) for row in rows)

    summary = {
        "candidate_file_count": len(source_files),
        "output_file_count": len(output_files),
        "missing_files": len(set(source_files) - set(output_files)),
        "extra_files": len(set(output_files) - set(source_files)),
        "hash_mismatches": sum(not value for value in comparisons.values()),
        "candidate_html_count": sum(name.endswith(".html") for name in source_files),
        "output_html_count": len(html_paths),
        "sitemap_url_count": sitemap_urls,
        "sitemap_errors": sitemap_error,
        "robots_errors": robots_error,
        "title_errors": total("title_error"),
        "description_errors": total("description_error"),
        "canonical_errors": total("canonical_error"),
        "jsonld_errors": total("jsonld_error"),
        "html_breadcrumb_pages": sum(row["breadcrumb_count"] == 1 for row in rows),
        "jsonld_breadcrumb_pages": sum(row["breadcrumb_list_count"] == 1 for row in rows),
        "breadcrumb_count_errors": sum(row["breadcrumb_count"] not in {0, 1} for row in rows),
        "top_breadcrumb_remaining": total("top_breadcrumb"),
        "bottom_breadcrumb_errors": total("bottom_error"),
        "broken_links": len(broken),
        "orphan_pages": len(orphans),
        "favicon_errors": favicon_error,
        "manifest_errors": manifest_error,
        "unexpected_changes": (
            len(set(source_files) - set(output_files))
            + len(set(output_files) - set(source_files))
            + sum(not value for value in comparisons.values())
        ),
    }
    zero_keys = [
        "missing_files", "extra_files", "hash_mismatches", "sitemap_errors",
        "robots_errors", "title_errors", "description_errors", "canonical_errors",
        "jsonld_errors", "breadcrumb_count_errors", "top_breadcrumb_remaining",
        "bottom_breadcrumb_errors", "broken_links", "orphan_pages",
        "favicon_errors", "manifest_errors", "unexpected_changes",
    ]
    passed = (
        summary["candidate_file_count"] == summary["output_file_count"]
        and summary["candidate_html_count"] == summary["output_html_count"] == 30457
        and all(summary[key] == 0 for key in zero_keys)
    )
    result = {
        "status": "PASS" if passed else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "candidate": str(SOURCE),
        "output": str(OUTPUT),
        "summary": summary,
        "broken_link_details": broken[:500],
        "orphan_details": orphans[:500],
    }
    temporary = AUDIT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)
    lines = [
        "# Output 승격 전수 감사", "",
        f"- 결과: **{result['status']}**",
        f"- 후보: `{SOURCE}`",
        f"- output: `{OUTPUT}`", "",
        *[f"- {key}: {value}" for key, value in summary.items()],
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], **summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
