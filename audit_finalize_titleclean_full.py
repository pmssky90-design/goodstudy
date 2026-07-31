from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BATCH_DIR = ROOT / "audit" / "titleclean_batches"
SOURCE_REPORT = ROOT / "audit" / "titleclean-batch-audit.json"
OUT_JSON = ROOT / "audit" / "titleclean-full-audit.json"
OUT_MD = ROOT / "audit" / "titleclean-full-audit.md"
CURRENT = ROOT / "audit" / "current-candidate.json"
TARGET = ROOT / "candidate_output_titleclean_recovery"


def atomic_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def main() -> None:
    merged = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))
    batches = []
    for index in range(1, 17):
        value = json.loads((BATCH_DIR / f"batch-{index:04d}.json").read_text(encoding="utf-8"))
        if value.get("status") != "complete":
            raise RuntimeError(f"incomplete batch {index}")
        batches.append(value)
    counts: Counter[str] = Counter()
    records = []
    for batch in batches:
        counts.update(batch.get("counts", {}))
        records.extend(batch.get("records", []))
    summary = dict(merged["summary"])
    modified_title_pages = sum(
        record.get("target_sha256") != record.get("baseline_sha256")
        for record in records
    )
    metadata = {
        "description_missing": counts["empty_description"],
        "canonical_missing": counts["canonical_missing"],
        "og_title_missing": counts["og_title_missing"],
        "og_description_missing": counts["og_description_missing"],
        "og_url_missing": counts["og_url_missing"],
        "twitter_title_missing": counts["twitter_title_missing"],
        "og_url_canonical_mismatch": counts["og_url_mismatch"],
    }
    comparison = {
        "slug_changes": summary["slug_changes"],
        "canonical_changes": summary["canonical_changes"],
        "description_changes": summary["description_changes"],
        "sitemap_url_changes": summary["sitemap"]["baseline_url_set_changed"],
        "internal_link_changes": summary["internal_link_changes"],
        "school_connection_changes": summary["school_connection_changes"],
        "page_count_changes": summary["page_count_changes"],
    }
    passed = (
        merged.get("status") == "PASS"
        and summary["html_count"] == 30457
        and summary["processed_html"] == 30457
        and all(value == 0 for value in metadata.values())
        and all(value == 0 for value in comparison.values())
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "status_code": "STATE_D_COMPLETE" if passed else "STATE_C_AUDIT_COMPLETE_FAIL",
        "target": str(TARGET),
        "baseline": str(ROOT / "candidate_output_titlefix"),
        "completed_at": datetime.now().astimezone().isoformat(),
        "audit_source": {
            "batch_count": len(batches),
            "processed_records": len(records),
            "file_list_hash": merged["file_list_hash"],
            "rule_version": merged["rule_version"],
        },
        "summary": {
            **summary,
            "title_modified_pages": modified_title_pages,
            "title_over_100": counts["title_over_100"],
            "metadata": metadata,
            "baseline_comparison": comparison,
        },
    }
    atomic_json(OUT_JSON, report)
    lines = [
        "# Titleclean 전수 감사",
        "",
        f"- 판정: **{report['status']}**",
        f"- 상태 코드: `{report['status_code']}`",
        f"- 검사 HTML: {summary['processed_html']:,} / {summary['html_count']:,}",
        f"- 제목 수정 페이지: {modified_title_pages:,}",
        "",
        "## Title 및 표현",
        "",
        f"- 완전 동일 title 그룹: {summary['exact_duplicate_title_groups']}",
        f"- 정규화 title 중복 그룹: {summary['normalized_duplicate_title_groups']}",
        f"- title과 slug 동일: {summary['title_equals_slug']}",
        f"- 100자 초과 title: {counts['title_over_100']}",
        f"- 수학 제목 영어 표현: {summary['math_title_english_expression']}",
        f"- 영어 제목 수학 표현: {summary['english_title_math_expression']}",
        f"- 일반 과외 과목 편향: {summary['general_title_subject_bias']}",
        f"- 동일 단어 3회 이상 반복: {summary['word_repeated_3_or_more']}",
        "",
        "## 구조 및 링크",
        "",
        f"- JSON-LD 누락: {summary['jsonld_missing']}",
        f"- JSON-LD 파싱 오류: {summary['jsonld_parsing_errors']}",
        f"- JSON-LD URL 불일치: {summary['jsonld_url_mismatch']}",
        f"- canonical 중복: {summary['canonical_duplicates']}",
        f"- sitemap 중복: {summary['sitemap']['duplicate_urls']}",
        f"- 깨진 링크: {summary['broken_internal_links']}",
        f"- 고아 페이지: {summary['orphan_pages']}",
        f"- 홈 도달 불가: {summary['home_unreachable_pages']}",
        "",
        "## 기준 후보 비교",
        "",
        *(f"- {key}: {value}" for key, value in comparison.items()),
        "",
        "## Meta 누락 및 불일치",
        "",
        *(f"- {key}: {value}" for key, value in metadata.items()),
    ]
    atomic_text(OUT_MD, "\n".join(lines) + "\n")
    if passed:
        atomic_json(CURRENT, {
            "candidate_path": str(TARGET),
            "status": "PASS",
            "reason": "Full title-clean audit passed",
            "html_count": 30457,
        })
    print(json.dumps({
        "status": report["status"],
        "status_code": report["status_code"],
        "html_count": summary["html_count"],
        "title_modified_pages": modified_title_pages,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
