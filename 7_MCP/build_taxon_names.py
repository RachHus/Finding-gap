"""
분류 계층(강·목·과·속) 라틴↔한글 이름 매핑 자산 생성 — taxon_names.json.gz

대화형 도우미(Edge Function chat)의 fg_taxon_name 적재용 백엔드 참조 자산.
입력 자료: 1_Data/raw/nibr/ktsn_*.ndjson (ndjson 형식 KTSN 종 레코드들)
           각 레코드의 필드: classKtsnLtnNm/classKtsnKrnNm(강),
                          orderKtsnLtnNm/orderKtsnKrnNm(목),
                          fmlyKtsnLtnNm/fmlyKtsnKrnNm(과),
                          gnusKtsnLtnNm/gnusKtsnKrnNm(속)
매핑 규칙: 라틴명당 최빈 한글명 1개 채택 (Counter 기반).
산출: 7_MCP/data/taxon_names.json.gz
      구조: {"class":{라틴명:한글명}, "order":{...}, "family":{...}, "genus":{...}}
      크기: ~31KB (gzip 압축)

용도 비교:
  - taxon_names.json.gz: 모든 KTSN 분류군명(~40,156종의 분류 계층)
  - 5_App/js/taxon_ko.js(quiz용): 사진 보유 종만(scope 축소)

커밋 여부: 예 (git add 7_MCP/data/taxon_names.json.gz)

실행 시점:
  - KTSN ndjson 파일 갱신 시(분류체계 변경, 종명 수정 등)
  - build_mcp_data.py보다 선행 필요 없음 (독립적 자산).
  - 다만 chat 기능이 새로운 종명을 알아야 하면 먼저 실행.

사용:  python 7_MCP/build_taxon_names.py
반환값: 0(성공) / 1(오류: ndjson 없음 또는 매핑 비어있음)
"""
import glob
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NIBR = ROOT / "1_Data" / "raw" / "nibr"
OUT = Path(__file__).resolve().parent / "data" / "taxon_names.json.gz"

# rank → (라틴명 필드, 한글명 필드)
FIELDS = {
    "class": ("classKtsnLtnNm", "classKtsnKrnNm"),
    "order": ("orderKtsnLtnNm", "orderKtsnKrnNm"),
    "family": ("fmlyKtsnLtnNm", "fmlyKtsnKrnNm"),
    "genus": ("gnusKtsnLtnNm", "gnusKtsnKrnNm"),
}


def build():
    counters = {rank: {} for rank in FIELDS}
    files = glob.glob(str(NIBR / "ktsn_*.ndjson"))
    if not files:
        print(f"경고: KTSN ndjson 없음 — {NIBR}")
        return None
    for p in files:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            for rank, (lf, kf) in FIELDS.items():
                la = (r.get(lf) or "").strip()
                ko = (r.get(kf) or "").strip()
                if la and ko:
                    counters[rank].setdefault(la, Counter())[ko] += 1
    return {rank: {la: c.most_common(1)[0][0] for la, c in d.items()}
            for rank, d in counters.items()}


def main():
    maps = build()
    if maps is None:
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(maps, ensure_ascii=False, separators=(",", ":"))
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        f.write(body)
    total = sum(len(v) for v in maps.values())
    print("[taxon_names] " + " · ".join(f"{rank} {len(maps[rank])}" for rank in FIELDS))
    print(f"[출력] {OUT.relative_to(ROOT)} · {OUT.stat().st_size/1024:.1f} KB · 총 {total} 매핑")
    if not total:
        print("경고: 매핑이 비었습니다(ktsn ndjson 확인).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
