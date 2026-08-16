# 3_ETL — 데이터 수집·정합·집계 파이프라인

NIBR·GBIF·EcoBank·국립공원 원천을 받아 학명을 정합하고, 서비스가 그대로 읽는 **정적 자산**(`5_App/demo/data/*.js`)과 환경·모형 자산을 만든다.

전체 구조·스키마·매칭 규칙·갱신 주기는 **[DATA_PIPELINE.md](DATA_PIPELINE.md)** 가 단일 출처다. 이 파일은 진입점만 안내한다.

## 두 체인

| 체인 | 언제 | 진입점 |
|---|---|---|
| **A. 관측 ETL** | 원자료가 갱신될 때(6개월) | `3_ETL/python/` 의 스크립트를 순서대로 — DATA_PIPELINE.md §3-A |
| **B. 환경·모형 자산** | A 이후, 또는 환경 레이어·모형 규칙이 바뀔 때 | `python 3_ETL/run_pipeline.py` (12단계) — §3-B |

```bash
python 3_ETL/run_pipeline.py --list         # 단계 목록
python 3_ETL/run_pipeline.py                # B 체인 전체
python 3_ETL/run_pipeline.py --from model   # 특정 단계부터
```

두 체인은 `1_Data/processed/observations.sqlite`(점 DB)에서 만난다 — A가 만들고 B가 읽는다.

## 서빙 구조

정적 자산이 곧 서비스다. 발견공백은 저장하지 않고 클라이언트가 여집합으로 계산하며, 서식지 후보도 브라우저가 종별 MaxEnt 계수로 105,340개 셀을 채점한다. Supabase는 조회 경로가 아니라 **시민 제보·로그인·대화형 도우미**(Feature B) 전용이다.

## 실행 환경

- R: `"C:/Program Files/R/R-4.5.0/bin/Rscript.exe"`. 경로에 공백이 있어 스크립트 직접 실행이 실패하므로(exit 127) `Rscript --vanilla -e "source('…')"` 형태로 부른다. `run_pipeline.py` 는 이미 그렇게 호출한다.
- Python: geopandas가 필요한 단계(`etl_observation`·`etl_national_park`·`etl_gbif`·`build_sigungu_agg`·`build_cell_sigungu`·`build_cell_water`·`improve_species_list`)는 **anaconda python**(`C:\Users\yssfr\anaconda3\python.exe`)으로 실행한다. PATH의 Windows Store python에는 geopandas가 없다.
- 스케줄러는 없다. 갱신은 수동 실행이며 주기는 DATA_PIPELINE.md §4 표를 따른다.

## 주의

- NIBR API: 인증키(`oapiAcsUnqNo`) + 허용 IP 승인 필요. 빌드타임 전용이며 키는 `.env`(gitignored)에 둔다.
- GBIF 다운로드는 자격증명이 필요하다. 비대화형 실행이면 `$env:R_ENVIRON_USER='…\.Renviron'` 을 먼저 설정한다.
- 원시 좌표점(`observations.sqlite`, 5.3M행)은 **공개하지 않는다.** 배포·MCP로 나가는 것은 집계뿐이다.
- Sentinel `.tif` 를 zip에서 직독하면 손상된 `.ovr` 오버뷰 때문에 GDAL이 heap 크래시를 낸다. `sentinel` 단계가 `.tif` 만 로컬 캐시로 뽑아 쓰는 이유다. 진행 로그도 Google Drive 폴더가 아니라 `LOCALAPPDATA` 에 쓴다(Drive File Stream 필터와 충돌).
