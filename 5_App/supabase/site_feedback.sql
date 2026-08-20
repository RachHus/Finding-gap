-- 사이트 피드백 공개 게시판(site_feedback) — 사이트 자체(버그·제안)에 대한 방문자 의견을 모은다.
-- 대상은 야생생물 관측이 아니라 "이 웹앱" 자체다 — reports·taxon_reference_reports 와 달리 검수 대기열이
-- 아니라 처음부터 전원 공개 게시판이다(운영자가 "누구나 읽는 공개 게시판"을 명시적으로 선택).
--
-- 기존 두 제보 테이블과 다른 점 — 로그인 없이도 글을 남길 수 있다:
--   · user_id 는 NOT NULL 이 아니다(anon 은 auth.uid() 가 NULL) · FK 는 on delete set null
--     (제보자가 나중에 탈퇴해도 이미 공개된 글은 남는다 — cascade 로 지우면 게시판 이력이 끊긴다)
--   · 비로그인 작성자는 profiles 가 없으므로 자기 이름을 직접 적을 수 있는 guest_name 을 둔다
--   · INSERT 정책은 to anon, authenticated 로 열어 두되, user_id 스푸핑만 막는다 — anon 은 auth.uid()
--     가 NULL 이라 애초에 남의 user_id 를 못 넣고, 로그인 사용자는 자기 id 가 아니면 거부된다
--   · 검수 게이트가 없다 — status 는 open(기본)/answered/closed 이고, 전부 즉시 공개(비공개 대기열 아님).
--     반응형 모더레이션만 한다: 문제 글은 관리자가 삭제, 답변은 admin_reply 로 공개 게시.
--   · 작성자 본인 수정/삭제는 없다(taxon_reference_reports 와 같은 이유 — 공개 게시판은 공유 기록이라
--     본인이 조용히 지우면 이미 보거나 답한 다른 사람 입장에서 맥락이 끊긴다. 게다가 익명 작성자는
--     "본인"을 증명할 방법이 없다). 관리자만 삭제(모더레이션)·수정(답변) 가능.
--   · 공개 조회는 원시 행을 직접 노출하지 않는다 — reports.sql 의 community_reports() 패턴과 동일.
--     단, 이 게시판은 애초에 숨길 필드가 없어(정밀 좌표 같은 게 없음) 상태 필터도 없다 — 즉시 공개.
--   · 스팸 방어는 이 마이그레이션 밖(클라이언트 허니팟 필드) + 메시지 길이 제약 정도로 최소화한다 —
--     CAPTCHA·레이트리밋·IP 기록은 이 프로젝트 규모에서 과잉이라 하지 않는다. REST 엔드포인트에
--     직접 스크립트로 붓는 공격에는 이 길이 제약과 관리자 사후 삭제만 방어선이라는 점을 알아둔다.
--
-- 선행조건: auth_baseline.sql (public.profiles 를 관리자 정책·표시 이름 조회에 참조)
-- 적용: Supabase 대시보드 SQL Editor 또는 MCP apply_migration 으로 실행.

create table if not exists public.site_feedback (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid default auth.uid() references auth.users(id) on delete set null,
  guest_name   text,                             -- 비로그인 작성자가 직접 적는 표시 이름(선택)
  category     text,                             -- 'bug' | 'suggestion' | 'other' (선택)
  message      text not null,
  status       text not null default 'open' check (status in ('open','answered','closed')),
  admin_reply  text,                              -- 관리자가 남기면 공개 목록에 함께 노출
  created_at   timestamptz not null default now(),
  constraint site_feedback_message_len check (length(trim(message)) > 0 and length(message) <= 2000),
  constraint site_feedback_guest_name_len check (guest_name is null or length(trim(guest_name)) <= 40),
  constraint site_feedback_category_chk check (category is null or category in ('bug','suggestion','other'))
);

create index if not exists site_feedback_created_idx on public.site_feedback(created_at desc);
create index if not exists site_feedback_status_idx  on public.site_feedback(status, created_at desc);
create index if not exists site_feedback_user_idx    on public.site_feedback(user_id, created_at desc);

alter table public.site_feedback enable row level security;

-- 누구나(익명 포함) 새 글을 남길 수 있다 — 이 리포에서 유일하게 anon insert 를 여는 테이블.
-- user_id 는 DB default auth.uid() 로 자동 채워진다. check 는 "본인 id 아니면 거부"만 한다 —
-- anon 요청은 auth.uid() 가 NULL 이라 user_id 를 NULL 로 남기는 것 외엔 할 수 없으므로 자동 통과.
drop policy if exists site_feedback_insert_any on public.site_feedback;
create policy site_feedback_insert_any on public.site_feedback for insert
  to anon, authenticated
  with check (user_id is null or user_id = auth.uid());

-- 원시 행 조회/수정/삭제는 관리자만 — 일반 방문자용 select 정책은 두지 않는다. 공개 목록은 아래
-- public_feedback() RPC 로만 나가며, 그 RPC 가 이미 전부(상태 무관) 보여주므로 "본인 행만 보기"
-- 정책이 따로 필요 없다(reports.sql 과 달리 여긴 본인에게만 더 보여줄 비공개 필드가 없다).
drop policy if exists site_feedback_admin_select on public.site_feedback;
drop policy if exists site_feedback_admin_update on public.site_feedback;
drop policy if exists site_feedback_admin_delete on public.site_feedback;
create policy site_feedback_admin_select on public.site_feedback for select
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));
create policy site_feedback_admin_update on public.site_feedback for update
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'))
  with check (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));
create policy site_feedback_admin_delete on public.site_feedback for delete
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));

-- 공개 피드백 피드(SECURITY DEFINER) — 상태 필터 없이 전부 공개(검수 대기열이 아니다).
-- 표시 이름: 로그인 작성자는 profiles.display_name, 없으면(또는 익명 작성자는) guest_name,
-- 그마저 없으면 '익명'. profiles.display_name 이 항상 guest_name 보다 우선이라, 만약 어떤 로그인
-- 사용자 행에 guest_name 이 섞여 들어와도(정상 UI 플로우에선 안 생김) 표시에는 영향이 없다.
create or replace function public.public_feedback(lim int default 50)
returns table(
  id uuid, category text, message text, status text, admin_reply text,
  created_at timestamptz, poster text
)
language sql
security definer
set search_path = public
stable
as $$
  select f.id, f.category, f.message, f.status, f.admin_reply, f.created_at,
         coalesce(nullif(trim(p.display_name),''), nullif(trim(f.guest_name),''), '익명') as poster
  from public.site_feedback f
  left join public.profiles p on p.id = f.user_id
  order by f.created_at desc
  limit greatest(1, least(coalesce(lim, 50), 200))
$$;

revoke all on function public.public_feedback(int) from public;
grant execute on function public.public_feedback(int) to anon, authenticated;

comment on table public.site_feedback is
  '사이트 자체 공개 피드백 게시판(버그·제안). anon+authenticated 모두 insert 가능. 조회는 public_feedback() RPC 로 전원 공개(비공개 필드 없음, 상태 무관). 관리자만 원시 행 조회/답변(update)/삭제(모더레이션).';
comment on function public.public_feedback(int) is
  '공개 피드백 피드 — 익명 작성자는 guest_name, 로그인 작성자는 profiles.display_name, 둘 다 없으면 익명으로 표시. 상태 필터 없음(검수 대기열이 아니라 즉시 공개 게시판이다).';
