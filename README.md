# Finding gap (발견공백)

국립생물자원관(NIBR) **국가생물종목록(KTSN)** 을 기준으로, 국내 조사자료에서
**아직 발견되지 않은 종**을 분류군·지역·시기로 조회하고, 시민 제보로 그 공백을 메우도록 잇는 웹 서비스.

> **발견공백 = 국가생물종목록(서비스 대상 종) − 그 지역에서 관측된 종**
> 미리 계산해 두지 않고 **브라우저가 조회할 때마다 여집합으로 계산**한다.
> 발견 = 최근 10년 내 기록 · 휴면 = 기록은 있으나 최신연도가 10년보다 오래됨 · 미발견 = 기록 없음.

- **라이브**: https://rachhus.github.io/Finding-gap/
- 대상: 9개 관리분류군(포유류·조류·파충류·양서류·어류·무척추(곤충 제외)·곤충·관속식물·선태) 약 4만 종
- 대상 지역: 시도 17 + 시군구 252

---

## 무엇으로 만들어졌나 (3계층)

이 저장소에는 성격이 다른 세 가지가 함께 들어 있다. 어디를 고치려는지에 따라 봐야 할 곳이 다르다.

| 계층 | 하는 일 | 서버 | 코드 위치 |
|---|---|---|---|
| **① 정적 조회** | 종 목록·관측 집계·지도·서식지 후보 — **조회는 전부 브라우저 안에서** 끝난다. 정적 `.js` 자산을 받아 클라이언트가 집계·채점·렌더한다. | 없음 (GitHub Pages) | `5_App/` → 빌드 산출 `docs/` |
| **② 계정·제보·도우미** | 로그인, 발견 제보(사진·EXIF), 관심종, 대화형 도우미. 조회 경로가 아니라 **참여 경로**만 담당한다. | Supabase (Postgres + RLS + Auth + Edge Function) | `5_App/fg_supabase.js` · `5_App/supabase/` |
| **③ 공개 MCP** | 같은 집계를 LLM·에이전트가 쓸 수 있게 여는 읽기 전용 도구 15개. 로컬 설치형이라 서버가 없다. | 없음 (stdio) | `7_MCP/` |

**①이 멈추면 서비스가 멈추고, ②가 멈춰도 조회는 그대로 된다.** 조회 경로에 백엔드를 두지 않은 것은
의도한 설계다 — 자료 갱신이 6개월 주기라 실시간 질의가 필요 없고, 무료 호스팅으로 계속 살아 있을 수 있다.

원시 좌표점(약 530만 행)은 **어느 계층으로도 나가지 않는다.** 배포·MCP로 공개되는 것은 집계뿐이다.

---

## 기능

**지도 서비스** (`5_App/index.html`)
- *분류군별 조회* — 시도·시군구 단계 지도 + 발견/미발견 필터 + 연도·10년 단위 보기 + 정렬 표 + CSV 내려받기
- *종별 검색* — 약 4만 종 색인을 브라우저에서 검색(국명·학명·**초성**) → 그 종이 발견된 지역 강조 + 제보 링크
- *지역 검색* — 시도 17 + 시군구 252, 총 269곳을 이름·초성으로 찾아 그 지역으로 확대
- *서식지 후보* — 종별 MaxEnt 모형 계수로 브라우저가 전국 1km 격자 105,340칸을 채점해 "있을 법한 곳"을 표시(신뢰 등급 A~E 병기)

**시민과학**
- 발견 제보 — 사진 업로드가 1순위(EXIF GPS로 위치 자동입력, 없으면 지도 클릭). 관리자 승인 후 집계에 반영
- 미션보드 · 리더보드 · 관심종(watchlist)

**그 밖에**
- 대화형 도우미 — 화면 우하단 패널. 질문을 받아 Postgres 도구 9종을 골라 호출한다(Gemini function-calling, Edge Function `chat`)
- 종 동정 연습(`5_App/quiz.html`) — 사진으로 분류군·과·속을 맞히는 퀴즈
- 지역·분류군 프로필 페이지 153개 — 공유·검색엔진용 정적 페이지(`build_profiles.py` 생성)
- 공개 MCP 서버(`7_MCP/`) — 자세한 도구 목록은 [`7_MCP/README.md`](7_MCP/README.md)

---

## 빠른 시작

### 조회 화면만 띄우기 (설정 0)

```bash
git clone https://github.com/RachHus/Finding-gap.git
cd Finding-gap
python -m http.server 5173 --directory docs
```

브라우저에서 http://localhost:5173 . `docs/` 는 배포와 **똑같은 빌드 산출물**이라 이대로 동작한다.

소스를 고치며 볼 때는 `--directory 5_App` 을 쓴다. 이때 `5_App/config.js` 가 없으면 배경지도는
**OSM 으로 자동 폴백**되고 로그인·제보·도우미는 꺼진 채로 뜬다(조회는 그대로 된다).

### 키를 넣어 전체 기능 켜기

런타임 설정은 `5_App/config.js` 한 파일에 담긴다(git 제외). 이 파일은 `5_App/.env` 에서 생성한다 —
템플릿은 [`5_App/.env.example`](5_App/.env.example).

```bash
cp 5_App/.env.example 5_App/.env      # 값을 채운 뒤
python 5_App/build_dist.py --out 5_App_local   # config.js 를 포함한 전체 산출물 생성
```

배경지도 키만 필요하면 `python 5_App/_make_config.py` 로 충분하다(이 스크립트는 `VWORLD_KEY` 만 주입한다).

| 키 | 없으면 |
|---|---|
| `VWORLD_KEY` | 국내 상세 배경지도 없이 OSM 만 사용 |
| `SUPABASE_URL` · `SUPABASE_KEY` | 로그인·제보·관심종 비활성. **publishable 키만 쓴다** — 관리자 권한 키(대시보드의 secret 키)는 어디에도 넣지 않는다 |
| `CHAT_ENABLED` | 대화형 도우미 버튼 숨김 |
| `GA4_MEASUREMENT_ID` | 사용 통계 미수집 |

### 데이터를 다시 만들려면

파이프라인 실행에는 Python(pandas·geopandas)과 R 4.5.0 이 필요하다.
단계·순서·필요 환경은 [`3_ETL/README.md`](3_ETL/README.md) 와 [`3_ETL/DATA_PIPELINE.md`](3_ETL/DATA_PIPELINE.md) 가 단일 출처다.

---

## 폴더 구조

```
Finding-gap/
├─ 1_Data/         # 원천·정제·공간 데이터 — 대용량이라 git 제외(.gitkeep만 추적)
├─ 3_ETL/          # 수집·정합·집계 파이프라인 (python · R) + DATA_PIPELINE.md
├─ 4_References/   # 코드가 읽는 매핑표(CSV) · 로고 원본 — 저작권 원문서는 제외
├─ 5_App/          # 웹앱 소스 + 정적 자산 빌드 스크립트 + Supabase 스키마·함수
│   ├─ index.html      # 서비스 본체(단일 파일: 마크업·스타일·스크립트)
│   ├─ quiz.html       # 종 동정 연습
│   ├─ build_*.py      # demo/data/* 정적 자산 생성 · dist 조립
│   ├─ demo/data/      # 브라우저가 직접 읽는 산출 자산(.js)
│   └─ supabase/       # 스키마(SQL) · Edge Function(chat) · 참조데이터 적재
├─ 6_Deliverables/ # 배포 가이드 · 향후 계획
├─ 7_MCP/          # 공개 읽기전용 MCP 서버(Python) + 데이터 빌드
└─ docs/           # GitHub Pages 서빙본 — build_dist.py 산출물(손으로 고치지 않는다)
```

> 폴더명은 코드·CLI·git 호환을 위해 공백·점 없이 `1_Data` 형식을 쓴다.
> `2_Planning/`(내부 기획)과 `8_mentoring/`(멘토링 기록)은 로컬 전용이라 저장소에 없다.

---

## 데이터 파이프라인

원천 → 정합 → 서비스 정적 자산. 스키마·매칭 규칙·갱신 주기의 단일 출처는 [`3_ETL/DATA_PIPELINE.md`](3_ETL/DATA_PIPELINE.md).

```
NIBR KTSN · EcoBank · 국립공원공단 · GBIF · 국가적색목록/멸종위기 등급
   │  3_ETL  (학명 정합: KTSN 마스터 + 변종/품종 별칭 + 수기 보정 + 이명.
   │          학명과 국명이 서로 다른 정명을 가리키면 폐기 / 시군구 공간결합 / 연도·건수 집계)
   ▼
1_Data/processed  (ktsn_master.csv · observation_*.csv · observations.sqlite ...)
   │  5_App/build_*.py
   ▼
5_App/demo/data/*.js  ──build_dist.py──▶  docs/  ──▶  GitHub Pages
```

- 정합 기준키는 **KTSN 종코드**. 적색목록은 마스터의 `national_redlist_category`, 멸종위기는 `endangered_grade`.
- 갱신 주기 6개월 — 원천 ETL → `build_*.py` → `build_dist.py` → 커밋·push.

---

## 배포

**조회 화면(①)** — GitHub Pages, `main` 브랜치의 `/docs` 폴더.

```bash
python 5_App/build_dist.py --osm-only --out docs
```

`docs/` 를 커밋·push 하면 Pages 가 자동으로 갱신된다. **`docs/` 를 직접 편집하지 않는다** — 다음 빌드에서 덮어써진다.

**계정·제보·도우미(②)** — Supabase. 스키마 적용 순서와 함수 배포 절차는
[`5_App/supabase/README.md`](5_App/supabase/README.md) 와 [`6_Deliverables/DEPLOY.md`](6_Deliverables/DEPLOY.md).

**MCP 서버(③)** — 배포가 없다. 각자 로컬에 설치해 쓴다([`7_MCP/README.md`](7_MCP/README.md)).

---

## 문서 지도

| 알고 싶은 것 | 문서 |
|---|---|
| 데이터가 어디서 와서 어떻게 정합되는가 | [`3_ETL/DATA_PIPELINE.md`](3_ETL/DATA_PIPELINE.md) |
| 파이프라인을 어떤 순서로 돌리는가 | [`3_ETL/README.md`](3_ETL/README.md) |
| 정적 자산·빌드 스크립트가 무엇을 만드는가 | [`5_App/README.md`](5_App/README.md) |
| DB 스키마를 새 환경에 재현하는 법 | [`5_App/supabase/README.md`](5_App/supabase/README.md) |
| 배포 절차 | [`6_Deliverables/DEPLOY.md`](6_Deliverables/DEPLOY.md) |
| MCP 도구 명세·집계 규칙 | [`7_MCP/README.md`](7_MCP/README.md) · [`7_MCP/MCP_DATA_CONTRACT.md`](7_MCP/MCP_DATA_CONTRACT.md) |
| 무엇을 공개하고 무엇을 빼는가 | [`SHARING.md`](SHARING.md) |
| 무엇이 언제 바뀌었는가 | [`CHANGELOG.md`](CHANGELOG.md) |

---

## 데이터 출처

- **국가생물종목록(KTSN) · 국가생물적색자료집 · 디지털자료관 도판** — 국립생물자원관(NIBR)
- **조사 관측** — EcoBank(국립생태원) · 국립공원공단 생물자원 현황
- **분류 보강 · 관측 보강** — GBIF
- **종 사진** — iNaturalist (CC 라이선스 사진만, 저작자 표시)
- **행정경계** — 통계청 SGIS
- **배경지도** — © OpenStreetMap 기여자 / (선택) © VWorld

원천 자료는 각 기관의 이용조건(공공누리, CC 등)을 따른다. 상업적 이용은 전제하지 않는다.

## 보안·공유

API 키(`.env`) · 클라이언트 설정(`config.js`) · 원천/정제 데이터 · 저작권 참고자료는 git 에서 제외된다.
공개·비공개 경계와 그 이유는 [`SHARING.md`](SHARING.md) 에 정리돼 있다.
