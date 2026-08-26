-- permissions_hardening.sql — 일반 사용자가 자기 권한을 올리거나 확정된 자료를 지우지 못하게 막는다.
--
-- 왜 필요한가. 지금까지의 정책은 "본인 것만 손댈 수 있다"까지는 맞았지만, 본인 것 안에 손대면
-- 안 되는 것이 섞여 있었다.
--   ① profiles.role — 본인 행 update 가 열려 있어 자기 역할을 'admin' 으로 바꿀 수 있었다.
--      관리자 검토 큐는 이 값 하나로 열리므로, 사실상 누구나 남의 제보를 승인·거부할 수 있었다.
--   ② reports — 승인된 제보도 본인이 지울 수 있었다. 승인 제보는 이미 지역 클럽 리그 승점과
--      선수 순위, MCP 공개 스냅샷에 반영된 뒤라, 지우면 그 값들이 소리 없이 줄어든다.
--      검토를 통과한 자료는 개인 소유가 아니라 공동 자료로 넘어간 것으로 본다.
--   ③ Storage 사진 — 마찬가지로 승인된 제보의 사진을 지우면 공개 피드에 깨진 이미지가 남는다.
--
-- 되돌릴 여지는 남긴다. 검토 전(pending)이나 반려된(rejected) 제보는 본인이 지울 수 있다 —
-- 잘못 올렸을 때 물릴 길까지 막으면 제보 자체를 망설이게 된다.
--
-- 관리자 지정은 이 파일 맨 아래 주석의 SQL 로 대시보드에서 직접 한다. 아래 트리거는 앱을 통한
-- 변경만 막으므로(auth.uid() 가 있을 때만), SQL Editor·service_role 로는 그대로 지정된다.
--
-- 적용: Supabase 대시보드 SQL Editor 에 붙여넣고 실행(여러 번 실행해도 무해).
-- 소비: fg_supabase.js(myRole·deleteReport·removeReportPhoto) · index.html(관리자 검토 큐)

-- ── ① 역할은 본인이 못 바꾼다 ──────────────────────────────────────────
-- 컬럼 단위 권한으로 막는다. RLS 정책만으로는 "행은 되는데 이 칸은 안 된다"를 표현할 수 없다.
-- 앱은 profiles 를 읽기만 하므로(display_name·role) update 를 통째로 회수해도 지금 기능은 그대로다.
-- display_name 만 다시 열어 둔다 — 표시 이름을 바꾸는 화면이 생기면 이 권한이 필요하고,
-- role 과 달리 남에게 영향을 주지 않는다.
revoke update on public.profiles from authenticated, anon;
grant  update (display_name) on public.profiles to authenticated;

-- 컬럼 권한을 우회하는 경로(다른 클라이언트·향후 정책 변경)까지 막는 이중 잠금.
-- auth.uid() 가 null 인 경우(SQL Editor·service_role·백엔드)는 통과시킨다 — 관리자 지정 통로다.
create or replace function public.profiles_guard_role()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if new.role is distinct from old.role and auth.uid() is not null then
    raise exception '역할은 직접 바꿀 수 없습니다';
  end if;
  return new;
end $$;
drop trigger if exists profiles_no_self_role on public.profiles;
create trigger profiles_no_self_role before update on public.profiles
  for each row execute function public.profiles_guard_role();

-- ── ② 승인된 제보는 본인도 못 지운다 ───────────────────────────────────
drop policy if exists reports_delete_own on public.reports;
create policy reports_delete_own on public.reports for delete
  using (user_id = auth.uid() and status is distinct from 'approved');

-- ── ③ 승인된 제보의 사진도 못 지운다 ───────────────────────────────────
-- 경로(<user_id>/<uuid>.jpg)가 reports.photo_path 와 같은 문자열이라 그대로 맞대어 본다.
drop policy if exists report_photos_delete_own on storage.objects;
create policy report_photos_delete_own on storage.objects for delete to authenticated
  using (
    bucket_id = 'report-photos'
    and (storage.foldername(name))[1] = auth.uid()::text
    and not exists (
      select 1 from public.reports r
      where r.photo_path = storage.objects.name and r.status = 'approved')
  );

comment on function public.profiles_guard_role() is
  '앱(auth.uid() 있음)에서의 role 변경을 막는다. 관리자 지정은 SQL Editor·service_role 로만.';

-- ── 관리자 지정(대시보드에서 손으로) ───────────────────────────────────
-- update public.profiles set role = 'admin'
--   where id = (select id from auth.users where email = 'admin@example.com');
--
-- 해제:
-- update public.profiles set role = 'user'
--   where id = (select id from auth.users where email = 'admin@example.com');
--
-- 확인:
-- select p.id, u.email, p.display_name, p.role
--   from public.profiles p join auth.users u on u.id = p.id order by p.role desc, u.email;
