from __future__ import annotations

import csv
import html
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_school_pyramid_navigation"
TARGET_BASE = ROOT / "candidate_output_school_pyramid_navigation_bottom_links"
PYRAMID_CHECKPOINT = ROOT / "intermediate" / "school-pyramid-navigation-build.json"
CHECKPOINT = ROOT / "intermediate" / "school-pyramid-bottom-links-build.json"
PAGES_CSV = ROOT / "audit" / "school-pyramid-bottom-links-pages.csv"
DUPLICATES_CSV = ROOT / "audit" / "school-pyramid-bottom-links-duplicates.csv"

TOP_NAV = re.compile(
    r'<nav class="region-school-links" aria-label="상위 학교 탐색">(.*?)</nav>',
    re.I | re.S,
)
ANCHOR = re.compile(r'<a\b[^>]*href="([^"]*)"[^>]*>.*?</a>', re.I | re.S)
PYRAMID = re.compile(
    r'<section class="related-section school-pyramid-navigation"[^>]*>.*?</section>',
    re.I | re.S,
)


def target_path() -> Path:
    if not TARGET_BASE.exists() or not any(TARGET_BASE.iterdir()):
        return TARGET_BASE
    index = 2
    while True:
        candidate = TARGET_BASE.with_name(f"{TARGET_BASE.name}_{index}")
        if not candidate.exists() or not any(candidate.iterdir()):
            return candidate
        index += 1


def normalized_href(href: str) -> str:
    parsed = urlsplit(html.unescape(href))
    path = unquote(parsed.path) or "/"
    if path != "/":
        path = "/" + path.strip("/") + "/"
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return path + fragment


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    target = target_path()
    pyramid = json.loads(PYRAMID_CHECKPOINT.read_text(encoding="utf-8"))
    slugs = list(pyramid["changed_region_slugs"])
    shutil.copytree(SOURCE, target)
    page_rows: list[dict[str, object]] = []
    duplicate_rows: list[dict[str, object]] = []

    for slug in slugs:
        path = target / slug / "index.html"
        source = path.read_text(encoding="utf-8")
        pyramid_match = PYRAMID.search(source)
        if not pyramid_match:
            raise RuntimeError(f"pyramid section missing: {slug}")
        nav_match = TOP_NAV.search(pyramid_match.group(0))
        if not nav_match:
            raise RuntimeError(f"top navigation missing: {slug}")
        anchors = ANCHOR.findall(nav_match.group(0))
        anchor_html = ANCHOR.findall(nav_match.group(0))
        raw_anchor_tags = [match.group(0) for match in ANCHOR.finditer(nav_match.group(0))]
        normalized = [normalized_href(href) for href in anchors]
        if len(normalized) != len(set(normalized)):
            raise RuntimeError(f"duplicate source navigation href: {slug}")

        without_nav_block = (
            pyramid_match.group(0)[:nav_match.start()]
            + pyramid_match.group(0)[nav_match.end():]
        )
        output = source[:pyramid_match.start()] + without_nav_block + source[pyramid_match.end():]

        # Existing bottom region navigation is preferred, but the source has none.
        existing_bottom = re.search(
            r'<section class="[^"]*\bregion-bottom-navigation\b[^"]*"[^>]*>.*?</section>',
            output, re.I | re.S,
        )
        existing_hrefs = set()
        integrated = 0
        skipped = 0
        moved_tags = []
        if existing_bottom:
            integrated = 1
            existing_hrefs = {
                normalized_href(href) for href in re.findall(
                    r'<a\b[^>]*href="([^"]*)"', existing_bottom.group(0), re.I
                )
            }
        for tag, href, normalized_value in zip(raw_anchor_tags, anchors, normalized):
            if normalized_value in existing_hrefs:
                skipped += 1
                duplicate_rows.append({
                    "page": f"/{slug}/", "href": href, "normalized_href": normalized_value,
                    "action": "not_added", "reason": "existing_bottom_same_destination",
                })
            else:
                moved_tags.append(tag)
                existing_hrefs.add(normalized_value)

        if existing_bottom:
            replacement = existing_bottom.group(0).replace(
                "</section>", "".join(moved_tags) + "</section>", 1
            )
            output = (
                output[:existing_bottom.start()] + replacement + output[existing_bottom.end():]
            )
        else:
            block = (
                '<section class="region-bottom-navigation region-school-links" '
                'aria-label="지역 탐색">'
                f'{"".join(moved_tags)}</section>'
            )
            insertion = output.rfind("</main>")
            if insertion < 0:
                raise RuntimeError(f"main closing tag missing: {slug}")
            output = output[:insertion] + block + output[insertion:]

        temporary = path.with_suffix(".html.bottom.tmp")
        temporary.write_text(output, encoding="utf-8", newline="")
        os.replace(temporary, path)
        level = "province" if 'data-school-level="province"' in output else "district"
        page_rows.append({
            "page": f"/{slug}/", "page_level": level,
            "source_top_link_count": len(anchors), "top_blocks_removed": 1,
            "bottom_blocks_added": int(not existing_bottom), "integrated_existing_bottom": integrated,
            "links_moved": len(moved_tags), "links_skipped_as_duplicate": skipped,
            "duplicate_links_removed": 0,
            "source_hrefs": "|".join(anchors), "target_hrefs": "|".join(
                re.findall(r'href="([^"]*)"', "".join(moved_tags))
            ),
        })

    write_csv(
        PAGES_CSV, page_rows,
        ["page", "page_level", "source_top_link_count", "top_blocks_removed",
         "bottom_blocks_added", "integrated_existing_bottom", "links_moved",
         "links_skipped_as_duplicate", "duplicate_links_removed", "source_hrefs", "target_hrefs"],
    )
    write_csv(
        DUPLICATES_CSV, duplicate_rows,
        ["page", "href", "normalized_href", "action", "reason"],
    )
    checkpoint = {
        "status": "complete", "source": str(SOURCE), "target": str(target),
        "province_pages": sum(row["page_level"] == "province" for row in page_rows),
        "district_pages": sum(row["page_level"] == "district" for row in page_rows),
        "changed_pages": len(page_rows),
        "top_blocks_removed": sum(int(row["top_blocks_removed"]) for row in page_rows),
        "bottom_blocks_added": sum(int(row["bottom_blocks_added"]) for row in page_rows),
        "integrated_existing_bottom": sum(int(row["integrated_existing_bottom"]) for row in page_rows),
        "links_moved": sum(int(row["links_moved"]) for row in page_rows),
        "links_skipped_as_duplicate": sum(int(row["links_skipped_as_duplicate"]) for row in page_rows),
        "duplicate_links_removed": sum(int(row["duplicate_links_removed"]) for row in page_rows),
        "changed_slugs": slugs,
    }
    CHECKPOINT.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(checkpoint, ensure_ascii=False))


if __name__ == "__main__":
    main()
