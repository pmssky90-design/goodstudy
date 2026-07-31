from __future__ import annotations

import json
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "intermediate" / "school-pyramid-navigation-build.json"
SECTION = re.compile(
    r'<section class="related-section school-pyramid-navigation" '
    r'data-school-level="(province|district)">.*?</section>',
    re.I | re.S,
)


def main() -> None:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    target = Path(checkpoint["target"])
    changed = 0
    for slug in checkpoint["changed_region_slugs"]:
        path = target / slug / "index.html"
        source = path.read_text(encoding="utf-8")
        match = SECTION.search(source)
        if not match:
            raise RuntimeError(f"navigation section missing: {slug}")
        level = match.group(1)
        block = match.group(0).replace(
            f'data-school-level="{level}"',
            f'id="school-pyramid-{level}" data-school-level="{level}"',
            1,
        )
        without = source[:match.start()] + source[match.end():]
        insertion = without.find('<section class="title-panel">')
        if insertion < 0:
            raise RuntimeError(f"title panel missing: {slug}")
        output = without[:insertion] + block + without[insertion:]
        temporary = path.with_suffix(".html.move.tmp")
        temporary.write_text(output, encoding="utf-8", newline="")
        os.replace(temporary, path)
        changed += 1
    print(json.dumps({"target": str(target), "moved_sections": changed}))


if __name__ == "__main__":
    main()
