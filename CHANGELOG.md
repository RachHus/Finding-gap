# Changelog

Finding gap의 릴리스 단위 변경 이력입니다.
버전은 이 파일과 git 태그로만 관리하며, **웹페이지에는 노출하지 않습니다.**
형식은 [Keep a Changelog](https://keepachangelog.com/ko/), 버전 체계는 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [Unreleased]

### 기능
- 발견 제보 근거: URL 입력 대신 **사진 업로드**를 1순위로 지원 — 선택한 사진의 EXIF GPS로 발견 위치 자동입력(없으면 지도 클릭), 업로드 전 클라이언트 압축(최대 1600px·JPEG q0.82). URL 입력은 "사진이 없다면" 폴백으로 유지.
- 사진은 Storage 버킷 `report-photos`(본인 폴더만 업로드/삭제, 읽기는 public)에 저장. `reports.url`은 선택 컬럼으로 변경, `photo_path` 컬럼 추가(둘 중 하나는 필수).

- 발견공백 도우미(chat)에 **강·목·과·속(class/order/family/genus) 단위 질의** 지원 — "사슴벌레과에 아직 기록되지 않은 종은?" 같은 질문에 응답. 과·속의 한글 분류명은 `fg_taxon_name`(taxon_ko.js 기반)으로 라틴명 해석(강·목은 한글 매핑 없어 라틴명만). KTSN 마스터 분류 단계가 강-목-과-속-종/아종뿐이라 아과·족 등은 지원 범위 밖.
- 발견공백 도우미: **분류군 질의 커버리지 전체화 + 발견공백 순위 도구** — (1) `fg_taxon_name`을 KTSN 전체(강·목·과·속 4계층)로 확대해 한글명 해석률을 과 60→96%·속 42→69%로 높이고 강·목도 한글 질의 지원(`7_MCP/build_taxon_names.py` → `taxon_names.json.gz`), (2) 한글명 정확 일치 실패 시 `pg_trgm` 유사도로 후보(`suggestions`) 제시(딱따구리↔딱다구리 등 철자변형·'나비' 통칭 완화), (3) 신규 도구 `taxon_gap_ranking` — "곤충류에서 미발견 종 많은 과", "전남에서 한 번도 기록 안 된 과" 등 과·속 단위 발견공백 순위. (4) 분류군명 해석을 **검증된 라틴명만 쿼리에 사용**하도록 강화(사전 정확일치→실데이터 라틴 존재확인→퍼지 근사 순, 어디에도 없으면 조회 미실행·후보만 반환), 근사 해석 시 `approximate`/`matched_taxon`으로 "가장 비슷한 분류군으로 안내".

### 수정
- 발견공백 도우미(chat v9) **정확성·성능 개선** — (1) `list_species_by_taxon` 의 발견상태(state) 필터를 `LIMIT` **뒤 후처리**에서 **SQL 내 판정·필터**로 이동. 종전엔 국명순 상위 N개만 뽑은 뒤 걸러 "미발견 몇 종?"에 잘린 수를 답하고 뒤쪽 종이 누락됐다(예: 고치벌과 미발견 1,295종인데 ≤30만 보고). 이제 `count`=실제 전체 수, `species`=국명순 상위 표본, `state_totals`=발견/휴면/미발견 내역을 함께 반환. (2) 전국(지역 미지정) 집계를 종별 사전집계 MV(`fg_species_national`, ≈20k행)로 전환해 `fg_species_region`(590k) 전량 GROUP BY 제거(`taxa_summary`·`list_species_by_taxon`·`taxon_gap_ranking`). (3) 지역 한정 경로에 커버링 인덱스(`region/sido, ktsn, maxyear`) 추가 → index-only. (4) 분류군명 해석의 한글 정확·근사 조회를 단일 쿼리로 병합(왕복 3→2, 우선순위 정확>라틴>근사 보존). (5) `taxon_gap_ranking` 의 불필요한 `count(distinct)` 제거.
- `load_reference.py`: `--only <table[,table]>` 선택 적재 옵션 추가(소규모 갱신 시 590k행 재적재 생략), `fg_species_region` 재적재 시 전국 롤업 MV 자동 `REFRESH`.

### 배포 전 확인
- `5_App/supabase/reports_photo.sql`을 Supabase SQL Editor에서 적용해야 사진 업로드가 동작함(`reports.sql` 적용 후).
- `5_App/supabase/conversational_service_taxon.sql`·`conversational_service_taxon_ranks.sql`·`conversational_service_perf.sql`(MV·커버링 인덱스) 적용 + `load_reference.py` 재실행 + `supabase functions deploy chat` 해야 강·목·과·속 질의·발견공백 순위·v9 개선이 동작함.

- 브랜드 파비콘 추가(svg/ico·apple-touch-icon) — 실제 시도 경계(sido.geojson)를 저해상도 격자로 래스터화해 "한국 지도 + 발견공백(격자 결손)" 모티프로 구성(색은 기존 발견/미발견 배지 색 재사용). 생성 스크립트: `5_App/design/gen_brand_icon.py`.
- 4개 페이지(index/service/quiz/chat)에 파비콘 링크 + OG/Twitter 공유 메타 태그 추가 — 공유 이미지는 `build_profiles.py`가 만드는 `og.png`로 site 공통 통일(지역·분류군 SEO 페이지와 동일 이미지).

## [0.9.0] - 2026-07-02

최초 버전 기준선 — 현재 라이브 상태를 정리한 스냅숏.

### 기능
- 발견공백 조회: 국가생물종목록(KTSN, 서비스 대상 40,156종) − 3원 관측 union(EcoBank·국립공원·GBIF)의 실시간 여집합으로 미발견·빈발견·지역/연도별 발견 현황 계산.
- 대문 대시보드: 분류군별 발견/미발견 종수, 국가적색목록 현황 도넛.
- 종별 검색·상세: 발견 지역 표시, 한반도 생물다양성(NIBR)·시민 제보(Naturing/EcoBank) 링크.
- 지도: 시도 ⇄ 시군구 토글 choropleth + 환경변수 오버레이(연평균기온·최난월·최한월·연강수·해발고도).
- 종 페이지: 발견지점 기후·고도 지위 막대(전국 분포 대비).
- 로그인(이메일 매직링크 + Google OAuth)과 관심종 저장(Supabase, 행 수준 보안).

### 배포
- GitHub Pages(main `/docs`, OpenStreetMap 배경) 상시 게시.

[Unreleased]: https://github.com/RachHus/Finding-gap/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/RachHus/Finding-gap/releases/tag/v0.9.0
