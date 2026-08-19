-- 분류 이력 전문가 제보 — 논문 근거(DOI) 기반. 로그인 사용자가 "이 종의 학명이 이 논문 때문에
-- 바뀌었다"를 제출하고, 관리자가 검수(pending/approved/rejected)한다. `reports.sql`(시민 사진·URL
-- 제보)과 완전히 같은 패턴 — RLS 본인 행만, 관리자 role로 전체 조회·상태변경.
--
-- fg_taxon_status_check(오늘 만든 GBIF·적색목록 자동 체크)와는 별도 테이블이다 — 그건 검증된
-- 자동 소스의 append-only 이력이라 승인 개념이 없고, 이건 사람이 내고 검수해야 하는 큐라서
-- reports 와 같은 성격이다. 승인된 행만 build_gap_reason_snapshot.py 가 읽어 gap_reason.json에 반영.
--
-- 적용: Supabase 대시보드 SQL Editor에서 이 파일 실행.

create table if not exists public.taxon_reference_reports (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null default auth.uid() references auth.users(id) on delete cascade,
  ktsn            text not null,
  korean_name     text,
  scientific_name text,          -- 제출 시점 KTSN 현재 학명(스냅숏, reports 관례와 동일)
  to_name         text not null, -- 제보자가 주장하는 새 학명
  ref_title       text not null, -- 논문 제목(DOI 있으면 Crossref 자동, 없으면 수기)
  ref_authors     text,
  ref_year        int,
  ref_container   text,          -- 저널/단행본명
  doi             text,
  ref_url         text,          -- DOI 없는 문헌의 대체 링크
  note            text,
  status          text not null default 'pending' check (status in ('pending','approved','rejected')),
  created_at      timestamptz not null default now()
);

create index if not exists taxon_ref_user_idx   on public.taxon_reference_reports(user_id, created_at desc);
create index if not exists taxon_ref_ktsn_idx   on public.taxon_reference_reports(ktsn);
create index if not exists taxon_ref_status_idx on public.taxon_reference_reports(status, created_at desc);

alter table public.taxon_reference_reports enable row level security;

-- 본인 행만 조회/삽입 (user_id 는 default auth.uid() 로 자동 채움). 삭제는 두지 않는다 —
-- 관리자 검토 대상이 제출자 임의로 사라지면 검토 이력이 끊긴다(reports 는 삭제를 허용하지만,
-- 그건 사진·좌표라 개인정보 성격이 강하고, 이건 학술 주장이라 철회보다 반려로 남기는 편이 맞다).
drop policy if exists taxon_ref_select_own on public.taxon_reference_reports;
drop policy if exists taxon_ref_insert_own on public.taxon_reference_reports;
create policy taxon_ref_select_own on public.taxon_reference_reports for select using (user_id = auth.uid());
create policy taxon_ref_insert_own on public.taxon_reference_reports for insert with check (user_id = auth.uid());

-- 관리자(profiles.role='admin'): 전체 조회 + 상태 변경(본인행 정책과 OR 결합, reports.sql 과 동일 패턴)
drop policy if exists taxon_ref_admin_select on public.taxon_reference_reports;
drop policy if exists taxon_ref_admin_update on public.taxon_reference_reports;
create policy taxon_ref_admin_select on public.taxon_reference_reports for select
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));
create policy taxon_ref_admin_update on public.taxon_reference_reports for update
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'))
  with check (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));

comment on table public.taxon_reference_reports is
  '분류 이력 전문가 제보(논문 근거). 본인 행 RLS + 관리자 검수. 승인 행만 gap_reason.json 스냅숏에 반영(user_id 제외).';