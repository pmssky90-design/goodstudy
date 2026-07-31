from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "candidate_output_titleclean_recovery"
BASELINE = ROOT / "candidate_output_titlefix"
LIST_FILE = ROOT / "intermediate" / "titleclean-audit-file-list.txt"
HASH_FILE = ROOT / "intermediate" / "titleclean-audit-file-list.sha256"
BATCH_DIR = ROOT / "audit" / "titleclean_batches"
META_FILE = ROOT / "intermediate" / "normalized-pages.json"
RULE_VERSION = "titleclean-batch-v2-geoname-exception"
WORD_RE = re.compile(r"[0-9A-Za-z가-힣]+")
MATH_BAD = ("어휘", "문법", "독해", "지문", "문장 해석", "듣기", "영작", "교과서 본문")
ENGLISH_BAD = ("연산", "계산 정확도", "함수", "방정식", "도형", "수식", "수학 유형", "수학 개념", "문제 풀이 속도")
YEONSAN_PLACE_NAMES = ("연산1동", "연산2동", "연산3동", "연산4동", "연산5동", "연산6동", "연산8동", "연산동")


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def atomic_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = ["relative_path", "code", "detail"]
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def attrs(values: list[tuple[str, str | None]]) -> dict[str, str]:
    return {str(k).lower(): html.unescape(v or "") for k, v in values}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_html = self.has_head = self.has_body = False
        self.stack: list[tuple[str, dict[str, str]]] = []
        self.capture: str | None = None
        self.buffer: list[str] = []
        self.title = self.h1 = ""
        self.description = self.canonical = ""
        self.og_title = self.og_description = self.og_url = self.twitter_title = ""
        self.hrefs: list[str] = []
        self.breadcrumb_hrefs: list[str] = []
        self.jsonld: list[str] = []
        self.page_type = ""

    def handle_starttag(self, tag: str, values: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        at = attrs(values)
        self.stack.append((tag, at))
        if tag == "html":
            self.has_html = True
        elif tag == "head":
            self.has_head = True
        elif tag == "body":
            self.has_body = True
        if at.get("data-page-type") and not self.page_type:
            self.page_type = at["data-page-type"]
        if tag in ("title", "h1"):
            self.capture, self.buffer = tag, []
        elif tag == "script" and at.get("type", "").lower() == "application/ld+json":
            self.capture, self.buffer = "jsonld", []
        elif tag == "meta":
            key = at.get("name", "").lower()
            prop = at.get("property", "").lower()
            content = at.get("content", "")
            if key == "description": self.description = content
            elif prop == "og:title": self.og_title = content
            elif prop == "og:description": self.og_description = content
            elif prop == "og:url": self.og_url = content
            elif key == "twitter:title": self.twitter_title = content
        elif tag == "link" and "canonical" in at.get("rel", "").lower().split():
            self.canonical = at.get("href", "")
        elif tag == "a":
            href = at.get("href", "")
            if href:
                self.hrefs.append(href)
                if any("breadcrumb" in x.get("class", "").lower() for _, x in self.stack):
                    self.breadcrumb_hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.capture == tag:
            value = re.sub(r"\s+", " ", "".join(self.buffer)).strip()
            if tag == "title": self.title = value
            elif tag == "h1": self.h1 = value
            self.capture, self.buffer = None, []
        elif tag == "script" and self.capture == "jsonld":
            self.jsonld.append("".join(self.buffer).strip())
            self.capture, self.buffer = None, []
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.buffer.append(data)


def parse(text: str) -> PageParser:
    parser = PageParser()
    parser.feed(text)
    parser.close()
    return parser


def normalized(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def internal_path(href: str) -> str | None:
    parsed = urlsplit(html.unescape(href))
    if parsed.scheme or parsed.netloc:
        if parsed.netloc.lower().removeprefix("www.") != "goodstudy.co.kr":
            return None
    path = unquote(parsed.path)
    if not path.startswith("/") or path.startswith("//"):
        return None
    if path.endswith("/index.html"):
        return path
    return path if path.endswith("/") else path + "/"


def jsonld_info(values: list[str], canonical: str) -> tuple[int, int, int, list[str]]:
    parse_errors = mismatch = 0
    urls: list[str] = []
    for raw in values:
        try:
            value = json.loads(raw)
        except Exception:
            parse_errors += 1
            continue
        queue = [value]
        while queue:
            item = queue.pop()
            if isinstance(item, dict):
                item_type = item.get("@type")
                if item_type in ("WebPage", "WebSite") and isinstance(item.get("url"), str):
                    urls.append(item["url"])
                queue.extend(item.values())
            elif isinstance(item, list):
                queue.extend(item)
    if not parse_errors and urls and canonical not in urls:
        mismatch = 1
    return len(values), parse_errors, mismatch, urls


def page_issues(parser: PageParser, slug: str, page_type: str, is_home: bool) -> list[str]:
    issues: list[str] = []
    title = parser.title
    if not title: issues.append("empty_title")
    if len(title) > 100: issues.append("title_over_100")
    if not is_home and "좋은공부" in title: issues.append("title_has_좋은공부")
    if not is_home and "goodstudy" in title.casefold(): issues.append("title_has_GoodStudy")
    if not is_home and "전국과외" in title: issues.append("title_has_전국과외")
    if slug and normalized(title) == normalized(slug): issues.append("title_equals_slug")
    words = Counter(x.casefold() for x in WORD_RE.findall(title))
    if any(count >= 3 for count in words.values()): issues.append("word_repeated_3_or_more")
    if not is_home and page_type and page_type != "unknown" and page_type not in title:
        issues.append("page_type_keyword_missing")
    if "수학" in page_type and any(term in title for term in MATH_BAD):
        issues.append("math_title_english_expression")
    english_check_title = title
    for place_name in YEONSAN_PLACE_NAMES:
        if place_name in slug:
            english_check_title = english_check_title.replace(place_name, "")
    if "영어" in page_type and any(term in english_check_title for term in ENGLISH_BAD):
        issues.append("english_title_math_expression")
    if page_type == "과외" and ("수학" in title or "영어" in title):
        issues.append("general_title_subject_bias")
    return issues


def load_metadata() -> dict[str, dict[str, object]]:
    values = json.loads(META_FILE.read_text(encoding="utf-8"))
    return {
        str(item["slug"]): {
            "page_type": str(item.get("page_type") or "unknown"),
            "school_name": str(item.get("school_name") or ""),
            "primary_parent_id": str(item.get("primary_parent_id") or ""),
        }
        for item in values
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-index", type=int, required=True)
    ap.add_argument("--batch-size", type=int, default=2000)
    args = ap.parse_args()
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    paths = LIST_FILE.read_text(encoding="utf-8").splitlines()
    list_hash = HASH_FILE.read_text(encoding="ascii").strip()
    start = (args.batch_index - 1) * args.batch_size
    selected = paths[start:start + args.batch_size]
    if not selected:
        raise SystemExit("empty batch")
    metadata = load_metadata()
    counts: Counter[str] = Counter()
    records: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    started = datetime.now().astimezone().isoformat()
    for rel in selected:
        target_path, source_path = TARGET / rel, BASELINE / rel
        slug = "" if rel == "index.html" else Path(rel).parent.name
        is_home = rel == "index.html"
        meta = metadata.get(slug, {})
        page_type = "home" if is_home else str(meta.get("page_type") or "unknown")
        school_page = bool(meta.get("school_name"))
        record: dict[str, object] = {"relative_path": rel, "slug": slug, "page_type": page_type}
        try:
            raw = target_path.read_bytes()
            counts["processed"] += 1
            if not raw: counts["zero_byte"] += 1
            text = raw.decode("utf-8")
            target = parse(text)
        except Exception as exc:
            counts["read_errors"] += 1
            errors.append({"relative_path": rel, "code": "read_error", "detail": repr(exc)})
            records.append(record)
            continue
        try:
            source = parse(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            counts["baseline_read_errors"] += 1
            errors.append({"relative_path": rel, "code": "baseline_read_error", "detail": repr(exc)})
            records.append(record)
            continue
        for key, present in (("missing_html_tag", target.has_html), ("missing_head", target.has_head), ("missing_body", target.has_body)):
            if not present: counts[key] += 1
        issues = page_issues(target, slug, page_type, is_home)
        counts.update(issues)
        if not target.description: counts["empty_description"] += 1
        for key, value in (
            ("canonical_missing", target.canonical), ("og_title_missing", target.og_title),
            ("og_description_missing", target.og_description), ("og_url_missing", target.og_url),
            ("twitter_title_missing", target.twitter_title),
        ):
            if not value: counts[key] += 1
        script_count, json_errors, json_url_mismatch, json_urls = jsonld_info(target.jsonld, target.canonical)
        if not script_count: counts["jsonld_missing"] += 1
        counts["jsonld_parsing_errors"] += json_errors
        counts["jsonld_url_mismatch"] += json_url_mismatch
        if "www." in target.canonical: counts["canonical_www"] += 1
        if target.canonical.startswith("http://"): counts["canonical_http"] += 1
        if "index.html" in target.canonical: counts["canonical_index_html"] += 1
        if "//" in urlsplit(target.canonical).path: counts["canonical_double_slash"] += 1
        if target.og_url != target.canonical: counts["og_url_mismatch"] += 1
        internal = [x for x in (internal_path(href) for href in target.hrefs) if x is not None]
        source_internal = [x for x in (internal_path(href) for href in source.hrefs) if x is not None]
        invariants = {
            "slug_changed": 0,
            "canonical_changed": int(target.canonical != source.canonical),
            "description_changed": int(target.description != source.description),
            "og_description_changed": int(target.og_description != source.og_description),
            "jsonld_url_changed": int(jsonld_info(source.jsonld, source.canonical)[3] != json_urls),
            "internal_links_changed": int(internal != source_internal),
            "page_type_changed": int(bool(source.page_type) and source.page_type != target.page_type),
            "school_connections_changed": int(school_page and internal != source_internal),
            "parent_relations_changed": int(target.breadcrumb_hrefs != source.breadcrumb_hrefs),
        }
        counts.update(invariants)
        record.update({
            "title": target.title, "description": target.description, "canonical": target.canonical,
            "internal_links": internal, "breadcrumb_links": [x for x in (internal_path(h) for h in target.breadcrumb_hrefs) if x],
            "school_page": school_page, "issues": issues, "jsonld_missing": int(not script_count),
            "jsonld_errors": json_errors, "jsonld_url_mismatch": json_url_mismatch,
            "invariants": invariants,
            "target_sha256": hashlib.sha256(raw).hexdigest(),
            "baseline_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        })
        records.append(record)
        for issue in issues:
            errors.append({"relative_path": rel, "code": issue, "detail": target.title})
        for key, value in invariants.items():
            if value:
                errors.append({"relative_path": rel, "code": key, "detail": ""})
    result = {
        "status": "complete", "rule_version": RULE_VERSION, "batch_index": args.batch_index,
        "batch_size": args.batch_size, "expected_count": len(selected), "processed_count": len(records),
        "file_list_hash": list_hash, "first_relative_path": selected[0], "last_relative_path": selected[-1],
        "started_at": started, "completed_at": datetime.now().astimezone().isoformat(),
        "counts": dict(counts), "records": records, "error_count": len(errors),
    }
    name = f"batch-{args.batch_index:04d}"
    atomic_json(BATCH_DIR / f"{name}.json", result)
    atomic_csv(BATCH_DIR / f"{name}-errors.csv", errors)
    print(json.dumps({"batch": args.batch_index, "processed": len(records), "errors": len(errors)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
