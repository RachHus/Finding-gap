# Finding gap — 배포 가이드

외부 사용자가 접근 가능한 발견공백 서비스를 배포한다. 정적 조회 화면과 동적 기능(로그인·제보·대화형 도우미)으로 나뉜다.

## 0. 서비스 구성

### 정적 조회 화면 (호스팅만 필요)
조회 기능만 필요하면 이 부분만 배포한다.
- **주소:** index.html(대문) · service.html(지도 서비스: 분류군별/종별 조회) · quiz.html(동정 연습)
- **데이터:** `demo/data/*.js`
  - 관측: `obs_<분류군코드>.js` (지연 로드)
  - 종 정보: `species_index.js`(종 검색), `species_state.js`(대문 요약)
  - 집계: `taxa_summary.js`, `region_gaps.js`
  - 지역 경계: `sido.geojson`, `sigungu.geojson`
  - 서식지 후보 모형: `model_<분류군코드>.js`, `env_model.js`, `env_grid.js` (지연 로드)
  - 시민과학: `missions.js`(미션 보드, 정적), `species_env.js`(뒷받침 환경 데이터)
- **지도 배경:** OSM(OpenStreetMap) 기본 배경 사용. vworld 키가 그 도메인에 등록돼 있으면 상세지도 overlay되고, 실패하면 자동으로 OSM 폴백. 키 없이도 OSM만으로 작동하므로 외부 배포에서 추가 설정 없이 즉시 표시.

### 동적 기능 (Supabase 필요)
로그인, 관심종 저장, 발견 제보, 대화형 도우미 등 사용자 기능.
- **인증:** Supabase Auth (이메일 매직링크 + Google OAuth)
- **데이터 저장:** Supabase Postgres (행 수준 보안)
- **대화형 도우미:** Supabase Edge Function(chat) + Gemini 모델
- 스키마(SQL) 적용 순서와 보안 정책은 `5_App/supabase/README.md` 참고
- 대화형 도우미 Edge Function 설정은 `5_App/supabase/functions/chat/README.md` 참고

### 갱신주기
정적 자산: 6개월마다 원천 ETL 재실행 → `build_demo_data.py` → `build_dist.py` → 재배포  
참조 데이터(종 마스터, 적색목록): 필요에 따라 별도 갱신

## 1. 정적 조회 화면 배포 준비

### 1-1. 빌드 (배포본 조립)
```bash
# 데이터가 바뀌었다면 정적 자산 재생성
python 3_ETL/python/build_demo_data.py 2026-06-20

# 배포본 조립 → 6_Deliverables/dist/ (또는 docs/)
python 5_App/build_dist.py --osm-only   # 기본: vworld 키 없이 OSM만 사용
# python 5_App/build_dist.py             # vworld 운영키가 도메인에 등록된 경우
```
- `--osm-only`: Supabase 및 chat 기능 미포함(정적 조회만). 외부 배포 권장.
- `--out docs`: GitHub Pages(`main/docs/`) 대상. 기본값은 `6_Deliverables/dist/`.
- `.gitignore` 처리: `dist/` 폴더는 원본 소스로 남기지 않음.

`build_dist.py`는 다음 항목들을 조립한다:
- HTML: index.html, service.html, quiz.html, chat.html
- 설정: config.js (환경변수에서 생성)
- 지역/분류군 프로필 페이지(SEO): `build_profiles.py` 산출물
- 캐시 헤더: `_headers` 파일 (Cloudflare Pages용)

### 1-2. 호스팅 선택
Cloudflare Pages, GitHub Pages, Netlify 등 정적 호스팅 모두 가능.

#### Cloudflare Pages (권장)
```bash
npx wrangler pages deploy 6_Deliverables/dist --project-name finding-gap
```
- 최초 1회 `wrangler login` 으로 인증 (사용자 직접).
- 배포 후 URL: `https://finding-gap.pages.dev`.
- 무료 플랜으로 충분.
- `_headers` 파일이 자동 적용되어 캐시·보안 헤더 설정 완료.

#### GitHub Pages
```bash
python 5_App/build_dist.py --osm-only --out docs
# git commit && git push
```
- `main` 브랜치의 `docs/` 폴더에서 자동 배포.
- URL: `https://<username>.github.io/Finding-gap/`.

#### Netlify
- 대시보드에서 `dist/` 폴더 드래그&드롭.

### 1-3. (선택) vworld 상세지도 추가
`--osm-only` 빌드는 OSM만 사용하므로 추가 설정 없이 바로 작동한다. 국내 상세지도를 추가하려면:
1. vworld(`www.vworld.kr`) → 운영키 신청(개발키는 3개월 한시).
2. 배포 도메인을 키의 서비스 URL에 등록.
3. `5_App/.env`에 `VWORLD_KEY=<운영키>` 설정.
4. `python 5_App/build_dist.py` 실행 (--osm-only 빼고).
5. 재배포.

vworld가 실패하면 자동으로 OSM 폴백. 키는 도메인 잠금된 공개 전용 키를 사용할 것.

## 2. 동적 기능 배포 (선택 사항)

로그인, 관심종, 발견 제보, 대화형 도우미를 활성화하려면 Supabase 설정이 필요하다.

### 2-1. Supabase 프로젝트 생성
1. Supabase 대시보드에서 새 프로젝트 생성.
2. 데이터베이스 URL · Publishable Key 확인.

### 2-2. 스키마 및 참조 데이터 적용
```bash
python 5_App/supabase/load_reference.py
```
SQL 파일을 어떤 순서로 적용하는지, 각 파일이 무엇을 만드는지는 `5_App/supabase/README.md` 참고.

### 2-3. Edge Function 배포
```bash
supabase functions deploy chat
```
Gemini API 키를 미리 설정할 것 (`supabase secrets set GEMINI_API_KEY=...`).

### 2-4. 프런트 활성화
```bash
# .env에 추가
SUPABASE_URL=<프로젝트URL>
SUPABASE_KEY=<publishable키>
CHAT_ENABLED=1

# 재빌드 및 배포
python 5_App/build_dist.py --osm-only
```

## 3. 점검 체크리스트

- [ ] 배포 URL 접속 → 대문 로드, 분류군 타일 표시
- [ ] 서비스 → 분류군별 조회: OSM 배경 + 시도 choropleth 표시, 분류군 전환 동작
- [ ] 서비스 → 종별 검색: 검색 → 종 선택 → 지도 시도 강조 + 외부 링크(NIBR/EcoBank)
- [ ] 대용량 분류군(곤충류)에서 표 상한(1,500행) 안내 + CSV 다운로드
- [ ] (동적 기능 배포 시) 로그인 → Google OAuth 동작, 관심종 저장 동작
- [ ] (동적 기능 배포 시) 발견 제보 → 사진 업로드 및 위치 자동입력
- [ ] (동적 기능 배포 시) 대화형 도우미 → 질문에 응답, 지도 링크 동작

## 4. 알려진 제약 및 성능 고려사항

### 초기 로드 성능
- `obs_meta.js`(~10KB) + 선택 분류군 `obs_<T>.js`(~0.15MB) + `species_index.js`(3.8MB)를 순차 로드.
- 분류군별 분할 + 인덱스 인코딩으로 지연 로드 적용(이전 통짜 40MB 제거).
- 전체 자산 ~15MB이나 한 번에 한 분류군만 전송.
- 호스팅 gzip 압축 시 ~1/4 크기로 감소.

### 외부 API 상태
- MBRIS 해양종 정보 API: 현재 500 응답. 임시로 분류학적 식별(Cetacea·기각류·해우류 과)로 대체.
- API 복구 시 `fetch_mbris.py` → `improve_species_list.py` 재실행으로 데이터 갱신 가능.

### 자세한 문서
- 정적 자산 생성: `3_ETL/DATA_PIPELINE.md`
- Supabase 스키마·적용 순서: `5_App/supabase/README.md`
- 대화형 도우미 Edge Function: `5_App/supabase/functions/chat/README.md`
