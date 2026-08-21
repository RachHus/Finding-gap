-- taxon_reference_reports 에 반려 사유(admin_note)를 추가 — reports_photo.sql 이 reports 에
-- 뒤늦게 photo_path 를 얹은 것과 같은 후속 ALTER 패턴. 제보자가 "반려됨"만 보고 왜인지 몰라
-- 답답해지는 걸 막으려고, 관리자가 반려할 때 이유를 한 줄 남길 수 있게 한다.
--
-- 적용: Supabase 대시보드 SQL Editor에서 이 파일 실행(taxon_reference_reports.sql 적용 후).

alter table public.taxon_reference_reports add column if not exists admin_note text;

comment on column public.taxon_reference_reports.admin_note is
  '관리자가 반려(또는 승인) 시 남기는 짧은 사유 — 제보자 본인 조회(RLS)에서만 노출.';
