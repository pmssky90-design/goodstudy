from __future__ import annotations

import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASE = ROOT / "output"
APPLY_OUTPUT = "--apply-output" in sys.argv
TARGET = BASE if APPLY_OUTPUT else ROOT / "candidate_output_mobile_contact"
SOURCE_CSS = ROOT / "assets" / "css" / "mobile-contact-cta.css"
WEB_CSS = "/assets/css/mobile-contact-cta.css"
TARGET_CSS = TARGET / WEB_CSS.lstrip("/")
REPORT = ROOT / "audit" / (
    "mobile-contact-production.json" if APPLY_OUTPUT else "mobile-contact-candidate.json"
)

PHONE_DISPLAY = "010-4947-9030"
TEL_URI = "tel:01049479030"
SMS_URI = "sms:01049479030"

HEAD_RE = re.compile(r"<head\b[^>]*>(.*?)</head>", re.I | re.S)
BODY_RE = re.compile(r"<body\b[^>]*>(.*?)</body>", re.I | re.S)
CTA_RE = re.compile(
    r'<div\s+class="goodstudy-mobile-contact-cta">.*?</div>', re.I | re.S
)
CSS_LINK_RE = re.compile(
    r'\s*<link\s+rel="stylesheet"\s+href="/assets/css/mobile-contact-cta\.css"\s*/?>', re.I
)
TEL_RE = re.compile(r'href="tel:([^"]*)"', re.I)
SMS_RE = re.compile(r'href="sms:([^"]*)"', re.I)
THUMBNAIL_META_RE = re.compile(
    r'<meta\b(?=[^>]*\bproperty=["\']og:image["\'])[^>]*>', re.I
)

CTA_HTML = (
    '<div class="goodstudy-mobile-contact-cta">'
    '<a class="goodstudy-mobile-contact-call" href="tel:01049479030" aria-label="전화 문의">전화</a>'
    '<a class="goodstudy-mobile-contact-sms" href="sms:01049479030" aria-label="문자 문의">문자</a>'
    "</div>"
)


def read_exact(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def strip_allowed(text: str) -> str:
    return CSS_LINK_RE.sub("", CTA_RE.sub("", text))


def apply_cta(text: str) -> str:
    if not HEAD_RE.search(text) or not BODY_RE.search(text):
        raise RuntimeError("head or body missing")
    cleaned = strip_allowed(text)
    head = HEAD_RE.search(cleaned)
    newline = "\r\n" if "\r\n" in head.group(1) else "\n"
    css_link = f'  <link rel="stylesheet" href="{WEB_CSS}">{newline}'
    output = cleaned[: head.end(1)] + css_link + cleaned[head.end(1) :]
    body = BODY_RE.search(output)
    return output[: body.end(1)] + CTA_HTML + output[body.end(1) :]


def main() -> None:
    unknown = set(sys.argv[1:]) - {"--apply-output"}
    if unknown:
        raise RuntimeError(f"unknown arguments: {sorted(unknown)}")
    if not SOURCE_CSS.is_file():
        raise RuntimeError("mobile CTA CSS missing")

    base_paths = sorted(BASE.rglob("*.html"))
    if len(base_paths) != 30457:
        raise RuntimeError(f"unexpected HTML count: {len(base_paths)}")
    if not TARGET.exists():
        shutil.copytree(BASE, TARGET)
    TARGET_CSS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_CSS, TARGET_CSS)

    def convert(base_path: Path) -> tuple[int, str]:
        relative = base_path.relative_to(BASE)
        target_path = TARGET / relative
        before = read_exact(base_path)
        current = read_exact(target_path) if target_path.exists() else before
        try:
            after = apply_cta(before)
            if strip_allowed(after) != strip_allowed(before):
                raise RuntimeError("non-CTA HTML changed")
            if len(CTA_RE.findall(after)) != 1:
                raise RuntimeError("CTA wrapper count is not one")
            if TEL_RE.findall(after) != ["01049479030"]:
                raise RuntimeError("telephone URI mismatch")
            if SMS_RE.findall(after) != ["01049479030"]:
                raise RuntimeError("SMS URI mismatch")
            if len(CSS_LINK_RE.findall(after)) != 1:
                raise RuntimeError("CTA CSS link count is not one")
            if len(THUMBNAIL_META_RE.findall(after)) != len(THUMBNAIL_META_RE.findall(before)):
                raise RuntimeError("search thumbnail metadata changed")
            changed = int(current != after)
            if changed:
                target_path.write_text(after, encoding="utf-8", newline="")
            return changed, ""
        except Exception as exc:
            return 0, f"{relative.as_posix()}: {exc}"

    with ThreadPoolExecutor(max_workers=24) as pool:
        converted = list(pool.map(convert, base_paths, chunksize=64))
    errors = [row[1] for row in converted if row[1]]

    def inspect(path: Path) -> tuple[int, int, int, int, int, int]:
        text = read_exact(path)
        wrappers = len(CTA_RE.findall(text))
        tel = TEL_RE.findall(text)
        sms = SMS_RE.findall(text)
        links = len(CSS_LINK_RE.findall(text))
        body = BODY_RE.search(text)
        body_html = body.group(1) if body else ""
        return (
            int(wrappers == 0), int(wrappers > 1),
            int(tel != ["01049479030"]), int(sms != ["01049479030"]),
            int(links != 1), int("/assets/images/search-thumbnails/" not in text or not body),
        )

    target_paths = sorted(TARGET.rglob("*.html"))
    with ThreadPoolExecutor(max_workers=24) as pool:
        inspected = list(pool.map(inspect, target_paths, chunksize=64))
    totals = [sum(row[index] for row in inspected) for index in range(6)]
    css = read_exact(SOURCE_CSS)
    css_checks = {
        "default_hidden": bool(re.search(r"\.goodstudy-mobile-contact-cta\s*\{[^}]*display\s*:\s*none", css, re.S)),
        "mobile_breakpoint": "@media (max-width: 768px)" in css,
        "mobile_display": bool(re.search(r"@media \(max-width: 768px\).*?\.goodstudy-mobile-contact-cta\s*\{[^}]*display\s*:\s*flex", css, re.S)),
        "fixed_position": "position: fixed" in css,
        "safe_area": "env(safe-area-inset-bottom" in css,
        "min_height_48": "min-height: 48px" in css,
        "viewport_width_bound": "max-width: calc(100vw - 24px)" in css,
    }
    passed = not errors and not any(totals) and all(css_checks.values()) and len(target_paths) == 30457
    report = {
        "status": "PASS" if passed else "FAIL",
        "mode": "output" if APPLY_OUTPUT else "candidate",
        "total_html": len(target_paths),
        "changed_html_this_run": sum(row[0] for row in converted),
        "cta_applied": len(target_paths) - totals[0],
        "cta_missing": totals[0],
        "cta_duplicate_pages": totals[1],
        "wrong_tel_pages": totals[2],
        "wrong_sms_pages": totals[3],
        "wrong_css_link_pages": totals[4],
        "search_thumbnail_missing_pages": totals[5],
        "phone_display": PHONE_DISPLAY,
        "tel_uri": TEL_URI,
        "sms_uri": SMS_URI,
        "css_checks": css_checks,
        "errors": errors[:100],
    }
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
