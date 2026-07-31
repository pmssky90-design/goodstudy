from __future__ import annotations

import json
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from build_structure_preview import (
    ROOT, SOURCE, META, HEAD_RE, classify, render_content,
)

PRIMARY_TARGET = ROOT / "candidate_output_structureclean"
REBUILD_TARGET = ROOT / "candidate_output_structureclean_rebuild"
CHECKPOINT = ROOT / "intermediate" / "structure-full-build-checkpoint.json"


def checkpoint(target: Path, total: int, completed: int, errors: int, last: str, started: str) -> None:
    value = {
        "status": "complete" if completed == total and errors == 0 else "running",
        "source": str(SOURCE), "target": str(target), "total_html": total,
        "completed_html": completed, "errors": errors, "last_relative_path": last,
        "started_at": started, "updated_at": datetime.now().astimezone().isoformat(),
    }
    temporary = CHECKPOINT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, CHECKPOINT)


def select_target() -> Path:
    if not PRIMARY_TARGET.exists():
        return PRIMARY_TARGET
    primary_html = [PRIMARY_TARGET / "index.html"] + list(PRIMARY_TARGET.glob("*/index.html"))
    if len(primary_html) == 30457 and all(path.exists() for path in primary_html):
        return PRIMARY_TARGET
    if REBUILD_TARGET.exists() and any(REBUILD_TARGET.iterdir()):
        raise RuntimeError(f"both full targets contain files: {PRIMARY_TARGET}, {REBUILD_TARGET}")
    return REBUILD_TARGET


def main() -> None:
    started = datetime.now().astimezone().isoformat()
    target = select_target()
    target.mkdir(parents=True, exist_ok=True)
    # The caller copies the complete baseline first; this guard prevents partial conversion.
    source_paths = [SOURCE / "index.html"] + sorted(SOURCE.glob("*/index.html"), key=lambda p: p.relative_to(SOURCE).as_posix())
    target_paths = [target / path.relative_to(SOURCE) for path in source_paths]
    if len(source_paths) != 30457 or any(not path.exists() for path in target_paths):
        raise RuntimeError(f"baseline copy incomplete: source={len(source_paths)}, missing={sum(not p.exists() for p in target_paths)}")
    metadata = json.loads(META.read_text(encoding="utf-8"))
    by_slug = {str(item["slug"]): item for item in metadata}
    by_id = {str(item["node_id"]): item for item in metadata}
    home = {"node_id": "home", "slug": "", "page_type": "home", "title": "좋은공부"}
    environment = Environment(loader=FileSystemLoader(ROOT / "templates"))
    shell = environment.get_template("structure_preview.html")
    shutil.copy2(ROOT / "assets" / "css" / "structure-preview.css", target / "assets" / "css" / "structure-preview.css")

    def convert(source_path: Path) -> str:
        rel = source_path.relative_to(SOURCE)
        slug = "" if rel.as_posix() == "index.html" else source_path.parent.name
        meta = home if not slug else by_slug[slug]
        source = source_path.read_text(encoding="utf-8")
        head_match = HEAD_RE.search(source)
        if not head_match:
            raise RuntimeError(f"head missing: {rel}")
        head = head_match.group(0)
        if "/assets/css/structure-preview.css" not in head:
            head = head.replace("</head>", '  <link rel="stylesheet" href="/assets/css/structure-preview.css">\n</head>')
        cls = {"entity_type": "home", "subject_type": "general", "grade_type": "general", "region_level": "home"} if not slug else classify(meta)
        body = shell.render(preview_content=render_content(source, meta, by_slug, by_id), **cls)
        output = re.sub(r"<head\b[^>]*>.*?</head>", head, source, count=1, flags=re.I | re.S)
        output = re.sub(r"<body\b[^>]*>.*?</body>", f"<body>{body}</body>", output, count=1, flags=re.I | re.S)
        target_path = target / rel
        temporary = target_path.with_name(target_path.name + ".structure.tmp")
        temporary.write_text(output, encoding="utf-8", newline="")
        if output.count("<h1") != 1 or "<body>" not in output or "</body>" not in output:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"render validation failed: {rel}")
        os.replace(temporary, target_path)
        return rel.as_posix()

    completed = errors = 0
    last = ""
    checkpoint(target, len(source_paths), completed, errors, last, started)
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(convert, path): path for path in source_paths}
        for future in as_completed(futures):
            try:
                last = future.result()
                completed += 1
            except Exception:
                errors += 1
                raise
            if completed % 250 == 0:
                checkpoint(target, len(source_paths), completed, errors, last, started)
    checkpoint(target, len(source_paths), completed, errors, last, started)
    print(json.dumps({"target": str(target), "source_html": len(source_paths), "generated_html": completed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
