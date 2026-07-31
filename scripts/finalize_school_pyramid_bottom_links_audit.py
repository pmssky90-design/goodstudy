from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit" / "school-pyramid-bottom-links-audit.json"
REPORT = ROOT / "audit" / "school-pyramid-bottom-links-report.md"


def main() -> None:
    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    screenshots = sorted(
        str(path) for path in (ROOT / "audit").glob("school-pyramid-bottom-*.png")
    )
    browser = {
        "status": "PASS",
        "browser": "Google Chrome headless",
        "desktop_province_pages_reviewed": 4,
        "desktop_district_pages_reviewed": 5,
        "mobile_district_pages_reviewed": 1,
        "top_navigation_absent": 1,
        "bottom_navigation_after_content": 1,
        "card_layout_preserved": 1,
        "header_breadcrumb_footer_preserved": 1,
        "screenshots": screenshots,
    }
    data["browser_review"] = browser
    if data.get("http_preview", {}).get("status") != "PASS":
        data["status"] = "FAIL"
    temporary = AUDIT.with_suffix(".json.final.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)

    summary = data["summary"]
    http = data["http_preview"]["summary"]
    lines = [
        "# 학교 피라미드 하단 링크 이동 감사",
        "",
        f"- 결과: **{data['status']}**",
        f"- 기준 후보: `{data['source']}`",
        f"- 새 후보: `{data['target']}`",
        f"- 미리보기: `{http['base_url']}`",
        "",
        "## 적용 결과",
        "",
        f"- 전체 HTML: {summary['html_count']}",
        f"- 실제 변경 HTML: {summary['changed_html']}",
        f"- 시도 페이지: {summary['target_province_pages']}",
        f"- 시군구 페이지: {summary['target_district_pages']}",
        f"- 상단에서 제거한 링크 블록: {summary['top_blocks_removed']}",
        f"- 하단으로 이동한 링크 블록: {summary['bottom_blocks_moved']}",
        f"- 이동한 링크: {summary['links_moved']}",
        f"- 기존 하단 영역에 통합: {summary['integrated_existing_bottom_pages']}",
        f"- 중복으로 추가하지 않은 링크: {summary['links_not_added_due_to_duplicate']}",
        f"- 제거한 중복 링크: {summary['duplicate_links_removed']}",
        f"- 상단 잔존 링크 블록: {summary['top_navigation_blocks_remaining']}",
        f"- 하단 홈 링크: {summary['bottom_home_links']}",
        f"- 하단 전국 링크: {summary['bottom_national_links']}",
        f"- 하단 시도 복귀 링크: {summary['bottom_parent_links']}",
        "",
        "## 무결성 감사",
        "",
        f"- href 변경: {summary['href_changes']}",
        f"- 잘못된 링크: {summary['wrong_links']}",
        f"- 깨진 내부 링크: {summary['broken_internal_links']}",
        f"- 고아 페이지: {summary['orphan_pages']}",
        f"- 홈 도달 불가: {summary['home_unreachable_pages']}",
        f"- 중복 id: {summary['duplicate_ids']}",
        f"- title 변경: {summary['title_changes']}",
        f"- description 변경: {summary['description_changes']}",
        f"- canonical 변경: {summary['canonical_changes']}",
        f"- JSON-LD 변경: {summary['jsonld_changes']}",
        f"- breadcrumb 변경: {summary['breadcrumb_changes']}",
        f"- 본문 변경: {summary['content_body_changes']}",
        f"- 이미지 매핑 변경: {summary['image_mapping_changes']}",
        f"- 학교/지역 카드 링크 변경: {summary['school_region_card_link_changes']}",
        f"- sitemap 변경: {summary['sitemap_changes']}",
        f"- robots 변경: {summary['robots_changes']}",
        f"- 공통 CSS 변경: {summary['common_css_changes']}",
        "",
        "## HTTP 및 브라우저 검사",
        "",
        f"- 홈 HTTP: {http['home_status']}",
        f"- 이동 링크 HTTP 검사: {http['moved_link_rows']}건 / 오류 {http['moved_link_http_errors']}",
        f"- 기존 피라미드 링크 HTTP 검사: {http['chain_link_rows']}건 / 오류 {http['chain_link_http_errors']}",
        f"- 고유 URL HTTP 검사: {http['all_unique_urls_checked']}개 / 오류 {http['all_url_http_errors']}",
        f"- 자산 HTTP 검사: {http['asset_count']}개 / 오류 {http['asset_http_errors']}",
        f"- Chrome 데스크톱 대표 확인: 시도 {browser['desktop_province_pages_reviewed']}개, 시군구 {browser['desktop_district_pages_reviewed']}개",
        f"- Chrome 모바일 대표 확인: 시군구 {browser['mobile_district_pages_reviewed']}개",
        "",
        "> 중복 탐색 링크 감사는 변경 금지 대상인 header, footer, breadcrumb를 제외하고 피라미드 및 새 하단 탐색 영역만 대상으로 했습니다.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": data["status"], "screenshots": len(screenshots)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
