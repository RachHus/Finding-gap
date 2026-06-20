# Finding gap

국립생물자원관(NIBR) **국가생물종목록(KTSN)** 을 기준으로, 국내 조사자료에서
**미발견 종 · 빈발견 종 · 광역시도/연도별 발견 현황**을 조회하고
시민 제보로 발견공백을 메우도록 유도하는 웹 서비스.

> **발견공백(gap) = 국가생물종목록(서비스 대상) − 관측된 종** — 실시간 여집합으로 계산.

순수 **정적(클라이언트) 사이트**라 백엔드가 없습니다. 브라우저가 정적 데이터 파일을 직접 읽어
집계·렌더합니다. 배경지도는 OpenStreetMap(키 불필요)을 기본으로 씁니다.

## 라이브 데모

- https://rachhus.github.io/Finding-gap/  *(레포 public 전환 + GitHub Pages 활성화 후 접속 가능)*

## 기능

- **대문 ([`5_App/index.html`](5_App/index.html))** — 분류군 타일 + 지역별 발견종수·국가적색목록 현황 대시보드.
- **서비스 ([`5_App/service.html`](5_App/service.html))**
  - *분류군별 조회* — 시도 choropleth 지도 + 발견/미발견 필터 + 정렬 테이블 + CSV 내려받기.
  - *종별 검색* — 전체 종 인덱스를 클라이언트에서 검색 → 그 종이 발견된 시도 강조 + 외부 제보 링크(한반도 생물다양성·Naturing·EcoBank).
- 9개 관리분류군(포유류·조류·파충류·양서류·어류·무척추(곤충제외)·곤충·관속식물·선태) 약 4만 종.

## 빠른 시작 (로컬 실행)

```bash
git clone https://github.com/RachHus/Finding-gap.git
cd Finding-gap
python -m http.server 5173 --directory 5_App
# 브라우저: http://localhost:5173/index.html   (서비스: /service.html)
```

`config.js`(vworld 키)가 없어도 **OSM 배경으로 자동 폴백**되어 추가 설정 없이 그대로 작동합니다.
국내 상세지도(vworld)를 쓰려면 `5_App/.env` 에 `VWORLD_KEY` 를 넣으세요(자세한 건 [`5_App/.env.example`](5_App/.env.example)).

## 폴더 구조

```
finding-gap/
├─ 1_Data/         # 데이터(원천/정제/공간) — 대용량이라 git 제외(.gitkeep만 추적)
├─ 3_ETL/          # 수집·정합·집계 파이프라인 (python·R) + DATA_PIPELINE.md
├─ 4_References/   # 참고자료(코드 입력 CSV만 공유 · 저작권 원문서는 제외)
├─ 5_App/          # 정적 웹앱 (index/service.html · demo/data · design 토큰)
├─ 6_Deliverables/ # 배포본(dist) · 계획서 · 다이어그램 · DEPLOY.md
└─ docs/           # GitHub Pages 서빙용 정적 빌드(OSM, build_dist.py 산출)
```

> 폴더명은 코드·CLI·git 호환을 위해 공백·점(`.`) 없이 `1_Data` 형식을 씁니다.

## 데이터 파이프라인

원천 → 정제 → 서비스 정적자산. 3계층 스키마·변환 상세는 [`3_ETL/DATA_PIPELINE.md`](3_ETL/DATA_PIPELINE.md).

```
NIBR KTSN · EcoBank · 국립공원 · GBIF · 국가적색목록/멸종위기 등급
   │  3_ETL  (학명 매칭: KTSN 마스터 + 변종/품종 별칭 + 수기 보정(override) + 이명;
   │          학명·국명이 다른 정명을 가리키면 폐기 / 시도 spatial join / 연도·obs_count 집계)
   ▼
1_Data/processed  (ktsn_master.csv · observation_*.csv · *_aliases/synonyms.csv ...)
   │  build_demo_data.py
   ▼
5_App/demo/data/*.js  (분류군별 관측 · 종 인덱스 · 요약)  →  브라우저가 직접 집계·렌더
```

- 매칭 기준키 **KTSN**. 발견 = 최근 10년 내 기록 / 미발견 = 관측 0 / 휴면 = 기록은 있으나 최신연도 ≤ (당해 − 10).
- 적색목록 = 마스터 `national_redlist_category`, 멸종위기 = `endangered_grade`.

## 데이터 출처

- **국가생물종목록(KTSN) · 국가생물적색자료집** — 국립생물자원관(NIBR)
- **조사 관측** — EcoBank(국립생태원) · 국립공원공단 생물자원 현황
- **분류 보강** — GBIF
- **배경지도** — © OpenStreetMap 기여자 / (선택) © VWorld

## 배포

- **GitHub Pages** — `main` 브랜치 `/docs` 폴더. 데이터 갱신 시:
  ```bash
  python 3_ETL/python/build_demo_data.py <날짜>      # 데이터가 바뀌었을 때만
  python 5_App/build_dist.py --osm-only --out docs   # docs/ 재빌드
  ```
  커밋·push 하면 Pages가 자동 갱신됩니다.
- **Cloudflare Pages · Netlify 등** — `python 5_App/build_dist.py --osm-only` → `6_Deliverables/dist` 업로드. 상세 [`6_Deliverables/DEPLOY.md`](6_Deliverables/DEPLOY.md).

## 공유 · 보안

API 키(`.env`) · 클라이언트 키(`config.js`) · 원천/정제 데이터 · 저작권 참고자료는 git에서 제외됩니다.
공유/비공유 정책은 [`SHARING.md`](SHARING.md) 참조.

## 갱신 주기

6개월 — 원천 ETL 재실행 → `build_demo_data.py` → `build_dist.py` → 재배포.
