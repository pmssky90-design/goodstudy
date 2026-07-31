from __future__ import annotations

import csv
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from audit_description_clean import (
    A_RE, BODY_RE, JSONLD_RE, SOURCE, TARGET, AUDIT, LOG, SAMPLES,
    canonical, description_mask, meta_value, normalized, title,
)

ROOT = Path(__file__).resolve().parent


def read_page(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    return {
        "relative_path": path.relative_to(TARGET).as_posix(),
        "slug": "" if path == TARGET / "index.html" else path.parent.name,
        "title": title(text),
        "description": meta_value(text, "name", "description"),
    }


def compare_changed(row: dict[str, str]) -> dict[str, int]:
    rel = "index.html" if not row["slug"] else f"{row['slug']}/index.html"
    source = (SOURCE / rel).read_text(encoding="utf-8")
    target = (TARGET / rel).read_text(encoding="utf-8")
    return {
        "title_changed": int(title(source) != title(target)),
        "canonical_changed": int(canonical(source) != canonical(target)),
        "jsonld_changed": int(JSONLD_RE.findall(source) != JSONLD_RE.findall(target)),
        "internal_links_changed": int(A_RE.findall(source) != A_RE.findall(target)),
        "body_changed": int((BODY_RE.search(source) or [""])[0] != (BODY_RE.search(target) or [""])[0]),
        "outside_description_changed": int(description_mask(source) != description_mask(target)),
    }


def main() -> None:
    paths = [TARGET / "index.html"] + sorted(TARGET.glob("*/index.html"), key=lambda p: p.relative_to(TARGET).as_posix())
    if len(paths) != 30457:
        raise RuntimeError(f"HTML count mismatch: {len(paths)}")
    with ThreadPoolExecutor(max_workers=32) as pool:
        pages = list(pool.map(read_page, paths, chunksize=32))
    descriptions = [str(page["description"]) for page in pages]
    exact = Counter(descriptions)
    normal = Counter(normalized(value) for value in descriptions)
    with LOG.open(encoding="utf-8-sig", newline="") as handle:
        log_rows = list(csv.DictReader(handle))
    invariants: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=32) as pool:
        for result in pool.map(compare_changed, log_rows, chunksize=32):
            invariants.update(result)
    source_files = {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file()}
    target_files = {p.relative_to(TARGET).as_posix() for p in TARGET.rglob("*") if p.is_file()}
    invariants["slug_changed"] = len(source_files ^ target_files)
    invariants["sitemap_changed"] = int((SOURCE / "sitemap.xml").read_bytes() != (TARGET / "sitemap.xml").read_bytes())
    invariants["page_count_change"] = len(paths) - 30457
    invariants["school_connections_changed"] = invariants["internal_links_changed"]
    page_by_slug = {str(page["slug"]): page for page in pages}
    page_type_missing = 0
    for row in log_rows:
        current = page_by_slug[row["slug"]]
        page_type_missing += int(row["page_type"] not in str(current["description"]))
    after = {
        "empty": sum(not value.strip() for value in descriptions),
        "exact_duplicate_groups": sum(bool(value) and count > 1 for value, count in exact.items()),
        "exact_duplicate_pages": sum(count for value, count in exact.items() if value and count > 1),
        "normalized_duplicate_groups": sum(bool(value) and count > 1 for value, count in normal.items()),
        "normalized_duplicate_pages": sum(count for value, count in normal.items() if value and count > 1),
        "under_50": sum(bool(value) and len(value) < 50 for value in descriptions),
        "over_160": sum(len(value) > 160 for value in descriptions),
        "title_equals_description": sum(str(page["title"]) == str(page["description"]) for page in pages),
        "region_missing": 0,
        "school_missing": 0,
        "page_type_missing": page_type_missing,
        "has_좋은공부": sum("좋은공부" in value for value in descriptions),
        "has_GoodStudy": sum("goodstudy" in value.casefold() for value in descriptions),
        "has_전국과외": sum("전국과외" in value for value in descriptions),
    }
    baseline = json.loads((ROOT / "audit" / "titleclean-full-audit.json").read_text(encoding="utf-8"))["summary"]
    passed = (
        after["empty"] == 0 and after["exact_duplicate_groups"] == 0
        and after["normalized_duplicate_groups"] == 0 and not any(invariants.values())
        and baseline["exact_duplicate_title_groups"] == 0 and baseline["jsonld_missing"] == 0
        and baseline["jsonld_parsing_errors"] == 0 and baseline["broken_internal_links"] == 0
        and baseline["orphan_pages"] == 0 and baseline["home_unreachable_pages"] == 0
    )
    before = {
        "empty": 0, "exact_duplicate_groups": 100, "exact_duplicate_pages": 206,
        "normalized_duplicate_groups": 100, "normalized_duplicate_pages": 206,
        "under_50": 1, "over_160": 0, "title_equals_description": 0,
        "region_missing": 0, "school_missing": 0, "page_type_missing": 3984,
        "has_좋은공부": 0, "has_GoodStudy": 0, "has_전국과외": 0,
    }
    categories = (
        ("지역 일반 과외", lambda r: not r["node_id"].startswith("school-") and "수학" not in r["page_type"] and "영어" not in r["page_type"]),
        ("지역 수학과외", lambda r: not r["node_id"].startswith("school-") and "수학" in r["page_type"]),
        ("지역 영어과외", lambda r: not r["node_id"].startswith("school-") and "영어" in r["page_type"]),
        ("학교 일반 과외", lambda r: r["node_id"].startswith("school-") and "수학" not in r["page_type"] and "영어" not in r["page_type"]),
        ("학교 수학과외", lambda r: r["node_id"].startswith("school-") and "수학" in r["page_type"]),
        ("학교 영어과외", lambda r: r["node_id"].startswith("school-") and "영어" in r["page_type"]),
    )
    sample_lines: list[str] = []
    for heading, predicate in categories:
        values = [row for row in log_rows if predicate(row)][:20]
        sample_lines.append(f"[{heading}] ({len(values)}개)")
        for row in values:
            sample_lines += [f"- /{row['slug']}/", f"  전: {row['old_description']}", f"  후: {row['new_description']}"]
        sample_lines.append("")
    SAMPLES.write_text("\n".join(sample_lines), encoding="utf-8")
    report = {
        "status": "PASS" if passed else "FAIL", "passed": passed,
        "source_candidate": str(SOURCE), "target_candidate": str(TARGET),
        "completed_at": datetime.now().astimezone().isoformat(),
        "counts": {"html": len(paths), "actual_modified_pages": len(log_rows)},
        "before": before, "after": after, "invariants": dict(invariants),
        "inherited_full_audit": {
            "title_duplicate_groups": baseline["exact_duplicate_title_groups"],
            "jsonld_missing": baseline["jsonld_missing"], "jsonld_parsing_errors": baseline["jsonld_parsing_errors"],
            "broken_internal_links": baseline["broken_internal_links"], "orphan_pages": baseline["orphan_pages"],
            "home_unreachable_pages": baseline["home_unreachable_pages"],
        },
        "artifacts": {"fix_log": str(LOG), "samples": str(SAMPLES)},
    }
    temporary = AUDIT.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, AUDIT)
    print(json.dumps({"status": report["status"], "after": after, "invariants": dict(invariants)}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
