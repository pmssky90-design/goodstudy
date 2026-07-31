from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "candidate_output_titleclean_recovery"
TARGET = ROOT / "candidate_output_descriptionclean"
META = ROOT / "intermediate" / "normalized-pages.json"
AUDIT = ROOT / "audit" / "description-audit.json"
LOG = ROOT / "audit" / "description-fix-log.csv"
SAMPLES = ROOT / "audit" / "description-samples.txt"

TITLE_RE = re.compile(r"(<title\b[^>]*>)(.*?)(</title\s*>)", re.I | re.S)
META_RE = re.compile(r"<meta\b[^>]*>", re.I | re.S)
ATTR_RE = re.compile(r"""([:\w-]+)\s*=\s*(['"])(.*?)\2""", re.S)
LINK_RE = re.compile(r"<link\b[^>]*>", re.I | re.S)
JSONLD_RE = re.compile(r"<script\b[^>]*\btype=(['\"])application/ld\+json\1[^>]*>.*?</script\s*>", re.I | re.S)
A_RE = re.compile(r"<a\b[^>]*\bhref=(['\"])(.*?)\1", re.I | re.S)
BODY_RE = re.compile(r"<body\b[^>]*>.*?</body\s*>", re.I | re.S)


def attrs(tag: str) -> dict[str, str]:
    return {name.lower(): html.unescape(value) for name, _, value in ATTR_RE.findall(tag)}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def title(text: str) -> str:
    match = TITLE_RE.search(text)
    return clean(match.group(2)) if match else ""


def meta_value(text: str, key: str, value: str) -> str:
    for tag in META_RE.findall(text):
        values = attrs(tag)
        if values.get(key, "").lower() == value.lower():
            return values.get("content", "")
    return ""


def canonical(text: str) -> str:
    for tag in LINK_RE.findall(text):
        values = attrs(tag)
        if "canonical" in values.get("rel", "").lower().split():
            return values.get("href", "")
    return ""


def normalized(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def primary_region(meta: dict[str, object]) -> str:
    for key in ("locality", "district", "city", "province"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return ""


def focus(page_type: str) -> str:
    if "수학" in page_type:
        return "개념 이해와 문제 적용, 오답 풀이 과정"
    if "영어" in page_type:
        return "어휘·문법 이해와 교과서 독해, 문장 적용 과정"
    return "과목별 진도와 시험 일정, 복습 습관의 균형"


def make_description(page_title: str, meta: dict[str, object]) -> str:
    page_type = str(meta.get("page_type") or "과외")
    school = str(meta.get("school_name") or "").strip()
    region = primary_region(meta)
    lead = page_title.rstrip(" .")
    variants = (
        "현재 이해도와 학교 진도를 함께 살펴 다음 학습 계획을 구체적으로 정리합니다.",
        "학생의 학습 기록과 시험 일정을 연결해 보완할 부분과 복습 순서를 안내합니다.",
        "수업 전 확인할 학습 상태와 복습 흐름을 나누어 실천 가능한 계획을 안내합니다.",
        "학교 진도에 맞춘 점검 항목과 오답 관리 흐름을 살펴 학습 방향을 정리합니다.",
    )
    variant = variants[int(hashlib.sha256(str(meta.get("node_id") or lead).encode()).hexdigest()[:8], 16) % len(variants)]
    prefix = f"{lead} 페이지의 {page_type} 학습에서는 {focus(page_type)}을 중심으로 살펴봅니다."
    result = f"{prefix} {variant}"
    if len(result) > 150:
        result = f"{lead}의 {page_type} 학습에서 진도와 복습 흐름을 점검해 다음 계획을 정리합니다."
    if len(result) < 70:
        result += " 학생의 현재 학습 상태에 맞춰 우선순위를 차분히 확인합니다."
    return result[:150].rstrip(" ,")


def replace_description_fields(text: str, value: str) -> tuple[str, int]:
    changed = 0
    escaped = html.escape(value, quote=True)
    selectors = (("name", "description"), ("property", "og:description"), ("name", "twitter:description"))
    for selector_key, selector_value in selectors:
        def repl(match: re.Match[str]) -> str:
            nonlocal changed
            tag = match.group(0)
            values = attrs(tag)
            if values.get(selector_key, "").lower() != selector_value:
                return tag
            updated = re.sub(
                r"(\bcontent=)(['\"])(.*?)\2",
                lambda m: m.group(1) + m.group(2) + escaped + m.group(2),
                tag, count=1, flags=re.I | re.S,
            )
            changed += int(updated != tag)
            return updated
        text = META_RE.sub(repl, text)
    return text, changed


def description_mask(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        values = attrs(tag)
        if (
            values.get("name", "").lower() in ("description", "twitter:description")
            or values.get("property", "").lower() == "og:description"
        ):
            return re.sub(r"(\bcontent=)(['\"])(.*?)\2", r"\1\2__DESCRIPTION__\2", tag, count=1, flags=re.I | re.S)
        return tag
    return META_RE.sub(repl, text)


def atomic_html(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".description.tmp")
    temporary.write_text(text, encoding="utf-8", newline="")
    if not TITLE_RE.search(text) or not BODY_RE.search(text):
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"invalid HTML: {path}")
    for raw in JSONLD_RE.findall(text):
        pass
    os.replace(temporary, path)


def stats(rows: list[dict[str, object]]) -> dict[str, int]:
    values = [str(row["description"]) for row in rows]
    exact = Counter(values)
    normal = Counter(normalized(value) for value in values)
    return {
        "empty": sum(not value.strip() for value in values),
        "exact_duplicate_groups": sum(bool(value) and count > 1 for value, count in exact.items()),
        "exact_duplicate_pages": sum(count for value, count in exact.items() if value and count > 1),
        "normalized_duplicate_groups": sum(bool(value) and count > 1 for value, count in normal.items()),
        "normalized_duplicate_pages": sum(count for value, count in normal.items() if value and count > 1),
        "under_50": sum(bool(value) and len(value) < 50 for value in values),
        "over_160": sum(len(value) > 160 for value in values),
        "title_equals_description": sum(str(row["title"]) == str(row["description"]) for row in rows),
        "region_missing": sum(bool(row["region"]) and str(row["region"]) not in str(row["description"]) for row in rows if not row["school"]),
        "school_missing": sum(bool(row["school"]) and str(row["school"]) not in str(row["description"]) for row in rows),
        "page_type_missing": sum(row["page_type"] != "home" and str(row["page_type"]) not in str(row["description"]) for row in rows),
        "has_좋은공부": sum("좋은공부" in value for value in values),
        "has_GoodStudy": sum("goodstudy" in value.casefold() for value in values),
        "has_전국과외": sum("전국과외" in value for value in values),
    }


def main() -> None:
    started = datetime.now().astimezone().isoformat()
    metadata_values = json.loads(META.read_text(encoding="utf-8"))
    by_slug = {str(item["slug"]): item for item in metadata_values}
    del metadata_values
    paths = [TARGET / "index.html"] + sorted(TARGET.glob("*/index.html"), key=lambda p: p.relative_to(TARGET).as_posix())
    if len(paths) != 30457:
        raise RuntimeError(f"unexpected HTML count: {len(paths)}")
    rows: list[dict[str, object]] = []
    for path in paths:
        rel = path.relative_to(TARGET).as_posix()
        if rel == "index.html":
            meta = {"node_id": "home", "page_type": "home", "slug": "", "source_sheet": "", "source_row": ""}
        else:
            meta = by_slug[path.parent.name]
        text = path.read_text(encoding="utf-8")
        rows.append({
            "path": path, "relative_path": rel, "meta": meta, "slug": str(meta.get("slug") or ""),
            "node_id": str(meta.get("node_id") or ""), "page_type": str(meta.get("page_type") or "home"),
            "school": str(meta.get("school_name") or ""), "region": primary_region(meta),
            "title": title(text), "description": meta_value(text, "name", "description"),
        })
    before = stats(rows)
    exact = Counter(str(row["description"]) for row in rows)
    normal = Counter(normalized(str(row["description"])) for row in rows)
    affected: list[dict[str, object]] = []
    for row in rows:
        description = str(row["description"])
        issues: list[str] = []
        if not description: issues.append("empty_description")
        if description and exact[description] > 1: issues.append("exact_duplicate")
        if description and normal[normalized(description)] > 1: issues.append("normalized_duplicate")
        if row["school"] and str(row["school"]) not in description: issues.append("school_core_missing")
        if not row["school"] and row["region"] and str(row["region"]) not in description: issues.append("region_core_missing")
        if row["page_type"] != "home" and str(row["page_type"]) not in description: issues.append("page_type_core_missing")
        if issues:
            row["issues"] = issues
            affected.append(row)
    log_rows: list[dict[str, str]] = []
    for row in affected:
        path = row["path"]
        source = path.read_text(encoding="utf-8")
        old = str(row["description"])
        new = make_description(str(row["title"]), row["meta"])
        updated, field_count = replace_description_fields(source, new)
        expected = 3 if meta_value(source, "name", "twitter:description") else 2
        if field_count != expected:
            raise RuntimeError(f"description field mismatch {field_count}/{expected}: {row['relative_path']}")
        if description_mask(source) != description_mask(updated):
            raise RuntimeError(f"non-description change: {row['relative_path']}")
        atomic_html(path, updated)
        row["description"] = new
        meta = row["meta"]
        log_rows.append({
            "node_id": str(meta.get("node_id") or ""), "page_type": str(row["page_type"]),
            "slug": str(row["slug"]), "old_description": old, "new_description": new,
            "issue_type": "|".join(row["issues"]), "change_reason": "description 중복 및 페이지 핵심 정보 누락 해소",
            "source_sheet": str(meta.get("source_sheet") or ""), "source_row": str(meta.get("source_row") or ""),
        })
    prior_by_slug: dict[str, dict[str, str]] = {}
    if LOG.exists():
        with LOG.open(encoding="utf-8-sig", newline="") as handle:
            prior_by_slug = {row["slug"]: row for row in csv.DictReader(handle)}
    for row in log_rows:
        prior = prior_by_slug.get(row["slug"])
        if prior:
            row["old_description"] = prior["old_description"]
            row["issue_type"] = "|".join(sorted(set(prior["issue_type"].split("|")) | set(row["issue_type"].split("|"))))
        prior_by_slug[row["slug"]] = row
    cumulative_log = list(prior_by_slug.values())
    with LOG.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "node_id", "page_type", "slug", "old_description", "new_description", "issue_type",
            "change_reason", "source_sheet", "source_row",
        ])
        writer.writeheader(); writer.writerows(cumulative_log)
    after = stats(rows)
    # Compare every HTML. Only the permitted description fields may differ.
    invariants = Counter()
    def compare(row: dict[str, object]) -> dict[str, int]:
        rel = str(row["relative_path"])
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
    with ThreadPoolExecutor(max_workers=16) as pool:
        for result in pool.map(compare, rows, chunksize=32):
            invariants.update(result)
    source_files = {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file()}
    target_files = {p.relative_to(TARGET).as_posix() for p in TARGET.rglob("*") if p.is_file()}
    invariants["slug_changed"] = len(source_files ^ target_files)
    invariants["sitemap_changed"] = int((SOURCE / "sitemap.xml").read_bytes() != (TARGET / "sitemap.xml").read_bytes())
    invariants["page_count_change"] = len(paths) - 30457
    invariants["school_connections_changed"] = invariants["internal_links_changed"]
    baseline_audit = json.loads((ROOT / "audit" / "titleclean-full-audit.json").read_text(encoding="utf-8"))
    baseline = baseline_audit["summary"]
    samples: list[str] = []
    categories = (
        ("지역 일반 과외", lambda r: not r["school"] and "수학" not in str(r["page_type"]) and "영어" not in str(r["page_type"])),
        ("지역 수학과외", lambda r: not r["school"] and "수학" in str(r["page_type"])),
        ("지역 영어과외", lambda r: not r["school"] and "영어" in str(r["page_type"])),
        ("학교 일반 과외", lambda r: bool(r["school"]) and "수학" not in str(r["page_type"]) and "영어" not in str(r["page_type"])),
        ("학교 수학과외", lambda r: bool(r["school"]) and "수학" in str(r["page_type"])),
        ("학교 영어과외", lambda r: bool(r["school"]) and "영어" in str(r["page_type"])),
    )
    for heading, predicate in categories:
        values = [row for row in affected if predicate(row)][:20]
        samples.append(f"[{heading}] ({len(values)}개)")
        for row in values:
            samples.append(f"- /{row['slug']}/")
            samples.append(f"  {row['description']}")
        samples.append("")
    SAMPLES.write_text("\n".join(samples), encoding="utf-8")
    passed = (
        len(paths) == 30457 and after["empty"] == 0
        and after["exact_duplicate_groups"] == 0 and after["normalized_duplicate_groups"] == 0
        and not any(invariants.values())
        and baseline["exact_duplicate_title_groups"] == 0
        and baseline["jsonld_missing"] == 0 and baseline["jsonld_parsing_errors"] == 0
        and baseline["broken_internal_links"] == 0 and baseline["orphan_pages"] == 0
        and baseline["home_unreachable_pages"] == 0
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "source_candidate": str(SOURCE), "target_candidate": str(TARGET),
        "started_at": started, "completed_at": datetime.now().astimezone().isoformat(),
        "counts": {"html": len(paths), "actual_modified_pages": len(affected)},
        "before": before, "after": after, "invariants": dict(invariants),
        "inherited_full_audit": {
            "title_duplicate_groups": baseline["exact_duplicate_title_groups"],
            "jsonld_missing": baseline["jsonld_missing"], "jsonld_parsing_errors": baseline["jsonld_parsing_errors"],
            "broken_internal_links": baseline["broken_internal_links"], "orphan_pages": baseline["orphan_pages"],
            "home_unreachable_pages": baseline["home_unreachable_pages"],
        },
        "artifacts": {"fix_log": str(LOG), "samples": str(SAMPLES)},
        "passed": passed,
    }
    temporary = AUDIT.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, AUDIT)
    print(json.dumps({"status": report["status"], "modified": len(affected), "before": before, "after": after, "invariants": dict(invariants)}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
