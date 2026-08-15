from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "output"
CANDIDATE = ROOT / "candidate_output_mobile_contact"
REPORT = ROOT / "audit" / "mobile-contact-preproduction-compare.json"
CSS_RELATIVE = Path("assets/css/mobile-contact-cta.css")

CTA_RE = re.compile(rb'<div\s+class="goodstudy-mobile-contact-cta">.*?</div>', re.I | re.S)
CSS_LINK_RE = re.compile(
    rb'\s*<link\s+rel="stylesheet"\s+href="/assets/css/mobile-contact-cta\.css"\s*/?>', re.I
)


def strip_allowed(data: bytes) -> bytes:
    return CSS_LINK_RE.sub(b"", CTA_RE.sub(b"", data))


def compare_html(path: Path) -> str:
    relative = path.relative_to(BASE)
    candidate = CANDIDATE / relative
    if not candidate.is_file():
        return f"{relative.as_posix()}: candidate missing"
    if strip_allowed(path.read_bytes()) != strip_allowed(candidate.read_bytes()):
        return f"{relative.as_posix()}: non-CTA HTML differs"
    return ""


def main() -> None:
    base_html = sorted(BASE.rglob("*.html"))
    candidate_html = sorted(CANDIDATE.rglob("*.html"))
    with ThreadPoolExecutor(max_workers=24) as pool:
        errors = [row for row in pool.map(compare_html, base_html, chunksize=64) if row]

    base_files = {
        path.relative_to(BASE).as_posix(): path
        for path in BASE.rglob("*")
        if path.is_file() and path.suffix.lower() != ".html"
    }
    candidate_files = {
        path.relative_to(CANDIDATE).as_posix(): path
        for path in CANDIDATE.rglob("*")
        if path.is_file() and path.suffix.lower() != ".html"
    }
    allowed = CSS_RELATIVE.as_posix()
    non_html_errors: list[str] = []
    if set(base_files) - {allowed} != set(candidate_files) - {allowed}:
        non_html_errors.append("non-HTML file set differs outside CTA CSS")
    for relative in sorted(set(base_files) & set(candidate_files)):
        if relative != allowed and base_files[relative].read_bytes() != candidate_files[relative].read_bytes():
            non_html_errors.append(relative)
    source_css = ROOT / CSS_RELATIVE
    candidate_css = CANDIDATE / CSS_RELATIVE
    css_match = source_css.is_file() and candidate_css.is_file() and source_css.read_bytes() == candidate_css.read_bytes()
    report = {
        "status": "PASS"
        if len(base_html) == len(candidate_html) == 30457
        and not errors and not non_html_errors and css_match else "FAIL",
        "base_html": len(base_html),
        "candidate_html": len(candidate_html),
        "non_cta_html_differences": len(errors),
        "non_html_differences": len(non_html_errors),
        "cta_css_matches_source": css_match,
        "html_errors": errors[:100],
        "non_html_errors": non_html_errors[:100],
    }
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
