# 3_ETL — 데이터 수집·정합·집계 파이프라인

NIBR·GBIF·EcoBank 원천을 받아 학명을 정합하고, 서비스용 집계 테이블을 만들어 Supabase에 적재한다.

## 단계
| 순서 | 위치 | 내용 | 산출 |
|---|---|---|---|
| 1 | `python/` | NIBR 종목록 API 수집 (분류군 1~11) | `1_Data/raw/nibr_*.json` |
| 2 | `R/` | GBIF occurrence 추출 (`rgbif`, 대한민국 + 1단계의 class 목록) | `1_Data/raw/gbif_*.csv` |
| 3 | `python/` | EcoBank 조사사업 수집 (KTSN 또는 학명) | `1_Data/raw/ecobank_*` |
| 4 | `python/` | **학명 3중 매칭** (KTSN ⟷ GBIF accepted ⟷ 조사자료), 미매칭 제외, 멸종위기 등급 태깅 | `1_Data/processed/matched_species.parquet` |
| 5 | `python/` | 집계: `(KTSN, 시도, 연도, 출처, 발견횟수)` + 미발견/빈발견 뷰 | `1_Data/processed/occurrence_summary.*` |
| 6 | `sql/` | Supabase 스키마(DDL)·materialized view 정의·적재 | Supabase |

## 실행 환경
- R: `"C:/Program Files/R/R-4.5.1/bin/Rscript.exe"`
- Python: 프로젝트 venv (`.venv`)
- 스케줄: GitHub Actions cron (무료) — 주기 재적재

## 주의
- NIBR API: 인증키(`oapiAcsUnqNo`) + 허용 IP 승인 필요.
- 원시 occurrence는 저장하지 않고 **집계만 Supabase 적재**(무료 용량 대응).
