// fg_supabase.js — Supabase 클라이언트 + 인증·관심종 헬퍼 (ES module)
// 설정값은 config.js(window.SUPABASE_URL/KEY, gitignore)에서 읽음. 미설정이면 configured=false 로 graceful 비활성.
// publishable 키는 공개 전제(RLS 보호). 데이터 접근 권한은 전적으로 Supabase RLS 정책이 통제.
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const URL = (window.SUPABASE_URL || '').trim();
const KEY = (window.SUPABASE_KEY || '').trim();
export const configured = !!(URL && KEY);
export const sb = configured ? createClient(URL, KEY) : null;

// ── 인증(이메일 매직링크) ──
export async function getUser() {
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session?.user || null;
}
export function onAuth(cb) {
  if (!sb) { cb(null); return; }
  sb.auth.getSession().then(({ data }) => cb(data.session?.user || null));
  // 두 번째 인자로 인증 이벤트 이름을 함께 넘긴다 — 새로 로그인한 것과 열어 둔 세션이 살아난 것을 구분해야 하는 쪽이 있다.
  sb.auth.onAuthStateChange((ev, sess) => cb(sess?.user || null, ev));
}
export async function sendMagicLink(email) {
  // 클릭 후 현재 페이지로 복귀(해당 URL 이 Supabase Auth Redirect URLs 에 등록돼 있어야 함)
  return sb.auth.signInWithOtp({ email, options: { emailRedirectTo: location.href.split('#')[0] } });
}
export async function signInWithGoogle() {
  // Google → Supabase 콜백 → 현재 페이지로 복귀(redirectTo 가 Auth Redirect URLs 에 등록돼 있어야 함)
  return sb.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: location.href.split('#')[0] } });
}
export async function signOut() { return sb?.auth.signOut(); }

// ── 관심 종(watchlist) — user_id 는 DB default auth.uid() 로 자동 채움 ──
export async function watchList() {
  if (!sb) return [];
  const { data, error } = await sb.from('watchlist').select('ktsn').order('created_at', { ascending: false });
  if (error) throw error;
  return (data || []).map(r => r.ktsn);
}
export async function watchAdd(ktsn) { return sb.from('watchlist').insert({ ktsn }); }
export async function watchRemove(ktsn) { return sb.from('watchlist').delete().eq('ktsn', ktsn); }

// ── 익명 관심종 집계(전체 사용자) — species_watch_counts() RPC ──
// 원시 watchlist 는 RLS(본인 행)로 보호되고, 이 RPC(SECURITY DEFINER)는 종별 집계 카운트만 반환(개인식별 불가).
// 마이그레이션: 5_App/supabase/species_watch_counts.sql. 미배포면 빈 배열.
export async function watchCounts() {
  if (!sb) return [];
  const { data, error } = await sb.rpc('species_watch_counts');
  if (error) throw error;
  return (data || []).map(r => ({ ktsn: r.ktsn, count: Number(r.watch_count) || 0 }))
                     .sort((a, b) => b.count - a.count);
}

// ── 알림 설정(활동 지역) — Auth user_metadata 에 둔다 ──
// 별도 표를 만들면 마이그레이션과 RLS 정책이 늘어나는데, 이 값은 본인만 읽고 쓰는 설정이라
// 세션과 함께 실려 오는 user_metadata 로 충분하다. 좌표가 아니라 시군구 코드만 담는다.
// 활동 지역은 여러 곳을 담을 수 있다. 예전에 한 곳만 고른 사용자는 목록이 없으므로 그 값을 목록으로 읽는다.
export function readProfile(user) {
  const m = (user && user.user_metadata) || {};
  const list = Array.isArray(m.fg_sggs) ? m.fg_sggs.filter(Boolean) : (m.fg_sgg ? [m.fg_sgg] : []);
  return { sgg: m.fg_sgg || list[0] || '', sggName: m.fg_sgg_name || '', sido: m.fg_sido || '',
           sggs: list, onboarded: !!m.fg_onboarded };
}
export async function saveProfile(p) {
  if (!sb) throw new Error('not configured');
  const list = Array.isArray(p.sggs) ? p.sggs.filter(Boolean) : (p.sgg ? [p.sgg] : []);
  const { data, error } = await sb.auth.updateUser({ data: {
    fg_sggs: list,
    // 목록 첫 곳은 대표 지역으로도 적어 둔다 — 한 곳만 읽던 자리가 그대로 동작한다.
    fg_sgg: list[0] || null, fg_sgg_name: p.sggName || null, fg_sido: p.sido || null, fg_onboarded: true
  } });
  if (error) throw error;
  return data ? data.user : null;
}

// ── 시민과학 제보(reports) — Feature B. 근거는 사진(권장) 또는 URL, 최소 하나 ──
// user_id 는 DB default auth.uid() 로 자동 채움. 정밀 좌표는 원시 행(본인 RLS)에만 저장.
// r = { ktsn, scientific_name, korean_name, taxon_group, url?, photo_path?, lat, lon, observed_date, note }
export async function submitReport(r) {
  if (!sb) throw new Error('not configured');
  return sb.from('reports').insert({
    ktsn: r.ktsn,
    scientific_name: r.scientific_name || null,
    korean_name: r.korean_name || null,
    taxon_group: r.taxon_group || null,
    url: r.url || null,
    photo_path: r.photo_path || null,
    lat: r.lat,
    lon: r.lon,
    observed_date: r.observed_date,
    note: (r.note && r.note.trim()) || null,
    /* sigungu·fills_gap 은 원래 "관리자 검토·배치에서 산정"으로 비워 뒀는데 그 배치가 없어서
       계속 NULL 이었다 — 그 결과 제보 리더보드의 '채운 공백'이 늘 0이고, approved_discoveries()
       는 sigungu is not null 조건 때문에 한 행도 안 돌려줬다. 제보하는 순간 브라우저가 두 값을
       다 알고 있으므로(시군구 경계는 지도에 이미 떠 있고, 발견 상태는 species_state 자산에 있다)
       여기서 실어 보낸다. 값은 호출자가 계산해 넘긴다 — 이 모듈은 지도·자산을 모르기 때문. */
    sigungu: (typeof r.sigungu === 'string' && /^\d{5}$/.test(r.sigungu)) ? r.sigungu : null,
    fills_gap: (typeof r.fills_gap === 'boolean') ? r.fills_gap : null
  });
}
// 내 제보 이력(본인 행 — RLS)
export async function myReports() {
  if (!sb) return [];
  const { data, error } = await sb.from('reports')
    .select('id,ktsn,korean_name,scientific_name,taxon_group,url,photo_path,lat,lon,observed_date,note,status,fills_gap,sigungu,created_at')
    .order('created_at', { ascending: false });
  if (error) throw error;
  return data || [];
}

// ── 제보 사진(Storage report-photos, 본인 폴더에만 업로드/삭제 · 읽기는 public) ──
// 마이그레이션: 5_App/supabase/reports_photo.sql. 미배포면 업로드 시 에러 반환(모달에서 URL로 폴백 안내).
export async function uploadReportPhoto(blob) {
  if (!sb) return { path: null, error: new Error('not configured') };
  const { data: { user } = {} } = await sb.auth.getUser();
  if (!user) return { path: null, error: new Error('로그인이 필요합니다') };
  const path = `${user.id}/${crypto.randomUUID()}.jpg`;
  const { error } = await sb.storage.from('report-photos').upload(path, blob, { contentType: 'image/jpeg' });
  return { path: error ? null : path, error };
}
export function reportPhotoUrl(path) {
  if (!sb || !path) return null;
  return sb.storage.from('report-photos').getPublicUrl(path).data.publicUrl;
}
export async function removeReportPhoto(path) {
  if (!sb || !path) return;
  return sb.storage.from('report-photos').remove([path]);
}
export async function deleteReport(id) { return sb.from('reports').delete().eq('id', id); }
// 공개 커뮤니티 피드 — community_reports() RPC(좌표 미노출·거부 제외). 미배포/미설정이면 빈 배열.
export async function communityReports(limit = 50) {
  if (!sb) return [];
  const { data, error } = await sb.rpc('community_reports', { lim: limit });
  if (error) throw error;
  return data || [];
}
// 리더보드 — report_leaderboard() RPC(제보자별 익명 집계: 제보 수·공백 메움 수)
export async function leaderboard(limit = 20) {
  if (!sb) return [];
  const { data, error } = await sb.rpc('report_leaderboard', { lim: limit });
  if (error) throw error;
  return (data || []).map(r => ({ reporter: r.reporter, reports: Number(r.reports) || 0, gaps: Number(r.gaps_filled) || 0 }));
}
// 리더보드에서 내 줄을 찾기 위한 표시 이름(profiles.display_name) — 본인 행만 RLS 로 보인다.
export async function myDisplayName() {
  if (!sb) return null;
  const { data } = await sb.from('profiles').select('display_name').maybeSingle();
  return data ? data.display_name : null;
}
// 내 역할(profiles.role) — 관리자 UI 게이트용. 비로그인/미설정이면 null.
export async function myRole() {
  if (!sb) return null;
  const { data } = await sb.from('profiles').select('role').maybeSingle();
  return data ? data.role : null;
}
// 관리자 전용 — RLS(role='admin')로 비관리자는 빈 결과. 검토 대기 제보 목록.
export async function adminPendingReports() {
  if (!sb) return [];
  const { data, error } = await sb.from('reports')
    .select('id,ktsn,korean_name,scientific_name,taxon_group,url,lat,lon,observed_date,note,status,fills_gap,sigungu,created_at')
    .eq('status', 'pending').order('created_at', { ascending: true });
  if (error) throw error;
  return data || [];
}
export async function setReportStatus(id, status) { return sb.from('reports').update({ status }).eq('id', id); }

// ── 분류 이력 전문가 제보(taxon_reference_reports) — 논문 근거(DOI) 기반. reports 와 완전히 같은 패턴 ──
// r = { ktsn, korean_name, scientific_name, to_name, ref_title, ref_authors?, ref_year?, ref_container?, doi?, ref_url?, note? }
export async function submitTaxonReference(r) {
  if (!sb) throw new Error('not configured');
  return sb.from('taxon_reference_reports').insert({
    ktsn: r.ktsn,
    korean_name: r.korean_name || null,
    scientific_name: r.scientific_name || null,
    to_name: r.to_name,
    ref_title: r.ref_title,
    ref_authors: r.ref_authors || null,
    ref_year: r.ref_year || null,
    ref_container: r.ref_container || null,
    doi: r.doi || null,
    ref_url: r.ref_url || null,
    note: (r.note && r.note.trim()) || null
  });
}
// 관리자 전용 — RLS(role='admin')로 비관리자는 빈 결과. 검토 대기 제보 목록.
export async function adminPendingTaxonRefs() {
  if (!sb) return [];
  const { data, error } = await sb.from('taxon_reference_reports')
    .select('id,ktsn,korean_name,scientific_name,to_name,ref_title,ref_authors,ref_year,ref_container,doi,ref_url,note,status,created_at')
    .eq('status', 'pending').order('created_at', { ascending: true });
  if (error) throw error;
  return data || [];
}
export async function setTaxonRefStatus(id, status, note) {
  return sb.from('taxon_reference_reports').update({ status, admin_note: (note && note.trim()) || null }).eq('id', id);
}
// 내 분류 이력 제보 이력(본인 행 — RLS). myReports() 와 동일한 패턴.
export async function myTaxonReferences() {
  if (!sb) return [];
  const { data, error } = await sb.from('taxon_reference_reports')
    .select('id,ktsn,korean_name,scientific_name,to_name,ref_title,ref_authors,ref_year,ref_container,doi,ref_url,note,status,admin_note,created_at')
    .order('created_at', { ascending: false });
  if (error) throw error;
  return data || [];
}

// ── 사이트 피드백 공개 게시판(site_feedback) — 이 앱 자체(버그·제안)에 대한 의견. 로그인 없이도
// 작성 가능(anon insert 허용, 이 파일에서 유일). user_id 는 로그인 시 DB default auth.uid() 로
// 자동 채워지고, 비로그인이면 NULL 로 남는다 — 그 경우 poster 표시는 guest_name 을 쓴다.
// f = { category?, message, guest_name? } — guest_name 은 비로그인일 때만 클라이언트가 채운다.
export async function submitFeedback(f) {
  if (!sb) throw new Error('not configured');
  return sb.from('site_feedback').insert({
    category: f.category || null,
    message: (f.message || '').trim(),
    guest_name: (f.guest_name && f.guest_name.trim()) || null
  });
}
// 공개 피드백 피드 — public_feedback() RPC(전원 공개, 상태 무관 — 검수 대기열이 아니라 즉시 공개 게시판).
export async function siteFeedback(limit = 50) {
  if (!sb) return [];
  const { data, error } = await sb.rpc('public_feedback', { lim: limit });
  if (error) throw error;
  return data || [];
}
// 관리자 전용 — RLS(role='admin')로 비관리자는 빈 결과. 답변 대기(open) 목록.
export async function adminPendingFeedback() {
  if (!sb) return [];
  const { data, error } = await sb.from('site_feedback')
    .select('id,category,message,guest_name,status,admin_reply,created_at')
    .eq('status', 'open').order('created_at', { ascending: true });
  if (error) throw error;
  return data || [];
}
export async function setFeedbackStatus(id, status, reply) {
  return sb.from('site_feedback').update({ status, admin_reply: (reply && reply.trim()) || null }).eq('id', id);
}
export async function deleteFeedback(id) { return sb.from('site_feedback').delete().eq('id', id); }
