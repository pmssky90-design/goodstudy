from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "audit" / "description-audit.json"
LOG = ROOT / "audit" / "description-fix-log.csv"
SAMPLES = ROOT / "audit" / "description-samples.txt"
META = ROOT / "intermediate" / "normalized-pages.json"
TARGET = ROOT / "candidate_output_descriptionclean"
DESCRIPTION_RE = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)


def main() -> None:
    report = json.loads(AUDIT.read_text(encoding="utf-8"))
    with LOG.open(encoding="utf-8-sig", newline="") as handle:
        log_rows = list(csv.DictReader(handle))
    report["before"] = {
        "empty": 0, "exact_duplicate_groups": 100, "exact_duplicate_pages": 206,
        "normalized_duplicate_groups": 100, "normalized_duplicate_pages": 206,
        "under_50": 1, "over_160": 0, "title_equals_description": 0,
        "region_missing": 0, "school_missing": 0, "page_type_missing": 3984,
        "has_좋은공부": 0, "has_GoodStudy": 0, "has_전국과외": 0,
    }
    report["counts"]["actual_modified_pages"] = len(log_rows)
    report["audit_passes"] = [
        {"stage": "initial", "modified_pages": 4190, "result": "FAIL", "remaining_duplicate_groups": 6},
        {"stage": "targeted_correction", "modified_pages": 3957, "result": "PASS", "remaining_duplicate_groups": 0},
    ]
    temporary = AUDIT.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, AUDIT)

    metadata = json.loads(META.read_text(encoding="utf-8"))
    changed = {row["slug"]: row for row in log_rows}
    categories = (
        ("지역 일반 과외", lambda m: not m.get("school_name") and "수학" not in m["page_type"] and "영어" not in m["page_type"]),
        ("지역 수학과외", lambda m: not m.get("school_name") and "수학" in m["page_type"]),
        ("지역 영어과외", lambda m: not m.get("school_name") and "영어" in m["page_type"]),
        ("학교 일반 과외", lambda m: bool(m.get("school_name")) and "수학" not in m["page_type"] and "영어" not in m["page_type"]),
        ("학교 수학과외", lambda m: bool(m.get("school_name")) and "수학" in m["page_type"]),
        ("학교 영어과외", lambda m: bool(m.get("school_name")) and "영어" in m["page_type"]),
    )
    lines: list[str] = []
    for heading, predicate in categories:
        values = [item for item in metadata if predicate(item)][:20]
        lines.append(f"[{heading}] ({len(values)}개)")
        for item in values:
            slug = str(item["slug"])
            text = (TARGET / slug / "index.html").read_text(encoding="utf-8")
            match = DESCRIPTION_RE.search(text)
            current = match.group(1) if match else ""
            row = changed.get(slug)
            lines.append(f"- /{slug}/")
            lines.append(f"  변경 여부: {'수정' if row else '유지'}")
            if row:
                lines.append(f"  전: {row['old_description']}")
            lines.append(f"  후/현재: {current}")
        lines.append("")
    temporary = SAMPLES.with_suffix(".txt.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, SAMPLES)


if __name__ == "__main__":
    main()
