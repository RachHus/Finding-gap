-- 발견공백 사유 태깅 — 종별 분류학 상태 확인 이력(GBIF 이명 여부·국가적색목록 지역절멸).
-- "미발견"이 진짜 조사부족인지, 이명(synonym) 잔재나 이미 지역절멸(RE)된 종이라 애초에
-- 찾을 대상이 아닌지를 구분하기 위한 근거 데이터. Darwin Core taxonomicStatus 어휘 재사용.
--
-- append-only — 절대 UPDATE/TRUNCATE하지 않는다. 매 체크마다 새 행을 쌓고, "현재 상태"는
-- (ktsn, source)별 최신 checked_at 행으로 조회한다(GBIF 백본이 재빌드되며 판정이 바뀔 수 있어,
-- 이력을 지우면 그 변화를 추적할 수 없다).
--
-- RLS 활성 + 공개 정책 없음 + anon/authenticated 권한 회수 → conversational_service.sql 의
-- fg_species 등과 동일한 잠금 패턴(참조 데이터, service-role 배치 스크립트만 기록).
--
-- 적재: python 7_MCP/check_gbif_synonyms.py --push (SUPABASE_DB_URL 필요).
-- 적용: Supabase 대시보드 SQL Editor에서 이 파일 실행.

create table if not exists public.fg_taxon_status_check (
  id bigint generated always as identity primary key,
  ktsn text not null,
  source text not null,              -- 'gbif_backbone' | 'redlist'
  taxonomic_status text,             -- gbif: ACCEPTED/SYNONYM/HOMOTYPIC_SYNONYM/... · redlist: 'RE'
  matched_name text,                 -- GBIF 인정 현재명(이명일 때만) — redlist 소스는 null
  detail jsonb,                      -- 원본 응답 보관(matchType·confidence·usageKey 등)
  checked_at timestamptz not null default now()
);
create index if not exists taxon_status_check_lookup
  on public.fg_taxon_status_check (ktsn, source, checked_at desc);

alter table public.fg_taxon_status_check enable row level security;
revoke all on public.fg_taxon_status_check from anon, authenticated;