from __future__ import annotations

import html
import json
import os
import re
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
AUDIT = ROOT / "audit" / "output-promotion-audit.json"
REPORT = ROOT / "audit" / "output-promotion-audit.md"
A = re.compile(r'<a\b[^>]*href="([^"]*)"', re.I)


def internal(href: str) -> str | None:
    parsed = urlsplit(html.unescape(href))
    if parsed.scheme or parsed.netloc:
        return None
    path = unquote(parsed.path)
    if not path.startswith("/") or path.startswith("//"):
        return None
    if path == "/":
        return "/"
    return path if path.endswith("/") else path + "/"


def main() -> None:
    paths = [OUTPUT / "index.html", *sorted(OUTPUT.glob("*/index.html"))]
    all_urls = {"/" if path == OUTPUT / "index.html" else f"/{path.parent.name}/" for path in paths}

    def inspect(path: Path) -> tuple[str, set[str]]:
        current = "/" if path == OUTPUT / "index.html" else f"/{path.parent.name}/"
        text = path.read_text(encoding="utf-8")
        links = {value for value in (internal(href) for href in A.findall(text)) if value}
        return current, links

    with ThreadPoolExecutor(max_workers=16) as pool:
        adjacency = dict(pool.map(inspect, paths, chunksize=32))
    broken = sorted(
        (source, destination)
        for source, destinations in adjacency.items()
        for destination in destinations
        if destination not in all_urls
    )
    incoming = Counter(
        destination
        for destinations in adjacency.values()
        for destination in destinations
        if destination in all_urls
    )
    orphans = sorted(url for url in all_urls if url != "/" and incoming[url] == 0)
    reverse = {url: set() for url in all_urls}
    for source, destinations in adjacency.items():
        for destination in destinations:
            if destination in reverse:
                reverse[destination].add(source)
    home_reachable = {"/"}
    queue = deque(["/"])
    while queue:
        current = queue.popleft()
        for prior in reverse[current]:
            if prior not in home_reachable:
                home_reachable.add(prior)
                queue.append(prior)
    home_unreachable = sorted(all_urls - home_reachable)

    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    data["summary"]["broken_links"] = len(broken)
    data["summary"]["orphan_pages"] = len(orphans)
    data["summary"]["home_unreachable_pages"] = len(home_unreachable)
    data["graph_audit_method"] = (
        "Orphan means a non-home HTML page with zero incoming internal links. "
        "Home reachability is checked in reverse: every page can navigate to home."
    )
    data["broken_link_details"] = [
        {"source_page": source, "href": destination}
        for source, destination in broken[:500]
    ]
    data["orphan_details"] = orphans[:500]
    data["home_unreachable_details"] = home_unreachable[:500]
    zero_keys = [
        "missing_files", "extra_files", "hash_mismatches", "sitemap_errors",
        "robots_errors", "title_errors", "description_errors", "canonical_errors",
        "jsonld_errors", "breadcrumb_count_errors", "top_breadcrumb_remaining",
        "bottom_breadcrumb_errors", "broken_links", "orphan_pages",
        "home_unreachable_pages", "favicon_errors", "manifest_errors",
        "unexpected_changes",
    ]
    data["status"] = "PASS" if all(data["summary"][key] == 0 for key in zero_keys) else "FAIL"
    temporary = AUDIT.with_suffix(".json.graph.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)
    lines = [
        "# Output 승격 전수 감사", "",
        f"- 결과: **{data['status']}**",
        f"- 후보: `{data['candidate']}`",
        f"- output: `{data['output']}`", "",
        "## 전수 검사", "",
        *[f"- {key}: {value}" for key, value in data["summary"].items()],
        "", f"> {data['graph_audit_method']}",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": data["status"],
        "broken_links": len(broken),
        "orphan_pages": len(orphans),
        "home_unreachable_pages": len(home_unreachable),
    }, ensure_ascii=False))
    raise SystemExit(0 if data["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
