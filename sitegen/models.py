from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Page:
    node_id: str
    node_type: str
    geo_level: str
    province: str
    city: str
    district: str
    locality: str
    village: str
    page_type: str
    slug: str
    title: str
    link_label: str
    breadcrumb_label: str
    body_html: str
    primary_parent_id: str = "home"
    secondary_parent_ids: list[str] = field(default_factory=list)
    children_ids: list[str] = field(default_factory=list)
    related_nodes: list[str] = field(default_factory=list)
    source_sheet: str = ""
    source_row: int = 0
    canonical_url: str = ""
    school_name: str = ""
    school_address: str = ""
    fallback_level: int | None = None
    original_slug: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceReport:
    sheets: list[dict[str, Any]] = field(default_factory=list)
    total_rows: int = 0
