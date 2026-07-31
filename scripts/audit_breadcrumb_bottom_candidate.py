from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_school_pyramid_navigation_bottom_links"
BUILD = ROOT / "intermediate" / "breadcrumb-bottom-build.json"
AUDIT = ROOT / "audit" / "breadcrumb-bottom-audit.json"
REPORT = ROOT / "audit" / "breadcrumb-bottom-report.md"
PAGES = ROOT / "audit" / "breadcrumb-bottom-pages.csv"

BREADCRUMB = re.compile(
    r'<nav\b(?=[^>]*\bclass="[^"]*\bbreadcrumb\b[^"]*")[^>]*>.*?</nav>',
    re.I | re.S,
)
BOTTOM = re.compile(
    r'<section\b[^>]*\bclass="[^"]*\bregion-bottom-navigation\b[^"]*"[^>]*>',
    re.I,
)
HREF = re.compile(r'\bhref=(["\'])(.*?)\1', re.I | re.S)
ANCHOR_HREF = re.compile(
    r'<a\b[^>]*\bhref=(["\'])(.*?)\1', re.I | re.S
)
TITLE = re.compile(r"<title\b[^>]*>.*?</title>", re.I | re.S)
DESC = re.compile(r'<meta\b(?=[^>]*\bname=["\']description["\'])[^>]*>', re.I)
CANON = re.compile(r'<link\b(?=[^>]*\brel=["\']canonical["\'])[^>]*>', re.I)
JSONLD = re.compile(
    r'<script\b(?=[^>]*\btype=["\']application/ld\+json["\'])[^>]*>.*?</script>',
    re.I | re.S,
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def extract(pattern: re.Pattern[str], text: str) -> list[str]:
    return pattern.findall(text)


def internal_target(href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        if parts.netloc not in {"goodstudy.co.kr", "www.goodstudy.co.kr"}:
            return None
    path = unquote(parts.path or "/").replace("\\", "/")
    while "//" in path:
        path = path.replace("//", "/")
    if not path.startswith("/"):
        return None
    if path == "/":
        return "index.html"
    relative = path.lstrip("/")
    if relative.endswith("/"):
        return relative + "index.html"
    if Path(relative).suffix:
        return relative
    return relative + "/index.html"


def main() -> None:
    build = json.loads(BUILD.read_text(encoding="utf-8"))
    target = Path(build["target"])
    source_paths = {
        path.relative_to(SOURCE).as_posix(): path for path in SOURCE.rglob("*.html")
    }
    target_paths = {
        path.relative_to(target).as_posix(): path for path in target.rglob("*.html")
    }

    def inspect(item: tuple[str, Path]) -> dict[str, object]:
        relative, source_path = item
        target_path = target_paths.get(relative)
        if target_path is None:
            return {"relative": relative, "missing": 1}
        source = source_path.read_text(encoding="utf-8")
        current = target_path.read_text(encoding="utf-8")
        source_bc = BREADCRUMB.findall(source)
        target_bc = BREADCRUMB.findall(current)
        has_bc = len(source_bc) == 1
        top_remaining = 0
        bottom_ok = 0
        href_changed = 0
        placement_only_error = 0
        if has_bc and len(target_bc) == 1:
            bc = target_bc[0]
            bc_pos = current.find(bc)
            h1_pos = current.find("<h1")
            top_remaining = int(h1_pos >= 0 and bc_pos < h1_pos)
            bottom_matches = list(BOTTOM.finditer(current[:bc_pos]))
            if bottom_matches:
                close = current.find("</section>", bottom_matches[-1].end())
                main_close = current.rfind("</main>")
                footer = current.find("<footer", main_close)
                bottom_ok = int(
                    close >= bc_pos + len(bc)
                    and main_close > close
                    and footer > main_close
                    and not current[close + len("</section>") : main_close].strip()
                )
            href_changed = int(
                [m[1] for m in HREF.findall(source_bc[0])]
                != [m[1] for m in HREF.findall(target_bc[0])]
            )
            source_without = BREADCRUMB.sub("", source, count=1)
            current_without = BREADCRUMB.sub("", current, count=1)
            current_without = re.sub(
                r'<section class="region-bottom-navigation" aria-label="하단 탐색">\s*</section>',
                "",
                current_without,
                count=1,
            )
            placement_only_error = int(source_without != current_without)
        return {
            "relative": relative,
            "missing": 0,
            "source_breadcrumb_count": len(source_bc),
            "target_breadcrumb_count": len(target_bc),
            "top_remaining": top_remaining,
            "bottom_ok": bottom_ok,
            "href_changed": href_changed,
            "placement_only_error": placement_only_error,
            "title_changed": int(extract(TITLE, source) != extract(TITLE, current)),
            "description_changed": int(extract(DESC, source) != extract(DESC, current)),
            "canonical_changed": int(extract(CANON, source) != extract(CANON, current)),
            "jsonld_changed": int(extract(JSONLD, source) != extract(JSONLD, current)),
            "href_list_changed": int(
                sorted(m[1] for m in HREF.findall(source))
                != sorted(m[1] for m in HREF.findall(current))
            ),
            "hrefs": [m[1] for m in ANCHOR_HREF.findall(current)],
        }

    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, source_paths.items(), chunksize=32))

    existing = set(target_paths)
    broken: list[dict[str, str]] = []
    for row in rows:
        relative = str(row["relative"])
        for href in row.get("hrefs", []):
            destination = internal_target(href)
            if destination is not None and destination not in existing:
                broken.append(
                    {"source_page": relative, "href": href, "expected_file": destination}
                )

    with PAGES.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "page", "source_breadcrumb_count", "target_breadcrumb_count",
            "top_remaining", "bottom_ok", "href_changed", "placement_only_error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            if row.get("source_breadcrumb_count") == 1:
                writer.writerow({field: row.get("relative") if field == "page" else row.get(field, 0) for field in fields})

    def total(key: str) -> int:
        return sum(int(row.get(key, 0)) for row in rows)

    source_assets = {
        path.relative_to(SOURCE).as_posix(): digest(path)
        for folder in ("assets",)
        for path in (SOURCE / folder).rglob("*")
        if path.is_file()
    }
    target_assets = {
        path.relative_to(target).as_posix(): digest(path)
        for folder in ("assets",)
        for path in (target / folder).rglob("*")
        if path.is_file()
    }
    summary = {
        "html_count": len(target_paths),
        "source_html_count": len(source_paths),
        "new_html": len(set(target_paths) - set(source_paths)),
        "deleted_html": len(set(source_paths) - set(target_paths)),
        "breadcrumb_pages": sum(row.get("source_breadcrumb_count") == 1 for row in rows),
        "moved_breadcrumb_pages": sum(
            row.get("source_breadcrumb_count") == 1
            and row.get("target_breadcrumb_count") == 1
            and row.get("bottom_ok") == 1
            for row in rows
        ),
        "top_breadcrumb_remaining": total("top_remaining"),
        "bottom_breadcrumb_errors": sum(
            row.get("source_breadcrumb_count") == 1 and row.get("bottom_ok") != 1
            for row in rows
        ),
        "breadcrumb_count_errors": sum(
            row.get("source_breadcrumb_count") != row.get("target_breadcrumb_count")
            for row in rows
        ),
        "breadcrumb_href_changes": total("href_changed"),
        "all_href_list_changes": total("href_list_changed"),
        "placement_only_errors": total("placement_only_error"),
        "broken_links": len(broken),
        "title_changes": total("title_changed"),
        "description_changes": total("description_changed"),
        "canonical_changes": total("canonical_changed"),
        "jsonld_changes": total("jsonld_changed"),
        "sitemap_changes": int(digest(SOURCE / "sitemap.xml") != digest(target / "sitemap.xml")),
        "robots_changes": int(digest(SOURCE / "robots.txt") != digest(target / "robots.txt")),
        "asset_changes": int(source_assets != target_assets),
        "read_or_missing_errors": total("missing"),
    }
    zero_keys = [
        "new_html", "deleted_html", "top_breadcrumb_remaining",
        "bottom_breadcrumb_errors", "breadcrumb_count_errors",
        "breadcrumb_href_changes", "all_href_list_changes", "placement_only_errors",
        "broken_links", "title_changes", "description_changes", "canonical_changes",
        "jsonld_changes", "sitemap_changes", "robots_changes", "asset_changes",
        "read_or_missing_errors",
    ]
    passed = (
        summary["html_count"] == 30457
        and summary["breadcrumb_pages"] == 30456
        and summary["moved_breadcrumb_pages"] == 30456
        and all(summary[key] == 0 for key in zero_keys)
    )
    result = {
        "status": "PASS" if passed else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "source": str(SOURCE),
        "target": str(target),
        "summary": summary,
        "broken_link_details": broken[:500],
    }
    temporary = AUDIT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)
    lines = [
        "# Breadcrumb 하단 이동 감사", "",
        f"- 결과: **{result['status']}**",
        f"- 기준 후보: `{SOURCE}`",
        f"- 새 후보: `{target}`", "",
        "## 전수 검사", "",
        *[f"- {key}: {value}" for key, value in summary.items()],
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], **summary}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
