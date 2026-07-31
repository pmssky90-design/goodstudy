from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "candidate_output_titleclean_recovery"
BASELINE = ROOT / "candidate_output_titlefix"
BATCH_DIR = ROOT / "audit" / "titleclean_batches"
LIST_FILE = ROOT / "intermediate" / "titleclean-audit-file-list.txt"
HASH_FILE = ROOT / "intermediate" / "titleclean-audit-file-list.sha256"
STATE_FILE = ROOT / "intermediate" / "titleclean-audit-batch-state.json"
OUT_JSON = ROOT / "audit" / "titleclean-batch-audit.json"
OUT_MD = ROOT / "audit" / "titleclean-batch-audit.md"
OUT_ERRORS = ROOT / "audit" / "titleclean-batch-audit-errors.csv"
OUT_BROKEN = ROOT / "audit" / "titleclean-batch-broken-links.csv"
CURRENT = ROOT / "audit" / "current-candidate.json"
BATCH_SIZE = 2000
RULE_VERSION = "titleclean-batch-v2-geoname-exception"
ENGLISH_BAD = ("연산", "계산 정확도", "함수", "방정식", "도형", "수식", "수학 유형", "수학 개념", "문제 풀이 속도")
YEONSAN_PLACE_NAMES = ("연산1동", "연산2동", "연산3동", "연산4동", "연산5동", "연산6동", "연산8동", "연산동")


def atomic_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding=encoding, newline="\n") as handle:
        handle.write(text); handle.flush(); os.fsync(handle.fileno())
    os.replace(temp, path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def normalized(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def url_path(url: str) -> str:
    path = unquote(urlsplit(url).path)
    return path if path.endswith("/") else path + "/"


def sitemap(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    try:
        root = ET.parse(path).getroot()
        urls = [(node.text or "").strip() for node in root.findall(".//{*}loc")]
    except Exception as exc:
        return [], [repr(exc)]
    return urls, errors


def main() -> int:
    paths = LIST_FILE.read_text(encoding="utf-8").splitlines()
    digest = HASH_FILE.read_text(encoding="ascii").strip()
    batches = (len(paths) + BATCH_SIZE - 1) // BATCH_SIZE
    values: list[dict[str, object]] = []
    missing: list[int] = []
    for index in range(1, batches + 1):
        path = BATCH_DIR / f"batch-{index:04d}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            expected = min(BATCH_SIZE, len(paths) - (index - 1) * BATCH_SIZE)
            if value.get("status") != "complete" or value.get("processed_count") != expected or value.get("file_list_hash") != digest:
                raise ValueError("invalid batch metadata")
            values.append(value)
        except Exception:
            missing.append(index)
    if missing:
        print(f"incomplete batches: {missing}", file=sys.stderr)
        return 2
    counts: Counter[str] = Counter()
    records: list[dict[str, object]] = []
    for value in values:
        counts.update(value.get("counts", {}))
        records.extend(value.get("records", []))
    # Re-evaluate only the English/math-expression rule from stored batch titles.
    # A place-name is exempt only when the same administrative name is present in
    # the slug; any remaining "연산" or other math term still fails.
    english_conflicts = 0
    geoname_exceptions: list[dict[str, str]] = []
    for record in records:
        if "영어" not in str(record.get("page_type") or ""):
            continue
        title = str(record.get("title") or "")
        slug = str(record.get("slug") or "")
        checked = title
        matched_places: list[str] = []
        for place_name in YEONSAN_PLACE_NAMES:
            if place_name in slug and place_name in checked:
                checked = checked.replace(place_name, "")
                matched_places.append(place_name)
        raw_hit = any(term in title for term in ENGLISH_BAD)
        remaining_hit = any(term in checked for term in ENGLISH_BAD)
        if remaining_hit:
            english_conflicts += 1
        elif raw_hit and matched_places:
            geoname_exceptions.append({
                "relative_path": str(record.get("relative_path") or ""),
                "place_name": ",".join(matched_places),
                "title": title,
            })
    counts["english_title_math_expression"] = english_conflicts
    titles = [str(r.get("title") or "") for r in records]
    descriptions = [str(r.get("description") or "") for r in records]
    canonicals = [str(r.get("canonical") or "") for r in records]
    exact = Counter(titles)
    normal = Counter(normalized(x) for x in titles)
    desc_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        desc_groups[str(record.get("description") or "")].append(record)
    duplicate_desc = [group for text, group in desc_groups.items() if text and len(group) > 1]
    same_type_groups = sum(any(c > 1 for c in Counter(str(x.get("page_type")) for x in group).values()) for group in duplicate_desc)
    cross_type_groups = sum(len({str(x.get("page_type")) for x in group}) > 1 for group in duplicate_desc)
    url_set = {"/" if p == "index.html" else "/" + str(Path(p).parent).replace("\\", "/") + "/" for p in paths}
    adjacency: dict[str, set[str]] = {}
    broken: list[dict[str, str]] = []
    self_links = 0
    for record in records:
        rel = str(record.get("relative_path"))
        current = "/" if rel == "index.html" else "/" + str(Path(rel).parent).replace("\\", "/") + "/"
        links = set(str(x) for x in record.get("internal_links", []))
        adjacency[current] = links
        self_links += int(current in links)
        for link in links:
            if link not in url_set:
                broken.append({"source": current, "target": link})
    incoming = Counter(link for links in adjacency.values() for link in links if link in url_set)
    orphans = sorted(path for path in url_set if path != "/" and incoming[path] == 0)
    reachable, queue = {"/"}, deque(["/"])
    while queue:
        for link in adjacency.get(queue.popleft(), set()):
            if link in adjacency and link not in reachable:
                reachable.add(link); queue.append(link)
    unreachable = sorted(url_set - reachable)
    target_urls, target_sitemap_errors = sitemap(TARGET / "sitemap.xml")
    source_urls, source_sitemap_errors = sitemap(BASELINE / "sitemap.xml")
    sitemap_counts = {
        "parse_errors": len(target_sitemap_errors), "url_count": len(target_urls),
        "duplicate_urls": sum(v - 1 for v in Counter(target_urls).values() if v > 1),
        "content_set_mismatch": int({url_path(x) for x in target_urls} != url_set),
        "baseline_url_set_changed": int(set(target_urls) != set(source_urls)),
        "www_urls": sum("www." in x for x in target_urls),
        "http_urls": sum(x.startswith("http://") for x in target_urls),
        "index_html_urls": sum("index.html" in x for x in target_urls),
        "double_slash_paths": sum("//" in urlsplit(x).path for x in target_urls),
    }
    summary = {
        "html_count": len(paths), "processed_html": len(records), "total_batches": batches,
        "completed_batches": len(values), "failed_batches": 0, "missing_batches": missing,
        "zero_byte_html": counts["zero_byte"], "read_errors": counts["read_errors"],
        "empty_title": counts["empty_title"], "empty_description": counts["empty_description"],
        "exact_duplicate_title_groups": sum(v > 1 for v in exact.values()),
        "exact_duplicate_title_pages": sum(v for v in exact.values() if v > 1),
        "normalized_duplicate_title_groups": sum(v > 1 for v in normal.values()),
        "title_equals_slug": counts["title_equals_slug"],
        "math_title_english_expression": counts["math_title_english_expression"],
        "english_title_math_expression": counts["english_title_math_expression"],
        "english_geoname_exceptions": geoname_exceptions,
        "general_title_subject_bias": counts["general_title_subject_bias"],
        "word_repeated_3_or_more": counts["word_repeated_3_or_more"],
        "jsonld_missing": counts["jsonld_missing"], "jsonld_parsing_errors": counts["jsonld_parsing_errors"],
        "jsonld_url_mismatch": counts["jsonld_url_mismatch"],
        "canonical_duplicates": sum(v > 1 for v in Counter(canonicals).values()),
        "broken_internal_links": len(broken), "orphan_pages": len(orphans),
        "home_unreachable_pages": len(unreachable), "self_links": self_links,
        "slug_changes": counts["slug_changed"], "canonical_changes": counts["canonical_changed"],
        "description_changes": counts["description_changed"], "internal_link_changes": counts["internal_links_changed"],
        "school_connection_changes": counts["school_connections_changed"],
        "parent_relation_changes": counts["parent_relations_changed"],
        "page_count_changes": len(paths) - 30457,
        "title_has_좋은공부": counts["title_has_좋은공부"], "title_has_GoodStudy": counts["title_has_GoodStudy"],
        "title_has_전국과외": counts["title_has_전국과외"],
        "description_duplicates": {
            "groups": len(duplicate_desc), "pages": sum(len(x) for x in duplicate_desc),
            "excess": sum(len(x) - 1 for x in duplicate_desc),
            "same_page_type_groups": same_type_groups, "cross_page_type_groups": cross_type_groups,
        },
        "sitemap": sitemap_counts,
    }
    required_zero = [
        "zero_byte_html", "read_errors", "empty_title", "empty_description",
        "exact_duplicate_title_groups", "normalized_duplicate_title_groups", "title_equals_slug",
        "math_title_english_expression", "english_title_math_expression", "general_title_subject_bias",
        "word_repeated_3_or_more", "jsonld_missing", "jsonld_parsing_errors", "jsonld_url_mismatch",
        "canonical_duplicates", "broken_internal_links", "orphan_pages", "home_unreachable_pages",
        "slug_changes", "canonical_changes", "description_changes", "internal_link_changes",
        "school_connection_changes", "page_count_changes", "title_has_좋은공부", "title_has_GoodStudy",
        "title_has_전국과외",
    ]
    passed = len(paths) == 30457 and len(records) == 30457 and all(summary[x] == 0 for x in required_zero) and all(
        sitemap_counts[x] == 0 for x in ("parse_errors", "duplicate_urls", "content_set_mismatch", "baseline_url_set_changed", "www_urls", "http_urls", "index_html_urls", "double_slash_paths")
    )
    report = {
        "status": "PASS" if passed else "FAIL", "status_code": "STATE_D_COMPLETE" if passed else "STATE_C_AUDIT_COMPLETE_FAIL",
        "rule_version": RULE_VERSION, "file_list_hash": digest, "completed_at": datetime.now().astimezone().isoformat(),
        "target": str(TARGET), "baseline": str(BASELINE), "summary": summary,
        "details": {"orphan_pages": orphans[:200], "home_unreachable_pages": unreachable[:200]},
    }
    error_rows: list[dict[str, object]] = []
    exception_paths = {item["relative_path"] for item in geoname_exceptions}
    for value in values:
        csv_path = BATCH_DIR / f"batch-{int(value['batch_index']):04d}-errors.csv"
        if csv_path.exists():
            error_rows.extend(
                row for row in csv.DictReader(csv_path.open(encoding="utf-8-sig", newline=""))
                if not (row.get("code") == "english_title_math_expression" and row.get("relative_path") in exception_paths)
            )
    atomic_json(OUT_JSON, report)
    lines = ["# Titleclean 배치 감사", "", f"- 판정: **{report['status']}**", f"- 상태 코드: `{report['status_code']}`", f"- HTML: {len(records):,}", f"- 배치: {len(values)}/{batches}", "", "## 핵심 집계", ""]
    lines.extend(f"- {key}: {value}" for key, value in summary.items() if not isinstance(value, dict))
    lines += ["", "## Description 중복", "", *(f"- {k}: {v}" for k, v in summary["description_duplicates"].items()), "", "## Sitemap", "", *(f"- {k}: {v}" for k, v in sitemap_counts.items())]
    lines += ["", "## 영어 제목 지명 예외", "", f"- 예외 처리: {len(geoname_exceptions)}건"]
    lines.extend(f"- `{item['relative_path']}` — {item['place_name']}" for item in geoname_exceptions)
    atomic_text(OUT_MD, "\n".join(lines) + "\n")
    error_fields = ["relative_path", "code", "detail"]
    temp = OUT_ERRORS.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, error_fields); writer.writeheader(); writer.writerows(error_rows)
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temp, OUT_ERRORS)
    temp = OUT_BROKEN.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, ["source", "target"]); writer.writeheader(); writer.writerows(broken)
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temp, OUT_BROKEN)
    if passed:
        atomic_json(CURRENT, {"candidate_path": str(TARGET), "status": "PASS", "reason": "Chunked title-clean audit passed", "html_count": 30457})
    print(json.dumps({"status": report["status"], "summary": summary}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
