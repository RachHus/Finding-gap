-- 로그인 기반(profiles·watchlist) — 시민과학 P0 의 토대. 다른 마이그레이션이 전제하는 스키마.
-- 이 두 테이블은 대시보드에서 먼저 만들어져 리포에 파일이 없었다. 라이브와 글자 단위로
-- 같은 정의를 여기 남겨, 새 환경에서 처음부터 재현할 수 있게 한다(라이브에는 이미 있으므로 재실행해도 무해).
-- 원시 행은 전부 RLS 로 본인 것만 보인다 — 집계 노출은 species_watch_counts.sql 의 RPC 를 거친다.
-- 적용: Supabase 대시보드 SQL Editor 또는 MCP apply_migration 으로 실행.
-- 소비: fg_supabase.js(로그인·관심종·myRole) · reports.sql(관리자 정책이 profiles.role 참조) · build_watch_snapshot.py.

-- ── 프로필 — auth.users 1:1. 가입 시 트리거가 자동 생성한다(아래 handle_new_user) ──
create table if not exists public.profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  role         text not null default 'user',   -- 'user' | 'admin' (제보 검토 권한 게이트)
  created_at   timestamptz not null default now()
);

-- 대시보드에서 먼저 만든 환경(role 없음)을 위한 보정 — 신규 생성 시엔 no-op.
alter table public.profiles add column if not exists role text not null default 'user';

-- ── 관심 종 — 사용자×종. ktsn = 종 마스터 식별자(= NIBR species-detail id) ──
create table if not exists public.watchlist (
  user_id    uuid not null default auth.uid() references auth.users(id) on delete cascade,
  ktsn       text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, ktsn)
);

alter table public.profiles  enable row level security;
alter table public.watchlist enable row level security;

-- 본인 행만. profiles 는 가입 트리거(SECURITY DEFINER)가 넣으므로 insert 정책이 없다.
drop policy if exists profiles_select_own on public.profiles;
drop policy if exists profiles_update_own on public.profiles;
create policy profiles_select_own on public.profiles for select using (auth.uid() = id);
create policy profiles_update_own on public.profiles for update using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists watchlist_select_own on public.watchlist;
drop policy if exists watchlist_insert_own on public.watchlist;
drop policy if exists watchlist_delete_own on public.watchlist;
create policy watchlist_select_own on public.watchlist for select using (auth.uid() = user_id);
create policy watchlist_insert_own on public.watchlist for insert with check (auth.uid() = user_id);
create policy watchlist_delete_own on public.watchlist for delete using (auth.uid() = user_id);

-- ── 가입 시 프로필 자동 생성 ──
-- auth 스키마에는 일반 권한으로 쓸 수 없으므로 SECURITY DEFINER. 표시 이름은 OAuth 의 name,
-- 없으면 이메일 로컬파트. on conflict do nothing 이라 프로필이 이미 있으면 가입을 막지 않는다.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)))
  on conflict (id) do nothing;
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

comment on table public.profiles is
  '사용자 프로필(auth.users 1:1). role 은 관리자 UI·제보 검토 정책의 권한 게이트.';
comment on table public.watchlist is
  '사용자별 관심 종. 원시 행은 RLS 로 본인만 조회하며, 공개 노출은 종별 익명 집계(species_watch_counts)뿐.';
comment on function public.handle_new_user() is
  '가입(auth.users insert) 시 public.profiles 행을 자동 생성하는 트리거 함수.';
