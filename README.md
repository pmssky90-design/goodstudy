# 좋은공부 정적 사이트 생성기

입력 파일은 `data/주요지역과 학교 분몬.xlsx`에 둡니다. 생성기는 원본 엑셀과 운영용
`output`을 수정하지 않고 `candidate_output`에만 후보 사이트를 만듭니다.

## 설치와 실행

```powershell
python -m pip install -r requirements.txt
python generator.py
```

검사만 포함한 재빌드는 `scripts\audit_candidate.bat`, 별도 미리보기는
`scripts\preview_candidate.bat`으로 실행할 수 있습니다. 운영 승격, Git 작업, 배포는
자동으로 수행하지 않습니다.

도메인과 사이트명은 `config.py`에서 한 번만 관리합니다. canonical, sitemap,
robots와 구조화 데이터는 이 설정을 참조합니다. 페이지의 `slug`와 `title`은 서로
독립된 필드이며 한쪽으로 다른 쪽을 생성하거나 덮어쓰지 않습니다.

운영 `output`을 정상 생성한 뒤 검색 썸네일 메타와 공개 이미지 자산을 결정적으로
적용하려면 다음 post-build 명령을 실행합니다. 기본 실행은 운영본을 건드리지 않고
`candidate_output_search_thumbnail` 후보만 생성합니다.

```powershell
python build_search_thumbnail_candidate.py --apply-output
python build_mobile_contact_candidate.py --apply-output
```

학교는 주소의 시도·시군구·읍면동을 기준으로 연결합니다. 정확한 읍면동(0), 시군구(1),
광역시·대도시(2), 시도(3), 연결 실패(4) 순으로 fallback 수준을 기록하며, 이름이 같은
다른 도시의 동에는 연결하지 않습니다.

## 지역별 과외 승인 디자인 적용

`scripts/build_general_samples.py --all`은 `page_type == '과외'`인 지역 페이지만
`candidate_output_general`에 생성합니다. 기존 운영 HTML의 본문·canonical·검색 이미지와
관련 링크를 보존하고, 승인 디자인 및 학습 선택/준비 콘텐츠를 추가합니다.
중등영어·고등영어·수학 등 다른 유형은 변경하지 않습니다.
원본의 과외 분류에 잘못 포함된 과목·학년 키워드는 추가로 제외합니다.
현재 대상은 1,634개이며, 운영 반영 후 `python scripts/audit_general_rollout.py`로
대상 범위, 제목 중복, canonical, 이미지와 연락 링크를 검사할 수 있습니다.

검토 후 `python scripts/build_general_samples.py --all --apply-output`으로 적용합니다.
전체 후보 검증 성공 후에만 운영 파일을 복사하며, 적용 전 원본은
`backup_output_general`에 보관합니다. 반복 실행 시 이 원본을 사용합니다.
기본 실행(옵션 없음)은 세 개의 noindex 미리보기만 생성합니다.
추가 콘텐츠는 공통 안내로, 지역별 실제 운영 사례나 고유 정보를 주장하지 않습니다.

## 지역별 영어과외 승인 디자인 적용

`python scripts/build_english_samples.py --all`은 순수 지역별 영어과외 1,634개만
`candidate_output_english`에 생성하고 검사합니다. 잘못 분류된 과목명 포함 지역과
초등·중등·고등·학교별 유형은 제외합니다. `--apply-output`을 함께 주면 전체 검사 후
원본을 `backup_output_english`에 보관하고 운영 파일에 반영합니다.
반복 실행은 백업 원문을 사용합니다. 옵션 없는 실행은 세 미리보기만 생성합니다.
기존 본문 설명·목록·canonical·검색 이미지를 보존하며, 반복 도입과 요약 인용문은
제외하고 영어 예문·적용 기록·영어 전용 질문을 추가합니다.

## 지역별 수학과외 승인 디자인 적용

`python scripts/build_math_samples.py --all --apply-output`은 순수 지역별 수학과외
1,634개를 검사한 뒤 기존 주소에 반영합니다. 초등·중등·고등·학교별 수학과외는
별도로 유지합니다. 후보는 `candidate_output_math`, 최초 원본은 `backup_output_math`,
검사 기록은 `audit/math-rollout.json`에 저장됩니다. 옵션 없는 실행은 미리보기 3개입니다.
수학 CSS는 각 HTML에 포함되어 다른 유형의 공통 CSS 파일을 변경하지 않습니다.
여섯 학년별 유형을 모두 완성한 후 전체 탐색 구조·유형 간 링크·모바일·검색 메타·
색인 설정을 통합 점검할 예정이며, 그 전에도 매 배포의 기본 검증은 수행합니다.

## 지역별 초등수학과외 승인 디자인 적용

`python scripts/build_elementary_math_samples.py --all --apply-output`은 순수 지역별
초등수학과외 1,634개를 검사한 후 기존 주소에 반영합니다. 후보와 최초 원문은 각각
`candidate_output_elementary_math`, `backup_output_elementary_math`에 보관합니다.
검사 기록은 `audit/elementary-math-rollout.json`입니다. 옵션 없는 실행은 미리보기입니다.
교과 전반의 안내 아래 관찰·활동·부모 대화·가정 확인과 원문 학습 설명을 배치합니다.
활동은 설명용 예시이며 지역의 실제 학생 사례를 주장하지 않습니다.

## 지역별 초등영어과외 승인 디자인 적용

`python scripts/build_elementary_english_samples.py --all --apply-output`은 지역별
초등영어과외 1,634개에 교재 선택·영어 자료·학교 학습 연결 구성을 반영합니다.
과목명이 섞인 지역 분류와 학교별 페이지는 제외합니다. 원문을 바탕으로 소리·읽기·
듣고 말하기 중 대표 구성을 선택하며 실제 지역 사례를 새로 주장하지 않습니다.
전체 후보 검증 후 적용하고 최초 원문은 `backup_output_elementary_english`, 후보는
`candidate_output_elementary_english`, 기록은 `audit/elementary-english-rollout.json`에
저장합니다. 옵션 없는 실행은 세 개의 noindex 미리보기입니다.

추가 승인된 혼합 분류 572개는 `--remaining --apply-output`으로 별도 반영합니다.
이 옵션은 기존 1,634개를 변경하지 않으며 기존 주소와 분류명을 유지합니다.
기록은 `audit/elementary-english-remaining-rollout.json`에 저장합니다.
초등영어과외 분류 전체는 합계 2,206개입니다. 혼합 지역명 데이터의 정규화와
중복 주소 통합은 이번 콘텐츠 적용과 별도 과제입니다.
