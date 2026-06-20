// Finding gap — 관리분류군 1~11 아이콘 (오리지널 채워진 실루엣)
// 아이콘은 fill="currentColor"(칩에서 흰색). 눈/구멍은 fill="var(--chip-bg)"로 칩 배경색을 받음.
import type { ReactNode, CSSProperties } from "react";

export type TaxonKey =
  | "mammal" | "bird" | "reptile" | "amphibian" | "fish" | "tunicate"
  | "cephalochordate" | "invertebrate" | "insect" | "vascular" | "bryophyte";

export const TAXON_COLOR: Record<TaxonKey, string> = {
  mammal: "#8B5E3C", bird: "#2F6FB0", reptile: "#4F8F3F", amphibian: "#3FA796",
  fish: "#2C7BA6", tunicate: "#9C6FB0", cephalochordate: "#B07FA0",
  invertebrate: "#C2667A", insect: "#D98C36", vascular: "#5C9A3A", bryophyte: "#7FA05C",
};

export const TAXON_LABEL: Record<TaxonKey, string> = {
  mammal: "포유류", bird: "조류", reptile: "파충류", amphibian: "양서류", fish: "어류",
  tunicate: "미삭동물", cephalochordate: "두삭동물", invertebrate: "무척추동물",
  insect: "곤충류", vascular: "관속식물", bryophyte: "선태류",
};

const stroke = { stroke: "currentColor", strokeWidth: 1, strokeLinecap: "round" as const, fill: "none" };

const PATHS: Record<TaxonKey, ReactNode> = {
  mammal: (<>
    <ellipse cx="7" cy="9.5" rx="1.7" ry="2.3" /><ellipse cx="11.2" cy="7.8" rx="1.7" ry="2.4" />
    <ellipse cx="15.4" cy="8" rx="1.7" ry="2.4" /><ellipse cx="18.7" cy="10.4" rx="1.6" ry="2.1" />
    <path d="M12.5 12.2c-3 0-5.5 2.1-6 4.5-.4 2 1.1 3.2 3.1 3 1-.1 2-.6 2.9-.6s1.9.5 2.9.6c2 .2 3.5-1 3.1-3-.5-2.4-3-4.5-6-4.5z" />
  </>),
  bird: (<>
    <ellipse cx="10.5" cy="13" rx="5.2" ry="3.5" transform="rotate(-16 10.5 13)" />
    <circle cx="15.8" cy="8.9" r="2.5" /><path d="M17.8 7.2l3.2-1-2 2.6z" /><path d="M5.3 14.8 2.5 17.6l3.6-.5z" />
    <path d="M8.8 16.6l-.7 2.6M11.4 16.8l-.3 2.5" {...stroke} strokeWidth={1.3} />
  </>),
  reptile: (<>
    <path d="M4.5 15.2c0-3.7 3.4-6.4 7.5-6.4s7.5 2.7 7.5 6.4c0 .6-.5 1.1-1.1 1.1H5.6c-.6 0-1.1-.5-1.1-1.1z" />
    <circle cx="20" cy="13.2" r="1.7" /><path d="M4 13.4 2 12.7l2-.8z" />
    <rect x="6.2" y="16" width="2.4" height="2.8" rx="1.2" /><rect x="15.4" y="16" width="2.4" height="2.8" rx="1.2" />
  </>),
  amphibian: (<>
    <path d="M12 3.6C9.9 3.6 8.4 5.2 8.4 7.1c0 .8.3 1.5.7 2C7.5 9.9 6.8 11.5 6.8 13.4c0 2.7 2.2 4.9 5.2 4.9s5.2-2.2 5.2-4.9c0-1.9-.7-3.5-2.3-4.3.4-.5.7-1.2.7-2C15.6 5.2 14.1 3.6 12 3.6z" />
    <path d="M9.1 8.4C7.6 7.4 5.9 6.2 4.7 5.8 4.2 5.6 3.8 6.1 4.1 6.6 5 8 6.7 9.6 8.5 10.2z" />
    <path d="M14.9 8.4c1.5-1 3.2-2.2 4.4-2.6.5-.2.9.3.6.8-.9 1.4-2.6 3-4.4 3.6z" />
    <path d="M10 12.9C7.8 13.2 5.6 14 4.9 15.6 4.4 17 4.3 18.8 4.5 20.2 4.5 20.7 4.9 21 5.4 21 6 21 6.4 20.6 6.5 20 6.7 18.6 6.9 17 7.5 15.9 8.1 14.9 9 14.1 10 13.8Z" />
    <path d="M14 12.9C16.2 13.2 18.4 14 19.1 15.6 19.6 17 19.7 18.8 19.5 20.2 19.5 20.7 19.1 21 18.6 21 18 21 17.6 20.6 17.5 20 17.3 18.6 17.1 17 16.5 15.9 15.9 14.9 15 14.1 14 13.8Z" />
    <circle cx="9.5" cy="4.8" r="1.7" /><circle cx="14.5" cy="4.8" r="1.7" />
    <path d="M4.4 5.9 3.3 5.1M4.4 5.9 3.4 6.5M4.4 5.9 4 4.7M19.6 5.9 20.7 5.1M19.6 5.9 20.6 6.5M19.6 5.9 20 4.7M4.8 20.6 4.3 21.7M5.5 20.9 5.4 22M6.2 20.6 6.7 21.7M19.2 20.6 19.7 21.7M18.5 20.9 18.6 22M17.8 20.6 17.3 21.7" {...stroke} />
    <circle cx="9.5" cy="4.8" r="0.7" fill="var(--chip-bg)" /><circle cx="14.5" cy="4.8" r="0.7" fill="var(--chip-bg)" />
  </>),
  fish: (<>
    <path d="M3 12c2.5-3.4 6.4-5 9.8-5 2.6 0 4.9 1.1 6.4 2.8l2.3-2.6v9.6l-2.3-2.6c-1.5 1.7-3.8 2.8-6.4 2.8-3.4 0-7.3-1.6-9.8-5z" />
    <circle cx="8.4" cy="11.6" r="1" fill="var(--chip-bg)" />
  </>),
  tunicate: (<>
    <path d="M7 20.5c-.9 0-1.5-.8-1.5-2.2C5.5 12.7 8.2 7.6 11 5.5c.6-.5 1-.7 1-.7s.4.2 1 .7c2.8 2.1 5.5 7.2 5.5 12.8 0 1.4-.6 2.2-1.5 2.2z" />
    <circle cx="9.7" cy="7.1" r="0.7" fill="var(--chip-bg)" /><circle cx="14.3" cy="7.1" r="0.7" fill="var(--chip-bg)" />
  </>),
  cephalochordate: (<>
    <path d="M2.5 12c5-2.6 14-2.6 19 0-5 2.6-14 2.6-19 0z" />
    <circle cx="5.2" cy="12" r="0.45" fill="var(--chip-bg)" />
  </>),
  invertebrate: (<>
    <path d="M3 17.5c0-1 .8-1.8 1.8-1.8h6.7c.6 0 1 .5 1 1.1 0 1.3-1.1 2.4-2.4 2.4H4.9C3.8 19.2 3 18.4 3 17.5z" />
    <circle cx="14.5" cy="11" r="5" /><circle cx="14.5" cy="11" r="1.7" fill="var(--chip-bg)" />
    <path d="M18.4 7.4l1.4-1.8M20 9l1.9-1" {...stroke} strokeWidth={1.5} />
  </>),
  insect: (<>
    <ellipse cx="7" cy="9.2" rx="4.2" ry="3.2" /><ellipse cx="17" cy="9.2" rx="4.2" ry="3.2" />
    <ellipse cx="7.8" cy="15" rx="3.4" ry="2.8" /><ellipse cx="16.2" cy="15" rx="3.4" ry="2.8" />
    <rect x="11.3" y="6.5" width="1.4" height="11" rx="0.7" />
    <path d="M12 6.6l-1.6-2M12 6.6l1.6-2" {...stroke} strokeWidth={1.2} />
  </>),
  vascular: (<>
    <path d="M4.5 19.5c-1.2-6.5 2.2-12.5 9.5-13.7 1.6-.3 3.2-.2 4.3.1.4 7.2-3.1 13.4-9.6 14.6-1.6.3-3.1 0-4.2-1z" />
    <path d="M4 20.2 6.4 18" {...stroke} strokeWidth={1.6} />
  </>),
  bryophyte: (<>
    <path d="M3 18.6c.8 0 1.2-1.5 2.4-1.5S6.6 18.6 7.8 18.6 9 17.1 10.2 17.1s1.2 1.5 2.4 1.5S13.8 17.1 15 17.1s1.2 1.5 2.4 1.5S18.6 17.1 19.8 17.1 21 18.6 21 18.6V20H3z" />
    <rect x="6.4" y="11" width="1.2" height="6" rx="0.6" /><ellipse cx="7" cy="10.4" rx="1.1" ry="1.6" />
    <rect x="11.4" y="9" width="1.2" height="8" rx="0.6" /><ellipse cx="12" cy="8.2" rx="1.1" ry="1.6" />
    <rect x="16.4" y="11.5" width="1.2" height="5.5" rx="0.6" /><ellipse cx="17" cy="10.9" rx="1.1" ry="1.6" />
  </>),
};

/** 분류군 아이콘 (SVG). 흰색 실루엣 — 색 칩 안에서 사용 권장. */
export function TaxonIcon({ taxon, size = 24 }: { taxon: TaxonKey; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor"
      style={{ ["--chip-bg" as any]: TAXON_COLOR[taxon] }} aria-label={TAXON_LABEL[taxon]} role="img">
      {PATHS[taxon]}
    </svg>
  );
}

/** 색 칩 + 흰색 아이콘 (+선택 라벨). */
export function TaxonChip({ taxon, showLabel = true, size = 28 }: { taxon: TaxonKey; showLabel?: boolean; size?: number }) {
  const box = size + 18;
  const chip: CSSProperties = {
    width: box, height: box, borderRadius: 12, background: TAXON_COLOR[taxon], color: "#fff",
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    ["--chip-bg" as any]: TAXON_COLOR[taxon],
  };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <span style={chip}><TaxonIcon taxon={taxon} size={size} /></span>
      {showLabel && <span style={{ fontSize: 13 }}>{TAXON_LABEL[taxon]}</span>}
    </span>
  );
}
