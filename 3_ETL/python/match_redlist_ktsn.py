# -*- coding: utf-8 -*-
"""
적색목록(national_redlist.csv) 학명을 KTSN 마스터에 매칭 → national_redlist_category 결합.
- KTSN 마스터: 1_Data/raw/nibr/ktsn_*.ndjson (fetch_nibr_ktsn.py 산출)
- 매칭: 학명 정규화(속+종, 괄호·저자 제거). 아종/변종은 3명법 우선, 없으면 2명법.
- 정명(corsynSeYn=='Y') 우선 선택. 출력: 매칭표 + 미매칭표 + 매칭률 리포트.
"""
import sys, csv, json, re
from pathlib import Path
from collections import defaultdict, Counter

BASE = Path(__file__).resolve().parents[2]
NIBR = BASE / "1_Data" / "raw" / "nibr"
REDLIST   = BASE / "1_Data" / "processed" / "national_redlist.csv"
OUT       = BASE / "1_Data" / "processed" / "redlist_ktsn_matched.csv"
UNMATCHED = BASE / "1_Data" / "processed" / "redlist_unmatched.csv"

def norm(s):
    s = re.sub(r"\([^)]*\)", " ", s or "")           # 괄호(저자/아속) 제거
    toks = [t for t in re.split(r"\s+", s) if re.match(r"^[A-Za-z]", t)]
    return [t.lower() for t in toks]

def binom(tk):  return " ".join(tk[:2]) if len(tk) >= 2 else ""
def trinom(tk): return " ".join(tk[:3]) if len(tk) >= 3 else ""

def load_ktsn():
    bi, tri, n = defaultdict(list), defaultdict(list), 0
    files = sorted(NIBR.glob("ktsn_*.ndjson"))
    if not files:
        sys.exit("KTSN NDJSON 없음 — 먼저 fetch_nibr_ktsn.py all 실행 필요")
    for fp in files:
        for line in fp.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            n += 1
            g  = (r.get("gnusKtsnLtnNm") or "").strip().lower()
            sp = (r.get("specsKtsnLtnNm") or "").strip().lower()
            ss = (r.get("sspecsKtsnLtnNm") or "").strip().lower()
            vr = (r.get("vrtyKtsnLtnNm") or "").strip().lower()
            rec = {"ktsn": r.get("ktsn"), "stnm": r.get("stnm"),
                   "kor": r.get("ktsnKrnNm"), "acc": r.get("corsynSeYn"),
                   "txgrp": r.get("txgrpGroupCd")}
            if g and sp:
                bi[f"{g} {sp}"].append(rec)
                if ss: tri[f"{g} {sp} {ss}"].append(rec)
                if vr: tri[f"{g} {sp} {vr}"].append(rec)
            else:
                tk = norm(r.get("stnm"))
                if len(tk) >= 2:
                    bi[binom(tk)].append(rec)
    return bi, tri, n

def pick(cands):
    acc = [c for c in cands if c.get("acc") == "Y"]
    return (acc[0] if acc else cands[0]), len(cands)

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    bi, tri, n = load_ktsn()
    print(f"KTSN 레코드 {n:,} | binomial키 {len(bi):,} | trinomial키 {len(tri):,}")

    rows = list(csv.DictReader(REDLIST.open(encoding="utf-8-sig")))
    out, per = [], defaultdict(lambda: [0, 0])
    for row in rows:
        tk = norm(row["학명"]); b, t = binom(tk), trinom(tk)
        rec, mtype, ncand = None, "none", 0
        if t and t in tri:
            rec, ncand = pick(tri[t]); mtype = "trinomial"
        elif b and b in bi:
            rec, ncand = pick(bi[b]); mtype = "binomial"
        tx = row["분류군명"]; per[tx][1] += 1
        if rec: per[tx][0] += 1
        out.append({**row,
                    "ktsn": rec["ktsn"] if rec else "",
                    "ktsn_stnm": rec["stnm"] if rec else "",
                    "ktsn_kor": rec["kor"] if rec else "",
                    "ktsn_accepted": rec["acc"] if rec else "",
                    "match_type": mtype, "n_candidates": ncand})

    fields = list(rows[0].keys()) + ["ktsn", "ktsn_stnm", "ktsn_kor",
                                     "ktsn_accepted", "match_type", "n_candidates"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(out)
    un = [o for o in out if not o["ktsn"]]
    with UNMATCHED.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(un)

    m = len(out) - len(un)
    print(f"\n매칭률 전체: {m:,}/{len(out):,} = {m/len(out)*100:.1f}%")
    print("분류군별:")
    for tx, (mm, tt) in sorted(per.items(), key=lambda x: -x[1][1]):
        print(f"  {tx:10s}: {mm:5,}/{tt:5,} = {mm/tt*100:5.1f}%")
    print("match_type:", dict(Counter(o["match_type"] for o in out)))
    print(f"\n미매칭 {len(un):,}건 → {UNMATCHED.name}")
    for o in un[:12]:
        print("  -", o["분류군명"], "|", o["학명"], "|", o["한글명"])

if __name__ == "__main__":
    main()
