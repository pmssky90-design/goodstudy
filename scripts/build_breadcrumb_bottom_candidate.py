from __future__ import annotations

import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_output_school_pyramid_navigation_bottom_links"
BASE_TARGET = ROOT / "candidate_output_school_pyramid_navigation_bottom_links_breadcrumb_bottom"
CHECKPOINT = ROOT / "intermediate" / "breadcrumb-bottom-build.json"

BREADCRUMB = re.compile(
    r'<nav\b(?=[^>]*\bclass="[^"]*\bbreadcrumb\b[^"]*")[^>]*>.*?</nav>',
    re.IGNORECASE | re.DOTALL,
)
BOTTOM_OPEN = re.compile(
    r'(<section\b[^>]*\bclass="[^"]*\bregion-bottom-navigation\b[^"]*"[^>]*>)',
    re.IGNORECASE,
)


def choose_target() -> Path:
    if BASE_TARGET.exists() and not CHECKPOINT.exists():
        return BASE_TARGET
    if not BASE_TARGET.exists():
        return BASE_TARGET
    index = 2
    while True:
        candidate = Path(f"{BASE_TARGET}_{index}")
        if not candidate.exists():
            return candidate
        index += 1


def main() -> None:
    target = choose_target()
    if not target.exists():
        shutil.copytree(SOURCE, target, copy_function=shutil.copy2)

    def transform(path: Path) -> tuple[int, int, int, int, str]:
        text = path.read_text(encoding="utf-8")
        matches = list(BREADCRUMB.finditer(text))
        if not matches:
            return 0, 0, 0, 0, ""
        if len(matches) != 1:
            return 1, 0, 0, 0, path.relative_to(target).as_posix()
        match = matches[0]
        prior_bottom = list(BOTTOM_OPEN.finditer(text[: match.start()]))
        if prior_bottom:
            close = text.find("</section>", prior_bottom[-1].end())
            if close >= match.end():
                integrated = "region-school-links" in prior_bottom[-1].group(0)
                return 1, 0, int(integrated), int(not integrated), ""
        breadcrumb = match.group(0)
        without = text[: match.start()] + text[match.end() :]
        bottom = BOTTOM_OPEN.search(without)
        if bottom:
            updated = (
                without[: bottom.end()]
                + breadcrumb
                + without[bottom.end() :]
            )
            integrated_existing = 1
            new_bottom = 0
        else:
            marker = without.rfind("</main>")
            if marker < 0:
                raise RuntimeError(f"</main> not found: {path}")
            block = (
                '<section class="region-bottom-navigation" '
                'aria-label="하단 탐색">'
                + breadcrumb
                + "</section>"
            )
            updated = without[:marker] + block + without[marker:]
            integrated_existing = 0
            new_bottom = 1
        path.write_text(updated, encoding="utf-8")
        return 1, 1, integrated_existing, new_bottom, ""

    paths = list(target.rglob("*.html"))
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(transform, paths, chunksize=32))
    html_count = len(paths)
    breadcrumb_pages = sum(row[0] for row in results)
    changed_this_run = sum(row[1] for row in results)
    integrated_existing_bottom = sum(row[2] for row in results)
    new_bottom_blocks = sum(row[3] for row in results)
    multiple_breadcrumb_errors = [row[4] for row in results if row[4]]
    changed_pages = breadcrumb_pages

    result = {
        "status": "complete" if not multiple_breadcrumb_errors else "error",
        "completed_at": datetime.now().astimezone().isoformat(),
        "source": str(SOURCE),
        "target": str(target),
        "html_count": html_count,
        "breadcrumb_pages": breadcrumb_pages,
        "changed_pages": changed_pages,
        "changed_this_run": changed_this_run,
        "integrated_existing_bottom": integrated_existing_bottom,
        "new_bottom_blocks": new_bottom_blocks,
        "multiple_breadcrumb_errors": multiple_breadcrumb_errors,
    }
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "complete" else 1)


if __name__ == "__main__":
    main()
