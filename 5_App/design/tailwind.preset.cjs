/* Finding gap Tailwind 프리셋 — 디자인 토큰을 Tailwind 색으로 노출.
   사용: tailwind.config 의 presets: [require('./design/tailwind.preset.cjs')] */
module.exports = {
  theme: {
    extend: {
      colors: {
        redlist: {
          ex: "#000000", ew: "#3D2645", re: "#6B4E71", cr: "#D81E05",
          en: "#FC7F3F", vu: "#F2DC00", nt: "#C3D838", lc: "#5CB85C",
          dd: "#CFCFC4", na: "#EAEAE2", ne: "#F7F7F4",
        },
        endangered: { 1: "#7F1D1D", 2: "#C2410C" },
        taxon: {
          mammal: "#8B5E3C", bird: "#2F6FB0", reptile: "#4F8F3F",
          amphibian: "#3FA796", fish: "#2C7BA6", tunicate: "#9C6FB0",
          cephalochordate: "#B07FA0", invertebrate: "#C2667A",
          insect: "#D98C36", vascular: "#5C9A3A", bryophyte: "#7FA05C",
        },
      },
      borderRadius: { sm: "6px", md: "8px", lg: "12px" },
    },
  },
};
