from __future__ import annotations

import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, unquote

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import ASSET_DIR, CANDIDATE_OUTPUT_DIR, SITE_NAME, SITE_NAME_EN, SITE_URL, TEMPLATE_DIR
from sitegen.models import Page
from sitegen.title_rules import description_from_html


def public_url(slug: str = "") -> str:
    return SITE_URL.rstrip("/") + (f"/{quote(slug, safe='')}/" if slug else "/")


def render_site(pages: list[Page]) -> None:
    CANDIDATE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    environment = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(("html", "xml")))
    by_id = {p.node_id: p for p in pages}
    by_original: dict[str, list[Page]] = {}
    final_slugs = {item.slug for item in pages}
    for item in pages:
        by_original.setdefault(item.original_slug, []).append(item)
    for page in pages:
        page.canonical_url = public_url(page.slug)
    roots = sorted([p for p in pages if p.primary_parent_id == "home"], key=lambda p: (p.province, p.city, p.slug))
    home_html = environment.get_template("home.html").render(
        site_name=SITE_NAME, site_name_en=SITE_NAME_EN, site_url=SITE_URL,
        title=f"{SITE_NAME} 지역과 학교별 맞춤 과외 학습 정보",
        description="지역과 학교, 학년과 과목에 따라 필요한 과외 학습 정보를 단계별로 탐색할 수 있습니다.",
        pages=roots, canonical=public_url(), website_json=json.dumps({
            "@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME,
            "alternateName": SITE_NAME_EN, "url": public_url(),
        }, ensure_ascii=False),
    )
    (CANDIDATE_OUTPUT_DIR / "index.html").write_text(home_html, encoding="utf-8")
    def render_page(page: Page) -> None:
        parent = by_id.get(page.primary_parent_id)
        related = [by_id[node_id] for node_id in page.related_nodes if node_id in by_id]
        children = [by_id[node_id] for node_id in page.children_ids if node_id in by_id]
        template = "school.html" if page.school_name else ("subject.html" if page.page_type != "과외" else "region.html")
        def remap(match: re.Match[str]) -> str:
            original = unquote(match.group(1))
            if original in final_slugs:
                return match.group(0)
            choices = by_original.get(original, [])
            local = [item for item in choices if item.province == page.province and item.city == page.city
                     and (not page.locality or item.locality == page.locality)]
            selected = (local or choices)
            return f'href="/{selected[0].slug}/"' if selected else 'href="/"'
        body_html = re.sub(r'href="/([^"/]+)/"', remap, page.body_html)
        html = environment.get_template(template).render(
            site_name=SITE_NAME, site_name_en=SITE_NAME_EN, site_url=SITE_URL, page=page,
            title=page.title, description=description_from_html(page.body_html, page.link_label),
            canonical=page.canonical_url, parent=parent, related=related, children=children,
            body_html=body_html,
        )
        target = CANDIDATE_OUTPUT_DIR / page.slug
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.html").write_text(html, encoding="utf-8")
    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(render_page, pages, chunksize=32))
    shutil.copytree(ASSET_DIR, CANDIDATE_OUTPUT_DIR / "assets", dirs_exist_ok=True)
    manifest = ASSET_DIR / "favicon" / "site.webmanifest"
    shutil.copy2(manifest, CANDIDATE_OUTPUT_DIR / "site.webmanifest")
    (CANDIDATE_OUTPUT_DIR / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    urls = [public_url()] + [p.canonical_url for p in sorted(pages, key=lambda p: p.slug)]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "".join(f"  <url><loc>{url}</loc></url>\n" for url in urls) + "</urlset>\n"
    (CANDIDATE_OUTPUT_DIR / "sitemap.xml").write_text(xml, encoding="utf-8")
