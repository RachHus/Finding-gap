# -*- coding: utf-8 -*-
"""
KTSN 종 마스터 정비 — 정명(corsynSeYn=Y)만, 종/아종 수준(최하위=아종, 변종은 상위로 폴드).
- 입력: 1_Data/raw/nibr/ktsn_*.ndjson (수집 산출)
- 조인: endangered_species.csv(등급) · national_redlist.csv(적색목록코드) — 학명키 기준
- 출력: 1_Data/processed/ktsn_master.csv
규칙:
- corsynSeYn=='Y' (정명) 레코드만.
- 관리 단위 = 속+종(+아종). 변종/품종(vrty)은 키에서 무시 → 종/아종으로 폴드.
- 같은 관리키에 정명이 여럿이면 '변종 아님·랭크 일치' 레코드 우선(canonical).
"""
import sys, csv, json, re
from pathlib import Path
from collections import defaultdict, Counter
from taxon_key import ktsn_keys, managed_key


def _kor(s):
    return re.sub(r"\s+", "", s or "")

BASE = Path(__file__).resolve().parents[2]
NIBR = BASE / "1_Data" / "raw" / "nibr"
PROC = BASE / "1_Data" / "processed"
ENDG = PROC / "endangered_species.csv"
REDL = PROC / "national_redlist.csv"
OUT  = PROC / "ktsn_master.csv"
ALIASES = PROC / "ktsn_aliases.csv"   # 정명으로 폴딩된 변종/품종/이표기 국명·학명 → 정명 ktsn(조사기록 매칭 복원용)

TAXA_KOR = {"MM":"포유류","AV":"조류","RP":"파충류","AM":"양서류","-P":"어류",
            "UC":"미삭동물","CC":"두삭동물","IV":"무척추동물(곤충제외)","IN":"곤충류",
            "VP":"관속식물","MS":"선태류"}


def load_lookup(path, sci_col, kor_col, val_col, val_name):
    """CSV → (학명키 dict, 국명 dict). 속명 재배치 대비 국명 폴백용."""
    sci, kor, rows = {}, {}, []
    if not path.exists():
        print(f"  (경고) {path.name} 없음 — {val_name} 조인 건너뜀")
        return sci, kor, rows
    for r in csv.DictReader(path.open(encoding="utf-8-sig")):
        v = (r.get(val_col) or "").strip()
        k = managed_key(r.get(sci_col) or "")
        if k and k not in sci:
            sci[k] = v
        kn = _kor(r.get(kor_col))
        if kn and kn not in kor:
            kor[kn] = v
        rows.append({"sci": k, "kor": kn, "val": v, "name": r.get(sci_col)})
    print(f"  {path.name}: {len(sci):,}학명키 / {len(kor):,}국명 ({val_name})")
    return sci, kor, rows


def canon_score(r, rank):
    vrty = (r.get("vrtyKtsnLtnNm") or "").strip()
    ss = (r.get("sspecsKtsnLtnNm") or "").strip()
    s = 0
    if not vrty:
        s += 2                                   # 변종 아닌 정식 종/아종 우선
    if rank == "종" and not ss:
        s += 1
    if rank == "아종" and ss:
        s += 1
    return s


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("조인 소스:")
    endg_sci, endg_kor, endg_rows = load_lookup(ENDG, "학명", "국명", "등급", "멸종위기등급")
    redl_sci, redl_kor, _ = load_lookup(REDL, "학명", "한글명", "적색목록코드", "적색목록")

    files = sorted(NIBR.glob("ktsn_*.ndjson"))
    if not files:
        sys.exit("KTSN NDJSON 없음 — fetch_nibr_ktsn.py all 먼저 실행")
    done = {p.stem.replace("ktsn_", "") for p in NIBR.glob("ktsn_*.done")}
    cand = defaultdict(list)          # managed_key → [정명 레코드…]
    n_all, n_acc = 0, 0
    for fp in files:
        for line in fp.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            n_all += 1
            if r.get("corsynSeYn") != "Y":        # 정명만
                continue
            binom, trinom = ktsn_keys(r.get("gnusKtsnLtnNm"), r.get("specsKtsnLtnNm"),
                                      r.get("sspecsKtsnLtnNm"))
            if not binom:                          # 속+종 미만(상위 분류군) 제외
                continue
            n_acc += 1
            key = trinom or binom
            cand[key].append(r)

    rows, per = [], defaultdict(lambda: [0, 0, 0])   # 분류군 → [종수, 멸종위기, 적색목록]
    rank_cnt = Counter()
    src = Counter()                                   # 조인 출처(학명/국명) 집계
    aliases, seen_alias = [], set()                   # 폴딩된 변종/품종 멤버 → 정명 ktsn 별칭
    for key, recs in cand.items():
        rank = "아종" if len(key.split()) == 3 else "종"
        rec = max(recs, key=lambda r: (canon_score(r, rank), -int(r.get("ktsn") or 0)))
        g = (rec.get("gnusKtsnLtnNm") or "").strip()
        sp = (rec.get("specsKtsnLtnNm") or "").strip()
        ss = (rec.get("sspecsKtsnLtnNm") or "").strip()
        sci = " ".join([g, sp] + ([ss] if (rank == "아종" and ss) else []))
        tx = rec.get("txgrpGroupCd") or ""
        kn = _kor(rec.get("ktsnKrnNm"))
        grade = endg_sci.get(key) or (endg_kor.get(kn, "") if kn else "")     # 학명→국명 폴백
        redcat = redl_sci.get(key) or (redl_kor.get(kn, "") if kn else "")
        if grade:
            src["멸종위기_학명" if key in endg_sci else "멸종위기_국명"] += 1
        if redcat:
            src["적색목록_학명" if key in redl_sci else "적색목록_국명"] += 1
        rows.append({
            "ktsn": rec.get("ktsn"), "scientific_name": sci, "match_key": key,
            "korean_name": rec.get("ktsnKrnNm") or "", "taxon_group": tx,
            "taxon_group_kor": TAXA_KOR.get(tx, tx), "rank": rank,
            "class_la": rec.get("classKtsnLtnNm") or "", "order_la": rec.get("orderKtsnLtnNm") or "",
            "family_la": rec.get("fmlyKtsnLtnNm") or "", "genus_la": g,
            "egspcs_yn": rec.get("egspcsYn") or "", "endangered_grade": grade,
            "national_redlist_category": redcat,
        })
        rank_cnt[rank] += 1
        per[tx][0] += 1
        if grade: per[tx][1] += 1
        if redcat: per[tx][2] += 1

        # 정명(rec)으로 폴딩된 다른 멤버(변종/품종/이표기)의 국명·학명을 별칭으로 — 조사기록이 옛 변종명을 써도 정명에 매칭
        canon_ktsn = rec.get("ktsn")
        for r2 in recs:
            if r2 is rec:
                continue
            a_kn = (r2.get("ktsnKrnNm") or "").strip()
            if a_kn and _kor(a_kn) != kn:
                tag = ("kor", _kor(a_kn), canon_ktsn)
                if tag not in seen_alias:
                    seen_alias.add(tag)
                    aliases.append({"alias_name": a_kn, "alias_type": "kor", "accepted_ktsn": canon_ktsn,
                                    "accepted_korean": rec.get("ktsnKrnNm") or "", "accepted_scientific": sci,
                                    "taxon_group": tx, "alias_rank": "변종/품종"})
            g2 = (r2.get("gnusKtsnLtnNm") or "").strip()
            sp2 = (r2.get("specsKtsnLtnNm") or "").strip()
            vr2 = (r2.get("vrtyKtsnLtnNm") or r2.get("sspecsKtsnLtnNm") or "").strip()
            a_sci = " ".join(x for x in (g2, sp2, vr2) if x)
            ak = managed_key(a_sci)
            if ak and ak != key:
                tag = ("sci", ak, canon_ktsn)
                if tag not in seen_alias:
                    seen_alias.add(tag)
                    aliases.append({"alias_name": a_sci, "alias_type": "sci", "accepted_ktsn": canon_ktsn,
                                    "accepted_korean": rec.get("ktsnKrnNm") or "", "accepted_scientific": sci,
                                    "taxon_group": tx, "alias_rank": "변종/품종"})

    rows.sort(key=lambda r: (r["taxon_group"], r["scientific_name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # 별칭 테이블 — 정명만 담긴 마스터를 보완(조사기록 매칭 복원). etl_*가 sci/kor 사전에 gap-fill로 흡수.
    master_kors = {_kor(r["korean_name"]) for r in rows if r["korean_name"]}
    master_keys = {r["match_key"] for r in rows}
    alias_out = [a for a in aliases
                 if (a["alias_type"] == "kor" and _kor(a["alias_name"]) not in master_kors)
                 or (a["alias_type"] == "sci" and managed_key(a["alias_name"]) not in master_keys)]
    with ALIASES.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["alias_name", "alias_type", "accepted_ktsn",
                                          "accepted_korean", "accepted_scientific", "taxon_group", "alias_rank"])
        w.writeheader(); w.writerows(alias_out)
    print(f"별칭(alias) 테이블: {ALIASES.name} — {len(alias_out):,}건 "
          f"(국명 {sum(1 for a in alias_out if a['alias_type']=='kor'):,} · 학명 {sum(1 for a in alias_out if a['alias_type']=='sci'):,})")

    incomplete = [c for c in TAXA_KOR if c not in done]
    print(f"\n총 레코드 {n_all:,} | 정명·종이상 {n_acc:,} | 관리 종/아종 {len(rows):,}")
    print(f"  랭크: {dict(rank_cnt)}")
    print(f"  멸종위기 태깅 {sum(p[1] for p in per.values()):,} | 적색목록 태깅 {sum(p[2] for p in per.values()):,}")
    print(f"  조인 출처: {dict(src)}")
    print("분류군별 (종/아종 · 멸종위기 · 적색목록):")
    for tx, (n, e, rl) in sorted(per.items(), key=lambda x: -x[1][0]):
        flag = "" if tx in done else "  ← 수집 미완(부분)"
        print(f"  {TAXA_KOR.get(tx, tx):16s}: {n:6,} · {e:4} · {rl:5}{flag}")
    if incomplete:
        print(f"\n⚠ 미완 분류군 {incomplete} — 수집 완료 후 재실행 시 확정.")
    print(f"\n→ {OUT}")
    # 멸종위기 282종 중 마스터 미반영(학명·국명 둘 다 미스) 점검
    msci = {r["match_key"] for r in rows}
    mkor = {_kor(r["korean_name"]) for r in rows}
    miss = [e for e in endg_rows if e["sci"] not in msci and e["kor"] not in mkor]
    print(f"멸종위기 {len(endg_rows)}종 중 마스터 미반영 {len(miss)}종 (대부분 미수집 분류군):")
    print("  예:", [e["name"] for e in miss[:8]])


if __name__ == "__main__":
    main()
