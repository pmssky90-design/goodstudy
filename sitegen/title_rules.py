from __future__ import annotations

import re
from html import unescape


TITLE_SUFFIXES = {
    "중등수학과외": " 중학생 내신 개념과 서술형 풀이를 함께 준비하는 맞춤 학습",
    "고등수학과외": " 고등학생 내신 개념과 문제 해결력을 함께 준비하는 맞춤 학습",
    "초등영어과외": " 초등학생 기초 어휘와 문장 이해를 함께 준비하는 맞춤 학습",
}


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def fix_title(title: str, slug: str, page_type: str) -> tuple[str, bool]:
    title = normalize_text(title)
    if title and title != slug:
        return title, False
    suffix = TITLE_SUFFIXES.get(page_type, " 학생의 현재 수준과 학습 목표를 함께 살피는 맞춤 과외")
    return f"{slug}{suffix}", True


def link_label(name: str, page_type: str, school: bool = False) -> str:
    clean = normalize_text(name)
    if school and page_type == "학교과외":
        return f"{clean} 과외"
    suffix = page_type.replace("학교", "")
    return f"{clean} {suffix}".strip()


def description_from_html(body_html: str, label: str) -> str:
    text = normalize_text(unescape(re.sub(r"<[^>]+>", " ", body_html)))
    summary = f"{label} 정보를 바탕으로 학년과 과목별 학습 방향, 내신 준비와 복습 방법을 차분히 살펴봅니다. "
    summary += text[:80]
    return summary[:150].rstrip(" ,.") + "."
