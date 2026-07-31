from __future__ import annotations

from collections import Counter
from sitegen.models import Page


def school_match_report(pages: list[Page]) -> tuple[list[dict[str, object]], dict[str, int]]:
    school_pages = [p for p in pages if p.school_name]
    matches = [{"node_id": p.node_id, "school_name": p.school_name, "address": p.school_address,
                "fallback_level": p.fallback_level, "parent_id": p.primary_parent_id,
                "failure_reason": "일치하는 지역 페이지 없음" if p.fallback_level == 4 else ""} for p in school_pages]
    counts = Counter(p.fallback_level for p in school_pages)
    return matches, {f"fallback_{level}": counts.get(level, 0) for level in range(5)}
