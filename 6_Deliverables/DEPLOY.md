# Finding gap — 외부 시범서비스 배포 가이드

대상: 외부 사용자가 접근 가능한 정적 시범서비스(대문 + 지도 서비스). 백엔드 불필요 — 순수 정적 호스팅.

## 0. 구성 요약
- `5_App/index.html` (대문) · `5_App/service.html` (서비스: 분류군별 조회 + 종별 검색)
- 데이터: `5_App/demo/data/*.js` (`obs_meta.js`+`obs_<T>.js` 분류군별 관측[서비스가 선택 분류군만 지연 로드], `species_index.js` 종 검색, `species_state.js` 대문 요약, `taxa_summary.js`, `sido.geojson`)
- 지도: **OSM(OpenStreetMap) 기본 배경** + (vworld 키가 그 도메인에 등록돼 있을 때만) vworld 상세지도 overlay. vworld 타일이 실패하면(도메인 미등록 등) 자동으로 OSM 폴백 → **외부 배포에서 키·도메인 등록 없이 즉시 배경지도 표시**. 클라이언트 키는 `config.js`(`.env`의 `VWORLD_KEY`에서 생성; 공개 파일럿은 `--osm-only`로 키 없이 빌드).
- 갱신주기: 6개월(원천 ETL 재실행 → `build_demo_data.py` → `build_dist.py` → 재배포)

## 1. 빌드 (배포본 조립)
```bash
# (데이터가 바뀌었다면) 정적 데이터 재생성
python 3_ETL/python/build_demo_data.py 2026-06-20

# 배포본(dist) 조립 → 6_Deliverables/dist/
python 5_App/build_dist.py --osm-only   # 공개 파일럿: vworld 키 없이 OSM 배경(권장)
# python 5_App/build_dist.py            # vworld 운영키를 그 도메인에 등록한 경우만(키 주입)
```
`6_Deliverables/dist/` 는 `.gitignore` 처리됨. `--osm-only` 빌드는 키가 없어 안전하지만 관례상 커밋하지 말 것.

## 2. 배포 — Cloudflare Pages (권장)

### 방법 A. CLI (wrangler)
```bash
npx wrangler pages deploy 6_Deliverables/dist --project-name finding-gap
```
- 최초 1회 `wrangler login` 브라우저 인증 필요(사용자 직접). 무료 플랜으로 충분.
- 배포 후 URL: `https://finding-gap.pages.dev` (프로젝트명 기준).

### 방법 B. 대시보드 드래그&드롭 (CLI 없이)
1. Cloudflare 대시보드 → Workers & Pages → Create → Pages → "Upload assets".
2. 프로젝트명 `finding-gap` 입력 → `6_Deliverables/dist/` 폴더 내용을 업로드.
3. 배포 완료 후 `*.pages.dev` URL 발급.

대안 호스팅: Netlify drop, GitHub Pages, Vercel(정적) 모두 동일 dist 폴더로 가능.

## 3. (선택) vworld 상세지도로 업그레이드 — 나중에
`--osm-only` 빌드는 OSM 배경으로 **도메인 등록 없이 바로 작동**하므로 외부 파일럿엔 추가 작업이 없습니다. 국내 상세지도(vworld)를 쓰고 싶을 때만:
1. vworld(`www.vworld.kr`) → **운영키** 신청(운영 도메인 확정 후; 개발키는 3개월 한시) → 해당 키의 **서비스 URL**에 배포 도메인 등록(예: `https://finding-gap.pages.dev`).
2. `5_App/.env` 의 `VWORLD_KEY` 를 그 운영키로 설정 → `python 5_App/build_dist.py`(--osm-only 빼고) → 재배포.
3. 그 도메인에서 vworld가 200을 주면 OSM 위에 자동 overlay. 실패하면 그대로 OSM 폴백(앱은 항상 작동). 키는 클라이언트 노출되므로 **도메인 잠금된 공개 전용 키**를 쓸 것.

## 4. 점검 체크리스트
- [ ] 배포 URL 접속 → 대문 로드, 분류군 타일 표시
- [ ] 서비스 → 분류군별 조회: OSM 배경 + 시도 choropleth 표시, 분류군 전환 동작
- [ ] 서비스 → 종별 검색: 검색 → 종 선택 → 지도 시도 강조 + 외부 링크(한반도 생물다양성/Naturing/EcoBank)
- [ ] 대용량 분류군(곤충류)에서 표 상한(1,500행) 안내 노출 + CSV 전체 다운로드

## 5. 알려진 제약 / 후속
- 서비스 초기 로드: `obs_meta.js`(~10KB)+선택 분류군 `obs_<T>.js`(기본 MM ~0.15MB)+`species_index.js`(3.8MB). 분류군 관측은 분류군별 분할·인덱스 인코딩으로 지연 로드(직전 40MB 통짜 제거; 전체 합 ~15MB이나 한 번에 한 분류군만 전송). 추가 여지: gzip(호스팅 기본 압축 ~1/4)·`species_index` 분할.
- MBRIS 해양종 API(B553482) 현재 500 응답 — 해양포유류 제외는 분류학적 식별(Cetacea·기각류·해우류 과)로 대체 적용. API 복구 시 `fetch_mbris.py`→`improve_species_list.py` 재실행으로 교차검증 가능.
