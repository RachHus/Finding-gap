"""분류 계층 자산 생성 — taxon_ko.js · taxon_tree.js

산출: 5_App/demo/data/taxon_ko.js    강·목·과·속 라틴명 → 한글명
      5_App/demo/data/taxon_tree.js  강 → 목 → 과 → 속 포함 관계
입력: 1_Data/processed/ktsn_master.csv (서비스가 다루는 종의 범위)
      1_Data/raw/nibr/ktsn_*.ndjson   (분류군 한글명의 유일한 출처)

화면에서 분류 계층을 "곤충강 Insecta" 처럼 한글과 학명을 나란히 보여주고, 검색창에
"밤나방과"나 "Noctuidae" 를 넣어도 그 아래 종이 나오게 하는 데 쓴다.

taxon_tree 는 포함 관계를 위에서 아래로 담는다(강→목, 목→과, 과→속). 검색은 이 방향
그대로 쓰고, 종에서 위로 거슬러 올라갈 때는 화면 쪽에서 뒤집어 쓴다. 같은 속명이 분류군에
따라 다른 과에 걸리는 경우가 있어, 다수와 어긋나는 종만 sp 에 ktsn 별로 따로 적는다.

같은 라틴명에 한글명이 여럿이면 가장 많이 쓰인 것을 고른다.

실행: python 5_App/build_taxon_assets.py — 손으로 따로 실행(run_pipeline.py 미포함)
배포: build_dist.py 의 DATA_FILES 에 두 파일 모두 포함
"""
import csv
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "5_App" / "demo" / "data"
NIBR = ROOT / "1_Data" / "raw" / "nibr"
MASTER = ROOT / "1_Data" / "processed" / "ktsn_master.csv"

# 자산 키 → (마스터 컬럼, ndjson 라틴명 필드, ndjson 한글명 필드)
RANKS = {
    "cls": ("class_la", "classKtsnLtnNm", "classKtsnKrnNm"),
    "ord": ("order_la", "orderKtsnLtnNm", "orderKtsnKrnNm"),
    "fam": ("family_la", "fmlyKtsnLtnNm", "fmlyKtsnKrnNm"),
    "gen": ("genus_la", "gnusKtsnLtnNm", "gnusKtsnKrnNm"),
}


def read_master():
    if not MASTER.exists():
        print(f"경고: 종 마스터 없음 — {MASTER}")
        return []
    return list(csv.DictReader(MASTER.open(encoding="utf-8-sig")))


def ndjson_records():
    for p in sorted(glob.glob(str(NIBR / "ktsn_*.ndjson"))):
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def korean_names(rows):
    """마스터에 등장하는 라틴명만 골라 라틴명 → 최빈 한글명."""
    wanted = {key: {r[col] for r in rows if r[col]} for key, (col, _, _) in RANKS.items()}
    tally = {key: {} for key in RANKS}
    for r in ndjson_records():
        for key, (_, lf, kf) in RANKS.items():
            la, ko = (r.get(lf) or "").strip(), (r.get(kf) or "").strip()
            if ko and la in wanted[key]:
                tally[key].setdefault(la, Counter())[ko] += 1
    names = {key: {la: c.most_common(1)[0][0] for la, c in sorted(t.items())}
             for key, t in tally.items()}
    return names, wanted


def containment(rows):
    """상위 → 하위 포함 관계와, 다수와 어긋나는 종의 과."""
    pair = {"co": defaultdict(Counter), "of": defaultdict(Counter), "fg": defaultdict(Counter)}
    for r in rows:
        c, o, f, g = r["class_la"], r["order_la"], r["family_la"], r["genus_la"]
        if o and c:
            pair["co"][o][c] += 1
        if f and o:
            pair["of"][f][o] += 1
        if g and f:
            pair["fg"][g][f] += 1
    up = {k: {child: cnt.most_common(1)[0][0] for child, cnt in d.items()} for k, d in pair.items()}
    tree = {}
    for k, d in up.items():
        down = defaultdict(list)
        for child, parent in d.items():
            down[parent].append(child)
        tree[k] = {parent: sorted(kids) for parent, kids in sorted(down.items())}
    tree["sp"] = {r["ktsn"]: r["family_la"] for r in rows
                  if r["genus_la"] and r["family_la"] and up["fg"].get(r["genus_la"]) != r["family_la"]}
    return tree


def write(path, var, payload):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(f"window.{var}=" + body + ";\n", encoding="utf-8")
    print(f"[출력] {path.relative_to(ROOT)} · {path.stat().st_size/1024:.0f} KB")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = read_master()
    if not rows:
        return 1
    names, wanted = korean_names(rows)
    tree = containment(rows)
    print("[taxon_ko] " + " · ".join(
        f"{key} {len(names[key])}/{len(wanted[key])}" for key in RANKS))
    print(f"[taxon_tree] 강→목 {len(tree['co'])} · 목→과 {len(tree['of'])} · "
          f"과→속 {len(tree['fg'])} · 종별 예외 {len(tree['sp'])}")
    DATA.mkdir(parents=True, exist_ok=True)
    write(DATA / "taxon_ko.js", "__TAXON_KO__", names)
    write(DATA / "taxon_tree.js", "__TAXON_TREE__", tree)
    if not any(names.values()):
        print("경고: 매핑이 비었습니다(ktsn ndjson 확인).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
