from __future__ import annotations

import json
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STRUCTURE = ROOT / "candidate_output_structureclean"
IMAGE = ROOT / "candidate_output_image_preview"
PREVIEW = ROOT / "candidate_output_structure_image_homefix_preview"
PRIMARY = ROOT / "candidate_output_structure_image_homefix"
REBUILD = ROOT / "candidate_output_structure_image_homefix_rebuild"
CSS = ROOT / "assets" / "css" / "structure-home-image-fix.css"
CHECKPOINT = ROOT / "intermediate" / "structure-image-homefix-full-build-checkpoint.json"
CSS_LINKS = (
    "/assets/css/structure-preview.css",
    "/assets/css/home-navigation-preview.css",
    "/assets/css/image-preview.css",
)


def choose_target() -> Path:
    if not PRIMARY.exists() or not any(PRIMARY.iterdir()):
        return PRIMARY
    if not REBUILD.exists() or not any(REBUILD.iterdir()):
        return REBUILD
    raise RuntimeError(f"both target candidates are non-empty: {PRIMARY}, {REBUILD}")


def integrated_css(source: str) -> str:
    for href in CSS_LINKS:
        source = re.sub(
            rf'\s*<link\s+rel="stylesheet"\s+href="{re.escape(href)}"\s*/?>',
            "",
            source,
            flags=re.I,
        )
    if "/assets/css/structure-home-image-fix.css" not in source:
        source = source.replace(
            "</head>",
            '  <link rel="stylesheet" href="/assets/css/structure-home-image-fix.css">\n</head>',
            1,
        )
    return source


def checkpoint(target: Path, status: str, completed: int, total: int) -> None:
    value = {
        "status": status, "target": str(target), "completed_html": completed,
        "total_html": total, "updated_at": datetime.now().astimezone().isoformat(),
    }
    temporary = CHECKPOINT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, CHECKPOINT)


def main() -> None:
    target = choose_target()
    image_paths = [IMAGE / "index.html", *sorted(IMAGE.glob("*/index.html"), key=lambda p: p.parent.name)]
    structure_paths = [STRUCTURE / "index.html", *sorted(STRUCTURE.glob("*/index.html"), key=lambda p: p.parent.name)]
    if len(image_paths) != 30457 or len(structure_paths) != 30457:
        raise RuntimeError(f"baseline count mismatch: image={len(image_paths)}, structure={len(structure_paths)}")
    if {p.relative_to(IMAGE).as_posix() for p in image_paths} != {
        p.relative_to(STRUCTURE).as_posix() for p in structure_paths
    }:
        raise RuntimeError("image and structure HTML path sets differ")

    checkpoint(target, "copying", 0, len(image_paths))
    shutil.copytree(IMAGE, target, dirs_exist_ok=True)
    shutil.copy2(CSS, target / "assets" / "css" / CSS.name)
    for name in ("sitemap.xml", "robots.txt", "site.webmanifest"):
        shutil.copy2(STRUCTURE / name, target / name)

    approved_home = (PREVIEW / "index.html").read_text(encoding="utf-8")
    (target / "index.html").write_text(approved_home, encoding="utf-8", newline="")

    content_paths = image_paths[1:]

    def convert(path: Path) -> None:
        relative = path.relative_to(IMAGE)
        output_path = target / relative
        output = integrated_css(path.read_text(encoding="utf-8"))
        temporary = output_path.with_name("index.html.integration.tmp")
        temporary.write_text(output, encoding="utf-8", newline="")
        os.replace(temporary, output_path)

    completed = 1
    with ThreadPoolExecutor(max_workers=16) as pool:
        for _ in pool.map(convert, content_paths, chunksize=32):
            completed += 1
            if completed % 1000 == 0:
                checkpoint(target, "integrating", completed, len(image_paths))
    checkpoint(target, "complete", completed, len(image_paths))
    print(json.dumps({"target": str(target), "generated_html": completed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
