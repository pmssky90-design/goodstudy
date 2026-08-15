from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "output"
CANDIDATE = ROOT / "candidate_output_search_thumbnail"
REPORT = ROOT / "audit" / "search-thumbnail-preproduction-compare.json"
THUMBNAIL_DIR = Path("assets/images/search-thumbnails")

OG_IMAGE_RE = re.compile(
    rb'\s*<meta\b(?=[^>]*\bproperty=["\']og:image(?::(?:width|height|alt|type))?["\'])[^>]*>',
    re.I,
)
TWITTER_IMAGE_RE = re.compile(
    rb'\s*<meta\b(?=[^>]*\b(?:name|property)=["\']twitter:image["\'])[^>]*>',
    re.I,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compare_html(base_path: Path) -> dict[str, object]:
    relative = base_path.relative_to(BASE)
    candidate_path = CANDIDATE / relative
    if not candidate_path.is_file():
        return {"path": relative.as_posix(), "error": "candidate missing"}
    base = base_path.read_bytes()
    candidate = candidate_path.read_bytes()
    stripped_base = TWITTER_IMAGE_RE.sub(b"", OG_IMAGE_RE.sub(b"", base))
    stripped_candidate = TWITTER_IMAGE_RE.sub(b"", OG_IMAGE_RE.sub(b"", candidate))
    return {
        "path": relative.as_posix(),
        "error": "" if stripped_base == stripped_candidate else "non-thumbnail HTML differs",
        "base_sha256": sha256(stripped_base),
        "candidate_sha256": sha256(stripped_candidate),
    }


def main() -> None:
    base_html = sorted(BASE.rglob("*.html"))
    candidate_html = sorted(CANDIDATE.rglob("*.html"))
    with ThreadPoolExecutor(max_workers=24) as pool:
        rows = list(pool.map(compare_html, base_html, chunksize=64))

    base_non_html = {
        path.relative_to(BASE).as_posix(): path
        for path in BASE.rglob("*")
        if path.is_file()
        and path.suffix.lower() != ".html"
        and THUMBNAIL_DIR.as_posix() not in path.relative_to(BASE).as_posix()
    }
    candidate_non_html = {
        path.relative_to(CANDIDATE).as_posix(): path
        for path in CANDIDATE.rglob("*")
        if path.is_file()
        and path.suffix.lower() != ".html"
        and THUMBNAIL_DIR.as_posix() not in path.relative_to(CANDIDATE).as_posix()
    }
    non_html_errors: list[str] = []
    if set(base_non_html) != set(candidate_non_html):
        non_html_errors.append("non-HTML file set differs")
    for relative in sorted(set(base_non_html) & set(candidate_non_html)):
        if base_non_html[relative].read_bytes() != candidate_non_html[relative].read_bytes():
            non_html_errors.append(relative)

    thumbnail_files = sorted((CANDIDATE / THUMBNAIL_DIR).glob("search-thumb-*.png"))
    html_errors = [row for row in rows if row["error"]]
    report = {
        "status": "PASS"
        if len(base_html) == len(candidate_html) == 30457
        and not html_errors
        and not non_html_errors
        and len(thumbnail_files) == 15
        else "FAIL",
        "base_html": len(base_html),
        "candidate_html": len(candidate_html),
        "non_thumbnail_html_differences": len(html_errors),
        "non_html_differences": len(non_html_errors),
        "candidate_thumbnail_assets": len(thumbnail_files),
        "html_errors": html_errors[:100],
        "non_html_errors": non_html_errors[:100],
    }
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
