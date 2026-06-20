# 5_App — 웹앱 (Next.js + Supabase)

미발견종 조회·종 검색·시도 지도·My data(제보)를 제공하는 프런트엔드/백엔드.

## 스택
- **Next.js** (App Router) — Vercel 무료 배포
- **Supabase** — Postgres + PostGIS + Auth(Google/Kakao/Naver) + RLS
- 지도: MapLibre/Leaflet + 시도경계 GeoJSON(`1_Data/spatial`에서 단순화)

## 시작 (구현 단계)
```bash
npx create-next-app@latest .
npm i @supabase/supabase-js
cp .env.example .env.local   # SUPABASE_URL / ANON_KEY 입력
npm run dev
```

## ⚠️ Google Drive 주의
이 폴더는 Drive 동기화 대상입니다. 다음은 **반드시 동기화/커밋 제외**:
- `node_modules/`, `.next/`, `.vercel/`, `.env*`

> 권장: 앱 소스는 Drive 밖(`C:\dev\finding-gap`) 또는 git 저장소에서 개발하고,
> 빌드 산출물·문서만 이 폴더에 반영. 루트 `.gitignore`가 위 항목을 이미 제외함.

## 데모 범위 (이번 주)
포유류(MM)+조류(AV) 1~2 분류군, 화면 ①미발견종 목록 ②종 검색→상세 ③시도 지도.
Auth·EcoBank·My data는 데모 이후 단계.
