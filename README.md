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

학교는 주소의 시도·시군구·읍면동을 기준으로 연결합니다. 정확한 읍면동(0), 시군구(1),
광역시·대도시(2), 시도(3), 연결 실패(4) 순으로 fallback 수준을 기록하며, 이름이 같은
다른 도시의 동에는 연결하지 않습니다.
