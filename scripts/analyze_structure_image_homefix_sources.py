from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit"
TERMS = [
    "수학과외 찾기", "영어과외 찾기", "학교별 과외 찾기", "지역별 학교 살펴보기",
    "home-explore-section", "school-explore", "subject-explore",
]
IMAGE_TERMS = ["<img", "content-fixed-image", "hero", "home-hero", "assets/images", 'loading="lazy"']
AUDIT_NAMES = [
    "current-candidate.json", "structure-full-audit.json", "home-navigation-preview-audit.json",
    "home-navigation-analysis.md", "navigation-hierarchy-preview-audit.json", "structure-analysis.md",
]


def file_count(path: Path, suffixes: tuple[str, ...]) -> int:
    return sum(1 for item in path.rglob("*") if item.is_file() and item.suffix.lower() in suffixes)


def candidate_record(path: Path) -> dict[str, object]:
    home = path / "index.html"
    source = home.read_text(encoding="utf-8") if home.is_file() else ""
    html_paths = ([home] if home.is_file() else []) + list(path.glob("*/index.html"))
    images = path / "assets" / "images"
    return {
        "candidate": str(path),
        "exists": path.is_dir(),
        "html_count": len(html_paths),
        "candidate_mtime": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(),
        "home_mtime": datetime.fromtimestamp(home.stat().st_mtime).astimezone().isoformat() if home.is_file() else "",
        "home_terms": {term: term in source for term in TERMS},
        "home_image_terms": {term: term.lower() in source.lower() for term in IMAGE_TERMS},
        "home_img_tags": len(re.findall(r"<img\b", source, re.I)),
        "assets_images_exists": images.is_dir(),
        "image_file_count": file_count(images, (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif")) if images.is_dir() else 0,
        "css_file_count": file_count(path / "assets" / "css", (".css",)) if (path / "assets" / "css").is_dir() else 0,
        "structure_css_exists": (path / "assets" / "css" / "structure-preview.css").is_file(),
        "home_navigation_css_exists": (path / "assets" / "css" / "home-navigation-preview.css").is_file(),
        "image_css_exists": (path / "assets" / "css" / "image-preview.css").is_file(),
    }


def audit_record(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    text = path.read_text(encoding="utf-8")
    parsed = None
    if path.suffix == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            pass
    target_keys = ("target", "candidate_path", "preview_candidate", "baseline_candidate", "source")
    targets = {}
    if isinstance(parsed, dict):
        for key in target_keys:
            if key in parsed:
                targets[key] = parsed[key]
        summary = parsed.get("summary", {})
    else:
        summary = {}
    return {
        "path": str(path), "exists": True,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(),
        "status": parsed.get("status", "") if isinstance(parsed, dict) else ("PASS" if "PASS" in text else ""),
        "targets": targets,
        "home_navigation_related": any(term in text for term in ("home-navigation", "home_explore", "new_math_links", "subject-explore")),
        "image_related": any(term in text for term in ("image", "이미지", "og_image", "content-fixed-image")),
        "summary": summary,
    }


def main() -> None:
    candidates = sorted(path for path in ROOT.glob("candidate_output*") if path.is_dir())
    report = {
        "completed_at": datetime.now().astimezone().isoformat(),
        "candidates": [candidate_record(path) for path in candidates],
        "audits": [audit_record(AUDIT / name) for name in AUDIT_NAMES],
    }
    output = AUDIT / "structure-image-homefix-source-inventory.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
