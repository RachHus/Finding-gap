// Finding gap — 희귀성 배지 컴포넌트 (React/TSX)
// 의존성 없음(inline style). shadcn/ui 프로젝트에 그대로 복사해 사용.
// 토큰 단일 소스: design/tokens.json · design/tokens.css

import type { CSSProperties } from "react";

// ── 적색목록 평가범주 ──
export type RedListCode =
  | "EX" | "EW" | "RE" | "CR" | "EN" | "VU" | "NT" | "LC" | "DD" | "NA" | "NE";

const REDLIST: Record<RedListCode, { label: string; bg: string; fg: string }> = {
  EX: { label: "절멸",     bg: "#000000", fg: "#FFFFFF" },
  EW: { label: "야생절멸", bg: "#3D2645", fg: "#FFFFFF" },
  RE: { label: "지역절멸", bg: "#6B4E71", fg: "#FFFFFF" },
  CR: { label: "위급",     bg: "#D81E05", fg: "#FFFFFF" },
  EN: { label: "위기",     bg: "#FC7F3F", fg: "#4A1B0C" },
  VU: { label: "취약",     bg: "#F2DC00", fg: "#5C5300" },
  NT: { label: "준위협",   bg: "#C3D838", fg: "#3B4D00" },
  LC: { label: "최소관심", bg: "#5CB85C", fg: "#103D17" },
  DD: { label: "정보부족", bg: "#CFCFC4", fg: "#3F3F38" },
  NA: { label: "미적용",   bg: "#EAEAE2", fg: "#44443E" },
  NE: { label: "미평가",   bg: "#F7F7F4", fg: "#44443E" },
};

const pill: CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 4,
  padding: "2px 8px", borderRadius: 999, fontSize: 12, fontWeight: 500,
  lineHeight: 1.5, whiteSpace: "nowrap",
};

/** 적색목록 등급 배지. <RedListBadge code="CR" /> → "CR 위급" */
export function RedListBadge({ code, showLabel = true }: { code: RedListCode; showLabel?: boolean }) {
  const c = REDLIST[code] ?? REDLIST.NE;
  return (
    <span style={{ ...pill, background: c.bg, color: c.fg }} title={`${code} ${c.label}`}>
      <b style={{ fontWeight: 700 }}>{code}</b>{showLabel && <span>{c.label}</span>}
    </span>
  );
}

// ── 멸종위기 야생생물 등급 ──
export function EndangeredBadge({ level }: { level: 1 | 2 }) {
  const bg = level === 1 ? "#7F1D1D" : "#C2410C";
  return (
    <span style={{ ...pill, background: bg, color: "#FFFFFF" }}>
      멸종위기 {level === 1 ? "I급" : "II급"}
    </span>
  );
}

// ── 관리분류군 — 아이콘 칩 (./taxon-icons) ──
// 기존 색 점 → 채워진 실루엣 아이콘 칩으로 교체. TaxonChip을 TaxonTag로 재노출.
export type { TaxonKey } from "./taxon-icons";
export { TaxonChip as TaxonTag, TaxonIcon, TAXON_COLOR, TAXON_LABEL } from "./taxon-icons";

export { REDLIST };
