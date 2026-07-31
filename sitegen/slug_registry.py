from __future__ import annotations

from collections import defaultdict
from sitegen.models import Page


def resolve_slugs(pages: list[Page]) -> tuple[dict[str, str], dict[str, int], list[dict[str, str]]]:
    groups: dict[str, list[Page]] = defaultdict(list)
    for page in pages:
        groups[page.slug].append(page)
    initial = sum(len(group) - 1 for group in groups.values() if len(group) > 1)
    redirects: list[dict[str, str]] = []
    for slug, group in sorted(groups.items()):
        if len(group) < 2:
            continue
        # 같은 행정구역의 동일 페이지는 우선순위로 하나만 남기는 대신, 실제 데이터는 도시명을 붙여 모두 보존한다.
        for page in sorted(group, key=lambda p: (p.province, p.city, p.locality, p.source_sheet, p.source_row)):
            prefix = page.city or page.province
            candidate = f"{prefix}{slug}"
            if sum(p.slug == candidate for p in pages) or sum(p.slug == candidate for p in group):
                candidate = f"{page.province}{prefix}{slug}"
            page.slug = candidate
            redirects.append({"from": slug, "to": candidate, "reason": "duplicate-source-slug"})
    # 서로 다른 원본 중복 묶음이 같은 접두어 결과로 수렴할 수 있으므로 전역 2차 고유화한다.
    used: set[str] = set()
    priority = {"과외": 0, "학교과외": 1, "학교수학과외": 1, "학교영어과외": 1}
    for page in sorted(pages, key=lambda p: (priority.get(p.page_type, 2), p.slug, p.node_id)):
        candidate = page.slug
        if candidate in used:
            readable = f"{candidate}{page.page_type}"
            candidate = readable if readable not in used else f"{readable}{page.node_id[-6:]}"
            redirects.append({"from": page.slug, "to": candidate, "reason": "global-collision"})
            page.slug = candidate
        used.add(page.slug)
    registry = {page.slug: page.node_id for page in pages}
    unresolved = len(pages) - len(registry)
    return registry, {"initial": initial, "resolved": initial - unresolved, "unresolved": unresolved}, redirects
