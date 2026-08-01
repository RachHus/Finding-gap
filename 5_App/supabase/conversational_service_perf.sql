-- 대화형 도우미 성능·정확성 개선(chat v9):
--  (1) 전국 발견 롤업 MV(fg_species_national) — 전국(지역 미지정) 집계가 fg_species_region(590k)
--      전량 GROUP BY 대신 종별 사전집계(≈20k행)를 조회하도록 한다. CUTOFF(기준연도)는 앱에서
--      national_maxyear 로 판정하므로 MV 에는 굽지 않는다(연도 무관).
--  (2) 지역 한정 경로 커버링 인덱스 — where region/sido=X group by ktsn max(maxyear) 를 index-only 화.
-- 적용: Supabase SQL Editor 에서 실행(멱등). fg_species_region 재적재 후에는
--       load_reference.py 가 REFRESH MATERIALIZED VIEW 를 자동 수행한다.

create materialized view if not exists public.fg_species_national as
  select ktsn,
         max(maxyear) as national_maxyear,
         count(*)::int as recorded_regions,
         coalesce(sum(obs_count), 0)::bigint as total_obs
  from public.fg_species_region
  group by ktsn;

create unique index if not exists idx_fg_species_national_ktsn
  on public.fg_species_national (ktsn);

-- PostgREST 노출 차단(다른 fg_* 와 동일하게 익명/인증 역할 접근 회수). Edge Function 은 DB 직결.
revoke all on public.fg_species_national from anon, authenticated;

create index if not exists idx_fg_sr_region_ktsn_year
  on public.fg_species_region (region, ktsn, maxyear);
create index if not exists idx_fg_sr_sido_ktsn_year
  on public.fg_species_region (sido, ktsn, maxyear);
