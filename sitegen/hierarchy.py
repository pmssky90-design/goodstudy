from __future__ import annotations

from collections import defaultdict
from sitegen.models import Page


def build_relations(pages: list[Page]) -> dict[str, dict[str, object]]:
    by_id = {page.node_id: page for page in pages}
    region_general: dict[tuple[str, str, str, str], Page] = {}
    variants: dict[tuple[str, str, str, str], list[Page]] = defaultdict(list)
    schools: dict[tuple[str, str, str], list[Page]] = defaultdict(list)
    topic_exact: dict[tuple[str, str, str, str], list[Page]] = defaultdict(list)
    topic_city: dict[tuple[str, str, str], list[Page]] = defaultdict(list)
    topic_province: dict[tuple[str, str], list[Page]] = defaultdict(list)
    for page in pages:
        geo = (page.province, page.city, page.locality, page.village)
        variants[geo].append(page)
        if page.page_type == "과외":
            region_general[geo] = page
        if page.school_name:
            schools[(page.province, page.city, page.locality)].append(page)
        else:
            topic_exact[(page.page_type, page.province, page.city, page.locality)].append(page)
            topic_city[(page.page_type, page.province, page.city)].append(page)
            topic_province[(page.page_type, page.province)].append(page)

    for page in pages:
        if page.school_name:
            desired = {"학교과외": "고등과외", "학교수학과외": "고등수학과외", "학교영어과외": "고등영어과외"}[page.page_type]
            candidates = topic_exact.get((desired, page.province, page.city, page.locality), [])
            fallback = 0
            if not candidates:
                candidates = topic_city.get((desired, page.province, page.city), [])
                fallback = 1
            if not candidates:
                candidates = topic_province.get((desired, page.province), [])
                fallback = 3
            if candidates:
                parent = sorted(candidates, key=lambda p: (p.locality, p.slug))[0]
                page.primary_parent_id = parent.node_id
                page.fallback_level = fallback
            else:
                page.primary_parent_id = "home"
                page.fallback_level = 4
        elif page.page_type != "과외":
            parent = region_general.get((page.province, page.city, page.locality, page.village))
            page.primary_parent_id = parent.node_id if parent else "home"
        else:
            parent_candidates = [
                p for p in pages if p.page_type == "과외" and p.node_id != page.node_id
                and p.province == page.province
                and ((page.village and p.locality == page.locality and not p.village)
                     or (page.locality and not page.village and p.city == page.city and not p.locality)
                     or (page.city and not page.locality and not p.city))
            ]
            page.primary_parent_id = sorted(parent_candidates, key=lambda p: p.geo_level)[-1].node_id if parent_candidates else "home"

    for page in pages:
        if page.primary_parent_id in by_id:
            by_id[page.primary_parent_id].children_ids.append(page.node_id)
        peers = variants.get((page.province, page.city, page.locality, page.village), [])
        page.related_nodes = sorted({p.node_id for p in peers if p.node_id != page.node_id})[:24]
        if page.school_name:
            same_school = [p for p in schools[(page.province, page.city, page.locality)]
                           if p.school_name == page.school_name and p.school_address == page.school_address and p.node_id != page.node_id]
            page.related_nodes = sorted({*page.related_nodes, *(p.node_id for p in same_school)})
    return {p.node_id: {"primary_parent_id": p.primary_parent_id, "children_ids": p.children_ids, "related_nodes": p.related_nodes} for p in pages}
