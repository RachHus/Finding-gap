# 공유 정책 (개방 / 비개방)

이 저장소는 **public**(GitHub Pages로 서비스 공개)이다. 무엇이 올라가고(공유)
무엇이 빠지는지(제외)를 정의한다. 실제 적용은 `.gitignore` 가 담당하며, 본 문서는 그 의도를 사람이 읽기 위한 설명이다.

## ✅ 개방 (git 추적 → 공개)
- `README.md` · `SHARING.md`
- `3_ETL/` · `5_App/` — **소스 코드** (키 제외)
- `5_App/demo/data/*` — 서비스용 정적 산출 데이터
- `docs/` — GitHub Pages 빌드 산출(OSM 배경)
- `6_Deliverables/` — 계획서·다이어그램·배포 가이드
- `4_References/*.csv` — 코드 입력 매핑표(gbif_class_keys·ktsn_name_overrides)
- `*.env.example` · `config.example.js` — 키 **이름만** 담긴 템플릿(값 없음)

## 🚫 비개방 (git 제외 → 절대 push 안 됨)
| 대상 | 이유 |
|---|---|
| `.env`, `*.key`, `*.pem`, `secret*`, `credential*` | **API key·토큰** (보안) |
| `5_App/config.js` | vworld 클라이언트 키(빌드 시 `.env`에서 생성) |
| `1_Data/raw/`, `1_Data/processed/` | 원천·가공 데이터 (대용량·내부용) |
| `*.shp / *.dbf / *.zip` | 대용량 공간데이터 (GitHub 100MB 제한) |
| `4_References/*.pdf · *.docx · *.txt · *.xlsx` | 저작권 원문서·예시키 포함 참고자료 |
| `.claude/` · `2_Planning/` | AI 개발도구 설정 · 내부 기획문서(공개 제외, 로컬 보관) |
| `node_modules/`, `__pycache__/`, `**/dist/` | 빌드·캐시 산출물 |

## 🔑 비밀 관리 원칙 (public이라 특히 중요)
1. 실제 키는 **`.env`** 에만 — git에 절대 넣지 않는다.
2. 배포 시 키는 **플랫폼 환경변수**(Cloudflare·Netlify 설정창)에 입력.
3. 공유는 `.env.example` 의 항목만 → 각자 본인 키를 채워 사용.
4. ❗ 키를 실수로 커밋하면 **히스토리에 영구히 남으므로** 즉시 **폐기·재발급**한다.
   public 저장소는 봇이 즉시 키를 스캔하므로 더욱 위험하다.

## 🌐 공개 범위
- 이 저장소는 **누구나 열람·clone·fork** 가능하다(public). 서비스도 GitHub Pages URL로 공개된다.
- 배경지도는 키가 필요 없는 OSM 기본 — 공개 배포에 추가 비밀이 필요 없다.
- 외부에 숨겨야 할 자료(미공개 원천·운영키 등)가 생기면 → **별도 비공개 저장소**로 분리한다.
  (한 저장소 안 브랜치/폴더로는 가시성 분리 불가)
