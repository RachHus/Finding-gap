# 5_App/design — 디자인 시스템 (코드 단일 소스)

UI 디자인을 **코드에서 관리**한다. 디자인 토큰이 단일 소스이고, Figma/Penpot은 랜딩 비주얼 탐색용 보조다.

## 파일
| 파일 | 역할 |
|---|---|
| `tokens.json` | **단일 소스** — 색(적색목록·멸종위기·분류군)·라운드·간격. W3C Design Tokens 형식 |
| `tokens.css` | 런타임 CSS 변수 (프레임워크 무관, shadcn/ui 호환) |
| `tailwind.preset.cjs` | Tailwind 색/라운드 매핑 (`presets: [require('./design/tailwind.preset.cjs')]`) |
| `badges.tsx` | 희귀성 배지 컴포넌트 (RedListBadge·EndangeredBadge·TaxonTag) |

## 사용 (예)
```tsx
import { RedListBadge, EndangeredBadge, TaxonTag } from "@/design/badges";
<RedListBadge code="CR" />          // CR 위급
<EndangeredBadge level={1} />        // 멸종위기 I급
<TaxonTag taxon="bird" />            // ● 조류
```

## 권장 스택
- **Tailwind CSS + shadcn/ui**(컴포넌트 코드 소유) + **Storybook**(컴포넌트 카탈로그)
- 토큰 수정은 `tokens.json` → `tokens.css`/`tailwind.preset` 반영 (추후 Style Dictionary로 자동화 가능)

## Figma / Penpot 연동
- **단일 소스는 코드**. Figma/Penpot은 랜딩 등 비주얼 탐색만.
- 토큰을 Figma로 가져가려면: `tokens.json`을 **무료 플러그인(Tokens Studio / Variables Import)** 으로 임포트.
- Figma 무료(Starter)+View 좌석은 **편집 제한** → 디자인 편집은 본인 소유 draft에서만, 또는 Penpot(무제한 무료) 사용 권장.
- Figma Dev Mode MCP로 **디자인 → 코드** 추출은 가능(읽기). 디자인이 채워지면 그 화면을 코드로 변환 지원.

## 적색목록 코드(IUCN)
EX 절멸 · EW 야생절멸 · RE 지역절멸 · CR 위급 · EN 위기 · VU 취약 · NT 준위협 · LC 최소관심 · DD 정보부족 · NA 미적용 · NE 미평가  (위협등급 = CR·EN·VU)
