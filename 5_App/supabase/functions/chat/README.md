# chat — 발견공백 대화형 도우미 (Supabase Edge Function)

로그인 사용자의 질문을 Gemini(함수호출)로 처리하고, 도구는 `fg_*` 참조 테이블만 조회한다.
원시 좌표·개인정보는 노출하지 않으며, 하루 사용 횟수를 제한한다.

## 초기 구성 순서 (처음부터)

### 1. 스키마 생성

Supabase SQL Editor에서 다음 순서로 실행:

```
5_App/supabase/conversational_service.sql
  ↓ (fg_species, fg_species_region, fg_region, fg_taxa, chat_usage 생성)
5_App/supabase/conversational_service_taxon.sql
  ↓ (fg_species 칼럼 확대, fg_taxon_name 생성)
5_App/supabase/conversational_service_taxon_ranks.sql
  ↓ (fg_taxon_name 제약 확대, pg_trgm 인덱스)
5_App/supabase/conversational_service_perf.sql
  ↓ (fg_species_national MV, 커버링 인덱스)
```

상세는 `5_App/supabase/README.md`의 "스키마 구성 파일" 표 참조.

### 2. 참조 데이터 적재

`.env`에 `SUPABASE_DB_URL` 추가 후:

```bash
# 강·목·과·속 한글명 사전 생성(필요 시)
python 7_MCP/build_taxon_names.py

# 데이터 적재
python 5_App/supabase/load_reference.py
```

이 스크립트가 `fg_species`, `fg_species_region`, `fg_region`, `fg_taxa`, `fg_taxon_name`을 적재하고, `fg_species_region` 재적재 시 자동으로 `fg_species_national` MV를 REFRESH합니다. 부분 재적재는 `--only fg_taxon_name,fg_species` 등으로 가능.

### 3. Gemini 키 설정

```bash
supabase secrets set GEMINI_API_KEY=...
```

선택 사항:
- `GEMINI_MODEL` — 기본 `gemini-flash-lite-latest`
- `CHAT_ABUSE_CAP` — 기본 300 (자동화 남용 방지용, 사용자는 닿지 않는 값)

주의: 무료 tier는 매우 제한적(`gemini-flash-latest`는 20/일). 실사용은 종량제 권장.

### 4. Edge Function 배포

```bash
supabase functions deploy chat
```

### 5. 프런트 노출

`.env`에 `CHAT_ENABLED=1` 추가 후:

```bash
python 5_App/build_dist.py --osm-only --out docs
```

커밋·푸시. 플래그가 off면 `chat.html`은 "곧 제공" 안내만 표시.

## 변경 시 재적용

### 스키마만 바뀐 경우

테이블 칼럼·인덱스·함수 정의를 추가/수정했을 때:

1. 해당 SQL 파일을 Supabase SQL Editor에서 재실행
2. Edge Function은 재배포 불필요 (코드 변경 없음)
3. 새로운 데이터가 필요한 경우만 `load_reference.py` 실행

**예**: `conversational_service.sql`에 테이블 칼럼을 추가한 경우, 파일을 다시 실행하면 `ALTER TABLE`로 추가되고 기존 행은 유지됨. `load_reference.py`는 필수 아님.

### 참조 데이터가 바뀐 경우

MCP SQLite(`7_MCP/data/fg_mcp.sqlite`)가 갱신되었을 때:

```bash
python 5_App/supabase/load_reference.py
```

또는 특정 테이블만:

```bash
python 5_App/supabase/load_reference.py --only fg_species,fg_species_region
```

- `fg_species_region` 재적재 시 `fg_species_national` MV 자동 REFRESH
- `fg_taxon_name`만 갱신하려면 `build_taxon_names.py` 선행 (별도 커밋본이 있으면 생략 가능)
- Edge Function 재배포 불필요

### 함수 코드만 바뀐 경우

`index.ts` 로직을 수정했을 때:

```bash
supabase functions deploy chat
```

- 스키마·데이터 재적용 불필요 (도구 로직 변경만)
- **단, 새로운 스키마 칼럼을 읽으려면 먼저 SQL 파일로 칼럼 추가 필요**

**예**: `index.ts`에서 `fg_species`의 새 칼럼을 읽도록 수정했으면, 먼저 해당 SQL 파일(`conversational_service_taxon.sql` 등)에 칼럼을 추가한 뒤 함수를 배포해야 함.

## 요청/응답

`POST /functions/v1/chat` · 헤더 `Authorization: Bearer <user_jwt>` (로그인 필수).
- 본문: `{ "messages": [{ "role": "user"|"assistant", "content": "..." }] }`
- 응답: `{ "reply": "...", "used_tools": ["..."] }`
- 미로그인 401, 키 미설정 503. `CHAT_ABUSE_CAP`은 자동화된 남용으로 무료 사용량이 한 번에
  소진되는 것만 막는 안전판이라, 사람이 쓰다가 닿을 값이 아니고 화면에도 표시하지 않는다(초과 시 429).

## 도구

`find_region` · `region_discovery_summary` · `undiscovered_priority_species` ·
`search_species` · `species_detail` · `list_protected_species` · `taxa_summary` ·
`list_species_by_taxon`(강·목·과·속 단위 종 목록·발견상태. 강·목·과·속 한글명 모두 `fg_taxon_name`
(KTSN 전체 매핑, `7_MCP/build_taxon_names.py`)으로 해석 — 커버리지 강96%·목95%·과96%·속69%.
정확 일치 실패 시 `pg_trgm` 유사도로 `suggestions`(후보) 반환. 라틴 학명도 가능. KTSN 마스터가
강-목-과-속-종/아종뿐이라 아과·족은 범위 밖 — `3_ETL/DATA_PIPELINE.md` 참고) ·
`taxon_gap_ranking`(과·속 단위 발견공백 순위 — `taxon_group`·`region` 한정, `only_zero_found`로 완전 미발견 분류군만).
발견 정의: 발견=최근 10년 내 기록, 휴면=기록은 있으나 10년 이상 미보고, 미발견=기록 없음.
