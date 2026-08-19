# Supabase 스키마 및 데이터 구성

발견공백 서비스의 백엔드를 이루는 Postgres 스키마와 참조 데이터를 처음부터 구성하는 방법을 설명합니다.

## 스키마 구성 파일

| 파일 | 만드는 것 | 선행 조건 | 멱등성 | 설명 |
|------|---------|---------|------|------|
| `auth_baseline.sql` | `profiles` 테이블, `watchlist` 테이블, 자동 가입 트리거 함수, RLS 정책 | 없음 | 예 | 사용자 기본 정보(프로필·역할·관심종). 이 두 테이블은 Supabase 대시보드에서 먼저 만들어졌으나 새 환경에서 재현할 수 있게 여기 남김. RLS로 본인 행만 조회 가능. |
| `reports.sql` | `reports` 테이블, 시민과학 RPC 함수(`community_reports()`, `report_leaderboard()`, `approved_discoveries()`), 관리자 정책 | `auth_baseline.sql` | 예 | 시민과학 제보(URL·좌표·발견일). 정밀 좌표는 원시 테이블에만 보관하고 공개 피드는 좌표를 노출하지 않음. 정리 상태(`status`) 및 공백 메움 여부(`fills_gap`)는 P2(현재 NULL). |
| `reports_photo.sql` | `reports.url` 칼럼을 선택 사항으로, `photo_path` 칼럼 추가, Storage 버킷 `report-photos`, `community_reports()` 함수 재정의 | `reports.sql` | 예 | 제보에 사진 업로드 기능 추가. 함수 반환 컬럼이 바뀌므로 기존 함수를 DROP 후 재생성. |
| `species_watch_counts.sql` | `species_watch_counts()` RPC — 종별 관심종 익명 집계 | `auth_baseline.sql` | 예 | 사용자의 `watchlist`를 종별로 집계해 반환. 3명 이상이 담은 종만 노출해 개인 관심도를 역추적하지 않게 함. |
| `conversational_service.sql` | `fg_species`, `fg_species_region`, `fg_region`, `fg_taxa` 테이블, `chat_usage` 테이블, RLS 및 권한 회수 | 없음(다른 테이블과 독립) | 예 | 대화형 도우미의 기본 스키마. 이 테이블들은 MCP 집계(7_MCP) 데이터의 Postgres 사본이며, Edge Function 코드가 DB 직결로 조회. REST API 접근은 차단(권한 회수). |
| `conversational_service_taxon.sql` | `fg_species`에 분류법 칼럼 추가(`class_la`, `order_la`, `family_la`, `genus_la`), `fg_taxon_name` 테이블 신설, 인덱스 | `conversational_service.sql` | 예 | 강·목·과·속 단위 질의를 지원하기 위해 KTSN 분류 체계 칼럼 추가 및 라틴↔한글 매핑 테이블 생성. |
| `conversational_service_taxon_ranks.sql` | `fg_taxon_name`의 CHECK 제약 확대(`class`/`order` 포함), 퍼지매칭 인덱스 | `conversational_service_taxon.sql` | 예 | 강·목까지 한글명 질의 지원. 오타 및 철자 변형(예: 딱따구리↔딱다구리)을 `pg_trgm`으로 근사 매칭. |
| `conversational_service_perf.sql` | 전국 발견 롤업 물리화 뷰(MV) `fg_species_national`, 지역 한정 경로 커버링 인덱스 | `conversational_service.sql` | 예 | 쿼리 성능 개선. 전국 집계는 `fg_species_region` 전량 GROUP BY 대신 사전집계 된 MV를 사용. 지역 한정 경로는 인덱스 전용 스캔으로 최적화. |

## 적용 순서

### 1단계: 기본 스키마 (사용자·시민과학)

```
auth_baseline.sql
  ↓
reports.sql
  ↓
reports_photo.sql
  ↓
species_watch_counts.sql
```

각 단계는 Supabase 대시보드의 SQL Editor 또는 MCP의 `apply_migration` 도구로 실행합니다.

### 2단계: 대화형 도우미 스키마

```
conversational_service.sql
  ↓
conversational_service_taxon.sql
  ↓
conversational_service_taxon_ranks.sql
  ↓
conversational_service_perf.sql
```

이 4개 파일도 순서대로 SQL Editor에서 실행하되, 마지막 파일(`conversational_service_perf.sql`)은 참조 데이터가 없어도 스키마 정의만 완성하면 됩니다.

### 3단계: 참조 데이터 적재

스키마 적용이 끝난 뒤, 환경변수를 설정해 데이터를 로드합니다:

1. **환경변수 설정** — 프로젝트 루트의 `.env` 파일에 추가:
   ```
   SUPABASE_DB_URL=postgresql://...
   ```
   값은 Supabase Dashboard → Project Settings → Database → Connection string에서 **Direct connection** 또는 **Session pooler** URI를 복사합니다. (Transaction pooler는 COPY 불가)

2. **MCP SQLite 준비**(필요 시):
   ```bash
   # 7_MCP/data/fg_mcp.sqlite 또는 fg_mcp.sqlite.gz 가 있는지 확인
   # 없으면 데이터 파이프라인을 실행해 생성해야 함 (이 작업의 범위 밖)
   ```

3. **분류명 매핑 생성**(필요 시):
   ```bash
   # 강·목·과·속 한글명 사전이 아직 없으면:
   python 7_MCP/build_taxon_names.py
   # → 7_MCP/data/taxon_names.json.gz 생성
   ```

4. **데이터 적재**:
   ```bash
   # 전체 재적재
   python 5_App/supabase/load_reference.py
   
   # 또는 특정 테이블만 (590k행 재적재 스킵):
   python 5_App/supabase/load_reference.py --only fg_taxon_name,fg_species
   ```

   이 스크립트는:
   - `7_MCP/data/fg_mcp.sqlite`(또는 `.sqlite.gz`)의 데이터를 읽음
   - Postgres의 `fg_species`, `fg_species_region`, `fg_region`, `fg_taxa`를 TRUNCATE 후 벌크 로드
   - `fg_taxon_name`을 `7_MCP/data/taxon_names.json.gz`에서 적재
   - `fg_species_region` 재적재 시 물리화 뷰 `fg_species_national`을 자동 REFRESH

### 4단계: Edge Function 배포

대화형 도우미 함수는 별도로 배포합니다:
- 스키마는 위의 단계로 Postgres에 반영
- 함수 코드 및 비밀키 설정은 `5_App/supabase/functions/chat/README.md` 참조

## 주요 설계 원칙

### RLS(행 수준 보안) 정책

| 테이블 | 정책 | 이유 |
|-------|------|------|
| `profiles` | 로그인 사용자가 본인 행만 조회/수정 | 개인 프로필 보호 |
| `watchlist` | 로그인 사용자가 본인 행만 조회/추가/삭제 | 개인 관심 목록 보호. 익명 집계는 별도 RPC(`species_watch_counts`)로 제공 |
| `reports` | 본인 행만 조회/삭제 + 관리자 전체 조회/상태 수정 | 제보자 개인정보 보호. 공개 피드는 별도 RPC(`community_reports`)로 정제해 제공 |
| `fg_species`, `fg_species_region`, `fg_region`, `fg_taxa`, `fg_taxon_name` | RLS 활성화 + 익명/인증 권한 회수 | Edge Function만 DB 직결로 접근 가능. REST API로는 직접 조회 불가 |
| `chat_usage` | 로그인 사용자가 본인 사용량만 조회 | 공용 API 배포 시 이용 현황 투명성. Edge Function이 직결로 업데이트 |

### 데이터 노출 계층

1. **비공개** — 원시 행 데이터 (좌표·개인정보)
   - 저장: `reports.lat`, `reports.lon` (정밀도)
   - 노출: 안 함

2. **공개(RPC를 통한 집계만)**
   - `community_reports()` — 제보 피드(좌표 미노출, 거부 제외, 제보자는 익명)
   - `species_watch_counts()` — 종별 관심도(3명 이상만, 개인 이력 미노출)
   - Edge Function → MCP — 지역/종 단위 재발견 정보

3. **공개 API** — 7_MCP 읽기 전용 MCP 서버

## 파일 참조

- **스키마 생성**: 위의 8개 `.sql` 파일
- **데이터 적재**: `load_reference.py` (MCP SQLite → Postgres 복사)
- **Edge Function 배포**: `functions/chat/README.md`
- **MCP 데이터 출처**: `7_MCP/data/` (SQLite + JSON 압축)
- **ETL 파이프라인**: `3_ETL/DATA_PIPELINE.md` (관측데이터 수집·집계)
