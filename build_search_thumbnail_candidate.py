from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from config import SITE_URL


ROOT = Path(__file__).resolve().parent
BASE = ROOT / "output"
APPLY_OUTPUT = "--apply-output" in sys.argv
TARGET = BASE if APPLY_OUTPUT else ROOT / "candidate_output_search_thumbnail"
SOURCE_IMAGES = ROOT / "assets" / "images" / "search-thumbnails"
WEB_IMAGE_DIR = "/assets/images/search-thumbnails"
TARGET_IMAGES = TARGET / WEB_IMAGE_DIR.lstrip("/")
REPORT_PATH = ROOT / "audit" / (
    "search-thumbnail-production.json" if APPLY_OUTPUT else "search-thumbnail-candidate.json"
)

CANONICAL_RE = re.compile(
    r'<link\b(?=[^>]*\brel=["\']canonical["\'])[^>]*\bhref=(["\'])(.*?)\1[^>]*>', re.I
)
HEAD_RE = re.compile(r"<head\b[^>]*>(.*?)</head>", re.I | re.S)
BODY_RE = re.compile(r"<body\b[^>]*>.*?</body>", re.I | re.S)
OG_IMAGE_RE = re.compile(
    r'\s*<meta\b(?=[^>]*\bproperty=["\']og:image(?::(?:width|height|alt|type))?["\'])[^>]*>', re.I
)
TWITTER_IMAGE_RE = re.compile(
    r'\s*<meta\b(?=[^>]*\b(?:name|property)=["\']twitter:image["\'])[^>]*>', re.I
)
OG_PRIMARY_RE = re.compile(r'<meta\b(?=[^>]*\bproperty=["\']og:image["\'])[^>]*>', re.I)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text_exact(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def canonical(text: str) -> str:
    match = CANONICAL_RE.search(text)
    if not match:
        raise RuntimeError("canonical missing")
    value = match.group(2)
    if not value.startswith(SITE_URL.rstrip("/") + "/") and value != SITE_URL.rstrip("/"):
        raise RuntimeError(f"unexpected canonical: {value}")
    return value


def select_image(canonical_url: str, images: list[dict[str, object]]) -> dict[str, object]:
    digest = hashlib.sha256(canonical_url.encode("utf-8")).digest()
    return images[int.from_bytes(digest[:8], "big") % len(images)]


def apply_metadata(text: str, image: dict[str, object]) -> str:
    head_match = HEAD_RE.search(text)
    if not head_match:
        raise RuntimeError("head missing")
    head = head_match.group(1)
    head = OG_IMAGE_RE.sub("", head)
    head = TWITTER_IMAGE_RE.sub("", head)
    newline = "\r\n" if "\r\n" in head else "\n"
    tags = (
        f'  <meta property="og:image" content="{image["url"]}">{newline}'
        f'  <meta property="og:image:width" content="{image["width"]}">{newline}'
        f'  <meta property="og:image:height" content="{image["height"]}">{newline}'
        f'  <meta property="og:image:type" content="{image["mime"]}">{newline}'
        f'  <meta property="og:image:alt" content="좋은공부 지역·학교별 맞춤 학습 정보">{newline}'
        f'  <meta name="twitter:image" content="{image["url"]}">{newline}'
    )
    new_head = head + tags
    return text[: head_match.start(1)] + new_head + text[head_match.end(1) :]


def main() -> None:
    unknown_arguments = set(sys.argv[1:]) - {"--apply-output"}
    if unknown_arguments:
        raise RuntimeError(f"unknown arguments: {sorted(unknown_arguments)}")
    source_paths = [path for path in BASE.rglob("*.html") if path.is_file()]
    source_paths.sort(key=lambda path: path.relative_to(BASE).as_posix())
    if not source_paths:
        raise RuntimeError("output HTML not found")

    source_images = sorted(SOURCE_IMAGES.glob("search-thumb-*.png"), key=lambda path: path.name)
    if not source_images:
        raise RuntimeError("thumbnail source images not found")

    images: list[dict[str, object]] = []
    hashes: set[str] = set()
    for index, source in enumerate(source_images, 1):
        digest = file_hash(source)
        if digest in hashes:
            raise RuntimeError(f"duplicate image content: {source.name}")
        hashes.add(digest)
        with Image.open(source) as opened:
            width, height = opened.size
            opened.verify()
        extension = source.suffix.lower()
        safe_name = f"search-thumb-{index:02d}{extension}"
        images.append(
            {
                "source": source,
                "source_name": source.name,
                "filename": safe_name,
                "url": f"{SITE_URL.rstrip('/')}{WEB_IMAGE_DIR}/{safe_name}",
                "width": width,
                "height": height,
                "bytes": source.stat().st_size,
                "mime": mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
                "sha256": digest,
            }
        )

    if not TARGET.exists():
        shutil.copytree(BASE, TARGET)
    TARGET_IMAGES.mkdir(parents=True, exist_ok=True)
    for image in images:
        destination = TARGET_IMAGES / str(image["filename"])
        if not destination.exists() or file_hash(destination) != image["sha256"]:
            shutil.copy2(image["source"], destination)

    def convert(source_path: Path) -> tuple[str, int, str]:
        relative = source_path.relative_to(BASE)
        target_path = TARGET / relative
        before = read_text_exact(source_path)
        current = read_text_exact(target_path) if target_path.exists() else before
        try:
            canonical_url = canonical(before)
            image = select_image(canonical_url, images)
            after = apply_metadata(before, image)
            if BODY_RE.search(before).group(0) != BODY_RE.search(after).group(0):
                raise RuntimeError("body changed")
            stripped = TWITTER_IMAGE_RE.sub("", OG_IMAGE_RE.sub("", after))
            if stripped != TWITTER_IMAGE_RE.sub("", OG_IMAGE_RE.sub("", before)):
                raise RuntimeError("non-thumbnail HTML changed")
            head = HEAD_RE.search(after).group(1)
            if len(OG_PRIMARY_RE.findall(head)) != 1:
                raise RuntimeError("og:image count is not one")
            if not str(image["url"]).startswith("https://"):
                raise RuntimeError("non-HTTPS image URL")
            was_changed = int(current != after)
            if current != after:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(after, encoding="utf-8", newline="")
            return str(image["filename"]), was_changed, ""
        except Exception as exc:
            return "", 0, f"{relative.as_posix()}: {exc}"

    with ThreadPoolExecutor(max_workers=16) as pool:
        converted = list(pool.map(convert, source_paths, chunksize=64))
    distribution: Counter[str] = Counter(row[0] for row in converted if row[0])
    changed = sum(row[1] for row in converted)
    errors = [row[2] for row in converted if row[2]]

    def inspect(path: Path) -> tuple[int, int, int, int]:
        text = read_text_exact(path)
        head_match = HEAD_RE.search(text)
        tags = OG_PRIMARY_RE.findall(head_match.group(1) if head_match else "")
        missing = int(len(tags) == 0)
        duplicate = int(len(tags) > 1)
        non_https = 0
        broken = 0
        if tags:
            url_match = re.search(r'content=["\']([^"\']+)', tags[0], re.I)
            url = url_match.group(1) if url_match else ""
            non_https = int(not url.startswith("https://"))
            filename = Path(urlsplit(url).path).name
            broken = int(not (TARGET_IMAGES / filename).is_file())
        return missing, duplicate, non_https, broken

    target_paths = sorted(TARGET.rglob("*.html"))
    with ThreadPoolExecutor(max_workers=16) as pool:
        inspected = list(pool.map(inspect, target_paths, chunksize=64))
    missing = sum(row[0] for row in inspected)
    duplicate = sum(row[1] for row in inspected)
    non_https = sum(row[2] for row in inspected)
    broken = sum(row[3] for row in inspected)

    counts = [distribution[str(image["filename"])] for image in images]
    report = {
        "status": "PASS" if not errors and not missing and not duplicate and not non_https and not broken else "FAIL",
        "project": str(ROOT),
        "baseline": str(BASE),
        "candidate": str(TARGET),
        "total_html": len(source_paths),
        "candidate_images": len(images),
        "used_images": sum(count > 0 for count in counts),
        "changed_html_this_run": changed,
        "missing_og_image": missing,
        "duplicate_og_image_pages": duplicate,
        "non_https_og_image": non_https,
        "broken_image_urls": broken,
        "min_assignment": min(counts),
        "max_assignment": max(counts),
        "average_assignment": sum(counts) / len(counts),
        "distribution": {str(image["filename"]): distribution[str(image["filename"])] for image in images},
        "images": [
            {key: value for key, value in image.items() if key != "source"} for image in images
        ],
        "errors": errors[:100],
    }
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
