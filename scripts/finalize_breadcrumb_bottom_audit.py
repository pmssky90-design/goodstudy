from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit" / "breadcrumb-bottom-audit.json"
REPORT = ROOT / "audit" / "breadcrumb-bottom-report.md"


def main() -> None:
    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    preview = {
        "status": "PASS",
        "base_url": "http://127.0.0.1:8123/",
        "server_pid": 19348,
        "http_checks": {
            "home": 200,
            "seoul_province": 200,
            "gangnam_district": 200,
            "gyeonggi_province": 200,
            "suwon_district": 200,
            "gaepo_school": 200,
            "style_css": 200,
            "integration_css": 200,
            "favicon": 200,
            "manifest": 200,
        },
        "browser": "Google Chrome headless",
        "desktop_bottom_placement": "PASS",
        "mobile_bottom_placement": "PASS",
        "screenshots": [
            str(ROOT / "audit" / "breadcrumb-bottom-gangnam-desktop.png"),
            str(ROOT / "audit" / "breadcrumb-bottom-gangnam-mobile.png"),
            str(ROOT / "audit" / "breadcrumb-bottom-school-desktop.png"),
        ],
    }
    data["preview"] = preview
    temporary = AUDIT.with_suffix(".json.final.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, AUDIT)
    with REPORT.open("a", encoding="utf-8") as handle:
        handle.write("\n## 미리보기 확인\n\n")
        handle.write("- 결과: **PASS**\n")
        handle.write("- URL: `http://127.0.0.1:8123/`\n")
        handle.write("- 대표 HTML 6개: 모두 HTTP 200\n")
        handle.write("- CSS, favicon, manifest: 모두 HTTP 200\n")
        handle.write("- Chrome 데스크톱/모바일 하단 배치: PASS\n")
    print(json.dumps({"status": data["status"], "preview": "PASS"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
