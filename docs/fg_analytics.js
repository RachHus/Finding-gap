// GA4 게이트 로더 — window.GA4_ID(config.js 주입)가 있을 때만 gtag 로드. 없으면 무해 no-op(네트워크 0).
// 배포: build_dist.py 가 .env 의 GA4_MEASUREMENT_ID 를 config.js 의 window.GA4_ID 로 기록.
// 사용: 어디서든 window.fgTrack('event_name', {params}) — ID 없으면 조용히 무시.
//       화면이 바뀌는 곳에서는 window.fgPage(경로, 제목) — 아래 이유로 순위 집계는 이쪽만 쓸 수 있다.
//
// fgPage 를 따로 두는 이유: fgTrack 이 보내는 사용자 지정 매개변수(ktsn·taxon 등)는 GA4 가
// 수집은 하되 **관리자가 맞춤 측정기준으로 등록하기 전까지 어떤 보고서에도 뜨지 않고, 등록해도
// 소급되지 않는다.** 반면 page_view 의 페이지 경로·제목은 표준 측정기준이라 등록 없이 처음부터
// 보고서에 잡힌다. 종별 조회 순위처럼 "지금부터 쌓여야 하는" 집계는 가상 페이지뷰로 보낸다.
(function () {
  window.fgTrack = window.fgTrack || function () {};   // 기본 no-op — ID 없거나 로드 전 호출도 안전
  window.fgPage = window.fgPage || function () {};
  var id = window.GA4_ID;
  if (!id) return;                                     // 측정 ID 없으면 gtag 미로드(요청 0·쿠키 0)
  var s = document.createElement('script');
  s.async = true;
  s.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(id);
  document.head.appendChild(s);
  window.dataLayer = window.dataLayer || [];
  function gtag() { dataLayer.push(arguments); }
  window.gtag = gtag;
  gtag('js', new Date());
  gtag('config', id, { anonymize_ip: true });          // IP 익명화(개인정보 최소화)
  window.fgTrack = function (name, params) {
    try { gtag('event', name, params || {}); } catch (e) {}
  };
  // 한 페이지 안에서 화면만 바뀌는 구조라 실제 이동이 없다 → 가상 페이지뷰로 알린다.
  // path 는 현재 주소 기준 상대경로("?sp=120000053303" 등)로 받아 URL 로 해석한다. 배포본이
  // 하위 경로(/Finding-gap/)에 놓이므로 origin 에 직접 이어붙이면 어긋난다.
  window.fgPage = function (path, title) {
    try {
      gtag('event', 'page_view', {
        page_location: new URL(path || (location.pathname + location.search), location.href).href,
        page_title: title || document.title,
      });
    } catch (e) {}
  };
})();
