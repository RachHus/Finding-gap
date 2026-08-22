# 5_App — 웹 서비스 정적 자산

`index.html` 을 중심으로 브라우저에서 실행되는 조회 화면의 소스와 정적 자산 빌드 스크립트를 담는다. 로그인·제보·대화형 도우미는 Supabase 백엔드(`supabase/`)를 거치지만, **조회 경로 자체(발견·미발견·서식지 후보 계산)는 모두 브라우저에서 끝난다.**

## 파일 구조

### 페이지
- `index.html` — 서비스 본체. 약 4,200줄. 마크업·스타일·스크립트가 단일 파일에 담긴다.
- `service.html`, `chat.html` — 레거시 주소 호환용 리다이렉트 껍데기. 이전 링크를 유지하기 위해 남겨 둔다.
- `quiz.html` — 종 동정 연습. 약 1,100줄의 독립 페이지.

### 클라이언트 모듈
- `fg_supabase.js` — Supabase 로그인·제보·관심종 인터페이스. 키가 없으면 자동으로 기능을 비활성화한다.
- `fg_analytics.js` — Google Analytics 4 이벤트 수집. GA4 ID가 없으면 로드되지 않는다.

### 정적 자산
- `demo/data/*.js` — 브라우저가 읽는 종 목록·관측 집계·지도·서식지 후보. 파이썬 빌드 스크립트가 생성한다.
- 로고·아이콘 — `logo.png` 등. `build_logo.py` 산출물.

### 빌드 설정
- `.env.example` — 환경변수 템플릿. 복사해서 `.env` 를 만들고 값을 채운다.
- `config.example.js` — 런타임 설정 템플릿. `build_dist.py` 가 `.env` 에서 `config.js` 를 자동 생성한다.

---

## 빌드 스크립트 (정적 자산 생성)

`build_*.py` 는 부분 재빌드를 지원하는 독립 스크립트다. 전체 체인은 [`3_ETL/run_pipeline.py`](../3_ETL/run_pipeline.py) 에서 조율한다.

| 스크립트 | 용도 | 읽는 입력 | 만드는 산출물 | 실행 시점 |
|---|---|---|---|---|
| `build_dist.py` | **정적 배포본 조립** — GitHub Pages / Cloudflare 용. 페이지·로고·데이터를 모두 모아 `docs/`(또는 지정 경로)로 복사·정리. `config.js` 도 생성. | 5_App 내 전체 소스 + demo/data/* | 6_Deliverables/dist/ (또는 `--out docs` 로 지정) | 손으로: `python 5_App/build_dist.py` 또는 `--out docs` |
| `build_env_data.py` | 종 페이지의 환경 정보(기후·지형 박스플롯) | 1_Data/processed/{species_env_stats.csv, env_national.csv} | demo/data/{species_env.js, env_meta.js} | **run_pipeline.py 에 포함** (env_data 단계) |
| `build_gap_data.py` | 발견공백 A(환경적합 미발견후보) 클라이언트 자산. 전국 1km 격자 환경값 + 종별 점유 + 메타 | 1_Data/processed/{env_grid.csv, cell_sigungu.csv, species_cells.csv, ndwi_species.csv, species_env_stats.csv, ktsn_master.csv} | demo/data/{env_grid.js, cells_<T>.js, gap_meta.js} | **run_pipeline.py 에 포함** (gap_data 단계) |
| `build_model_data.py` | 서식지 후보(관찰 추천도) 클라이언트 자산. 종별 MaxEnt 계수 + 계절 점수 + 신뢰 등급 | 1_Data/processed/{model_store/<T>.json, species_season.csv, env_grid_model.csv, env_grid.csv, ktsn_master.csv, ndwi_species.csv, cell_water.csv} | demo/data/{env_model.js, model_<T>.js, season_<T>.js, model_meta.js} | **run_pipeline.py 에 포함** (model_data 단계) |
| `build_logo.py` | 로고·파비콘·앱 아이콘 생성 | 4_References/{finding_gap_logo.png, 기관 로고 등} | logo.png·favicon.ico·apple-touch-icon.png·icon-512.png·logo_<기관>.png | 손으로: 필요할 때만 (기본: 고정) |
| `build_media_nibr.py` | NIBR 디지털자료관에서 종별 사진·세밀화 수집 | NIBR API (schKtsn, 인증키+IP 제약) | 1_Data/processed/media_nibr.json | 3_ETL/DATA_PIPELINE.md 관측 ETL 단계 참조 |
| `build_media_inat.py` | iNaturalist에서 종별 사진 수집(한반도 한정) | iNaturalist API (place_id=6891) | 1_Data/processed/media_inat.json | 3_ETL/DATA_PIPELINE.md 관측 ETL 단계 참조 |
| `build_media_index.py` | NIBR + iNaturalist 미디어 병합·분류군별 분할·대표 이미지 추출 | 1_Data/processed/{media_nibr.json, media_inat.json} + ktsn_master.csv | demo/data/{media_<T>.js, rep_<T>.js} + media_meta.js | 손으로 따로 실행 (미디어 갱신 후) |
| `build_region_gaps.py`* | 시군구×분류군 발견/공백 요약 — 활동지역·알림용 | 7_MCP/data/fg_mcp.sqlite | demo/data/region_gaps.js | **손으로 따로 실행** (run_pipeline.py 미포함, 하지만 배포본 O) |
| `build_species_interest.py`* | 종별 관심도 지수(웹 인코딩) — 지도 투명도·상세 화면 | 7_MCP/data/fg_mcp.sqlite | demo/data/species_interest.js | **손으로 따로 실행** (run_pipeline.py 미포함, 하지만 배포본 O) |
| `build_taxon_assets.py`* | 강·목·과·속 라틴명 → 한글 룩업 + 강→목→과→속 포함 관계 (종 카드 분류 체계·계층명 검색·퀴즈 범위) | 1_Data/processed/ktsn_master.csv + 1_Data/raw/nibr/ktsn_*.ndjson | demo/data/{taxon_ko.js, taxon_tree.js} | **손으로 따로 실행** (run_pipeline.py 미포함, 하지만 배포본 O) |
| `build_species_obs.py`* | 종별 관측 수 합계 — 시민과학 분류군별 관측 리더보드 | 7_MCP/data/fg_mcp.sqlite | demo/data/species_obs.js | **손으로 따로 실행** (run_pipeline.py 미포함, 하지만 배포본 O) |
| ~~`build_missions.py`~~ | 유망 공백 미션보드 — **화면에서 제거됨**(카드가 화면을 차지하는 데 비해 쓰임이 적었다). 스크립트·자산은 남아 있으나 배포본·화면에 안 들어간다 | 7_MCP/data/fg_mcp.sqlite | demo/data/missions.js | 쓰지 않음 |

> `*` 표식: `build_dist.py` 의 `DATA_FILES` 리스트에 있어서 배포본에 자동 포함되지만, `3_ETL/run_pipeline.py` 에는 포함되지 않는다. 즉, 6개월 갱신 파이프라인을 돌려도 이 네 스크립트의 산출물은 갱신되지 않는다. **자료(sqlite 등)를 갱신한 후 이 스크립트들을 **손으로 따로** 실행해야 배포본에 반영된다.**

---

## 런타임 설정 (config.js)

브라우저가 실행 중에 읽어야 할 설정(API 키 등)은 `config.js` 에 들어 있다.

```javascript
window.VWORLD_KEY = "...";          // 배경지도 키(도메인 잠금)
window.SUPABASE_URL = "...";        // Supabase 프로젝트 URL
window.SUPABASE_KEY = "...";        // Supabase publishable 키(공개·RLS 보호)
window.GA4_ID = "...";              // Google Analytics 4 측정 ID
window.CHAT_ENABLED = true|false;   // 대화형 도우미 노출 플래그
```

### 생성 방식
`build_dist.py` 가 `.env` 에서 자동 생성한다.

```bash
# .env 에 키를 넣은 뒤
python 5_App/build_dist.py                    # 배포본 + config.js 생성
# 또는 배경지도만 필요하면
python 5_App/_make_config.py                  # config.js 만 생성
```

### 키가 없을 때
각 키가 없으면(또는 빈 문자열이면) 해당 기능이 자동으로 비활성화된다:

| 키 | 없으면 |
|---|---|
| `VWORLD_KEY` | 국내 상세 배경지도 없이 OpenStreetMap만 사용 |
| `SUPABASE_URL` · `SUPABASE_KEY` | 로그인·제보·관심종·대화형 도우미 비활성 |
| `GA4_MEASUREMENT_ID` | 사용 통계 미수집 |
| `CHAT_ENABLED` | 대화형 도우미 버튼 숨김 |

---

## 개발 중에 띄우기

### 설정 없이 조회 화면만
```bash
python -m http.server 5173 --directory 5_App
```
`5_App/config.js` 가 없으면 배경지도는 OSM으로 자동 폴백되고 로그인·제보·도우미는 꺼진다. **조회 기능은 정상 작동한다.**

### 전체 기능 켜기
```bash
cp 5_App/.env.example 5_App/.env              # 값을 채운 뒤
python 5_App/build_dist.py --out 5_App_local # 로컬 배포본 생성
python -m http.server 5173 --directory 5_App_local
```

---

## docs/ 폴더 (배포본)

`build_dist.py` 의 산출물이다. **손으로 편집하지 않는다** — 다음 빌드에서 덮어써진다.

배포 절차는 루트 [`README.md`](../README.md#배포) 참조.

---

## Supabase 설정

로그인·제보·대화형 도우미 기능은 Supabase 백엔드가 필요하다. 스키마·함수 배포 절차는 [`supabase/README.md`](supabase/README.md) 참조.

---

## Google Drive 동기화

이 폴더가 Google Drive에 동기화되도록 설정되어 있다면, 다음을 **git에서만 추적**하고 Drive 동기화에서는 제외해야 한다(`repo/.gitignore` 에 이미 있음):

- `.env` (키 포함)
- `config.js` (빌드 산출물)
- `node_modules/`, `.next/`, `.vercel/` (프레임워크 캐시 — 현재 프로젝트는 Next.js 미사용)

그 외 `.py`, `.html`, `.js` 는 git에 추적되므로 Drive와 git 사이 동기화 충돌이 발생할 수 있다. 앱 소스는 Drive 밖(`C:\dev` 등) 또는 git 저장소에서 별도로 관리하고, **빌드 산출물만 이 폴더에 반영**하는 워크플로우를 권장한다.
