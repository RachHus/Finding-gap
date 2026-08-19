# Finding gap — 기능 진행 현황

서비스는 정적 조회 화면(조회는 브라우저에서 끝남)과 동적 기능(로그인·제보·도우미)으로 이루어진다.
원래 설계했던 3단계 구현은 대부분 완료되었으며, 아래 항목들의 현황을 정리한다.

## 구현 현황 요약

| 항목 | 상태 | 참고 |
|------|------|------|
| 로그인 (Google OAuth + 이메일) | 구현됨 | v0.9.0 이래 지원 |
| 관심종 저장 (Supabase RLS) | 구현됨 | v0.9.0 이래 지원 |
| 발견 제보 (사진 + EXIF) | 구현됨 | v0.10.0에서 사진 업로드 추가 |
| 대화형 도우미 (Chat) | 구현됨 | v0.10.0에서 라이브, 강·목·과·속 질의 지원 |
| Open MCP 서버 | 운영 중 | 7_MCP/ 에서 공개 읽기전용 서버 운영 |
| 관리자 페이지 | 계획 중 | 미발견, 아래 Phase 2 참고 |

## 채택된 아키텍처

| 평면 | 서비스 | 상태 |
|------|--------|------|
| 정적 조회 | **정적 호스팅** (Cloudflare Pages / GitHub Pages) | 운영 중 |
| 로그인 + 사용자 기능 | **Supabase Auth + Postgres(RLS)** | 운영 중 |
| 대화형 도우미 | **Supabase Edge Function(chat) + Gemini** | 운영 중 |
| 공개 읽기 MCP | **7_MCP (로컬 Python + FastMCP)** | 운영 중 |
| ETL(배치) | 로컬 Postgres/PostGIS + GitHub Actions | 운영 중 |

비용: **무료~$25/월** (초기 무료, 사용자 규모에 따라 Supabase 유료 플랜 전환 가능).

## Phase 1: 로그인 기반 — [구현됨]

### Google 로그인 및 기본 인증
- **상태:** v0.9.0부터 운영 중
- Supabase `signInWithOAuth({provider:'google'})` + JWT.
- 이메일 매직링크도 지원.
- 모든 테이블에 RLS(행 수준 보안) 적용.

### 관리자 페이지 (계획 중)
- 신규 `admin.html`: 미로그인 리다이렉트 + role 체크.
- 탭: 평가 검수 / 의견 관리 / 사용자 활동 / 설정.
- 권한: `user`(제보·평가·의견) vs `admin`(검수·관리).

## Phase 2: 사용자 기능 입력 및 평가 — [부분 구현]

### 개요
**상태:** v0.10.0에서 발견 제보(사진 업로드) 구현. 관심종·평가·의견은 스키마 준비됨.

### 실장 이력
- v0.10.0에서 **발견 제보**의 근거를 사진 업로드로 변경 (기존 URL 입력 → 사진 1순위, EXIF GPS로 위치 자동입력).
- 사진 저장소: Supabase Storage(`report-photos` 버킷, 사용자별 폴더).

### 아직 구현 안 된 항목 (계획)

다음 항목들의 테이블·API는 이미 설계됐으며, 필요 시 `service.html` 종 검색(Mode B) 종 카드에 UI 추가만 하면 된다.

### 즐겨찾기 `favorite_species`
| 항목 | 타입 | 필수 | 검증 |
|---|---|---|---|
| 메모 | TEXT | N | 0~500자 |
| (user_id, ktsn) | | | UNIQUE — 종당 1회 |

### 희귀도 평가 `rarity_assessment`
| 항목 | 타입 | 필수 | 검증/선택지 | 비고 |
|---|---|---|---|---|
| 희귀도 스코어 | INT | Y | 1~5 (1흔함·2보통·3드문·4아주드문·5극히드문) | IUCN 간략화 |
| IUCN 범주 매핑 | ENUM | N | CR·EN·VU·NT·LC·DD·(공란) | 전문가 검수용 |
| 근거 메모 | TEXT | N | 0~500자, HTML strip | XSS 방지 |
| 신뢰도 | INT | N | 0~100%, 10단위 | 기여도 가중치 |
| (user_id, ktsn, type) | | | UNIQUE | |

희귀도 5단계 ↔ IUCN: 1=LC, 2=NT, 3=VU, 4=EN, 5=CR. `iucn_category_match`로 학술용 승격 가능.
관계: 종 마스터의 `national_redlist_category`(공식 평가)와 별개의 **시민 체감 평가**로 병기.

### 의견 `comment`
| 항목 | 타입 | 필수 | 검증 |
|---|---|---|---|
| 의견 텍스트 | TEXT | Y | 1~2000자, HTML strip |
| 대댓글 대상 | UUID | N | parent_comment_id 유효성 |
| is_moderated | BOOL | Y | 기본 false(관리자 검수 전) |

## Phase 3: Open MCP 서버 — [구현됨]

### 상태
- v0.10.0부터 라이브.
- 저장소: `7_MCP/` (Python + FastMCP).
- 공개 읽기전용, 인증 불필요 (일부 도구만 로그인 필수).
- 원시 좌표·개인정보는 노출하지 않음 (공개 하한 K-익명 3 적용).

### 노출 도구

| 도구 | 입력 | 출력 | 인증 |
|---|---|---|---|
| search_species | query, limit | 종 기본정보 + IUCN 등급 + NIBR 링크 | 공개 |
| get_species_status | ktsn | 발견현황(시도·연도), 적색목록 등급, 출처 | 공개 |
| find_undiscovered_species | taxon_group?, sido?, year? | 미발견종 목록 | 공개 |
| list_red_list | category?, taxon_group? | 적색목록 종 + 관측 여부 | 공개 |
| region_gap_summary | sido, taxon_group? | 시도별 공백 현황 | 공개 |
| list_species_by_taxon | taxon(강·목·과·속), region? | 분류군 내 종 목록 + 발견상태 | 공개 |
| taxon_gap_ranking | taxon_group?, sido? | 과·속 단위 발견공백 순위 | 공개 |
| get_user_contributions | user_id | 유저 기여(평가·의견·관심종) | 로그인 |
| submit_rarity_assessment | (평가 스키마) | 제출 결과 | 로그인 |

원출처(sources[]) 동봉 원칙 유지.

## 구현 현황

### Phase 1 — 완료
- Supabase Auth + Google OAuth
- 관심종 저장 (`favorite_species` + RLS)
- 로그인 UI 통합

### Phase 2 — 부분 완료
- 발견 제보 (사진 업로드)
- 평가·의견 테이블/API (설계됨, UI 미통합)
- 관리자 페이지 (계획 중)

### Phase 3 (MCP) — 완료
- 7_MCP 서버 운영 중
- 9개 도구 지원
- 공개 읽기전용, K-익명 보호

## 유지 및 위험 요소

### Supabase 비용
- 초기: 무료 (월 50,000 이상의 쿼리)
- 1,000명+ 사용자: 유료 플랜 전환 고려

### 보안 및 개인정보
- 모든 입력: HTML strip으로 XSS 방지
- 탈퇴 시: 이메일·닉네임 익명화
- 이용약관·처리방침 필수

### 데이터 정신성
- ETL 갱신: GitHub Actions cron + 멱등 upsert
- MCP 데이터셋: 생성일 자동 기록

---
*이 문서는 기획 기록이다. 구현 상태는 위 요약 표를 기준으로 하며, 추가될 기능들의 설계는 보존된다.*
