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
