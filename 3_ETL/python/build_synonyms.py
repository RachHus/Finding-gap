# -*- coding: utf-8 -*-
"""KTSN 정명여부(corsynSeYn)=N 레코드 → 이명(synonym)→정명 매핑 테이블.

배경: KTSN 응답필드 corsynSeYn(정명여부)가 'N'이면 그 레코드 이름은 이명이고,
  specsKtsn(종_KTSN)이 정명 종을 가리킨다. 이를 alias 테이블로 뽑아 조사기록 매칭에 쓴다.

주의(실측 2026-06-20): 분류군별 검색(schTxgrpGroupCd=1~11)으로 받은 40,660건엔 N이 9건뿐이고
  대부분 specsKtsn이 자기 자신이라 사실상 이명 미수록. 의미있는 이명은 분류군 미지정 전수집
  (fetch_nibr_ktsn.py synall → ktsn_ALL.ndjson)에서 나올 가능성이 있어, 그 파일까지 함께 읽는다.
  → 이 스크립트는 ktsn_ALL.ndjson 유무와 무관하게 동작하며, N 레코드가 늘면 자동으로 더 많은 이명을 산출.

입력: 1_Data/raw/nibr/ktsn_*.ndjson (ktsn_ALL.ndjson 포함 시 자동 합산), ktsn_master.csv
출력: 1_Data/processed/ktsn_synonyms.csv
  (alias_name, alias_type[kor|sci], accepted_ktsn, accepted_korean, accepted_scientific,
   taxon_group, alias_rank=corsyn, source=ktsn_corsyn)
  컬럼은 ktsn_aliases.csv 와 동일(+source) → name_overrides.load_aliases()가 합쳐 쓸 수 있음.
사용: python build_synonyms.py
"""
import sys, csv, json, re, glob
from pathlib import Path
from taxon_key import managed_key

BASE = Path(__file__).resolve().parents[2]
NIBR = BASE / "1_Data" / "raw" / "nibr"
PROC = BASE / "1_Data" / "processed"
MASTER = PROC / "ktsn_master.csv"
OUT = PROC / "ktsn_synonyms.csv"


def _kor(s):
    return re.sub(r"\s+", "", s or "")


def load_master():
    """ktsn → (korean_name, scientific_name, taxon_group). 정명 해석·검증용."""
    m = {}
    for r in csv.DictReader(MASTER.open(encoding="utf-8-sig")):
        m[str(r["ktsn"])] = (
            (r.get("korean_name") or "").strip(),
            (r.get("scientific_name") or "").strip(),
            r.get("taxon_group") or "",
        )
    return m


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not MASTER.exists():
        sys.exit("ktsn_master.csv 없음 — build_ktsn_master.py 먼저 실행")
    master = load_master()

    files = sorted(glob.glob(str(NIBR / "ktsn_*.ndjson")))
    n_n = n_self = n_no_master = 0
    rows = []
    seen = set()
    for fp in files:
        for line in Path(fp).open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("corsynSeYn") != "N":
                continue
            n_n += 1
            own = str(r.get("ktsn"))
            acc = str(r.get("specsKtsn") or "")
            if not acc or acc == own:          # 자기참조 = 이명 매핑 아님
                n_self += 1
                continue
            if acc not in master:              # 정명이 마스터(서비스 대상)에 없음
                n_no_master += 1
                continue
            acc_kor, acc_sci, tx = master[acc]
            # 이명 국명
            syn_kor = _kor(r.get("ktsnKrnNm"))
            if syn_kor and (syn_kor, acc) not in seen and syn_kor != _kor(acc_kor):
                seen.add((syn_kor, acc))
                rows.append({"alias_name": (r.get("ktsnKrnNm") or "").strip(), "alias_type": "kor",
                             "accepted_ktsn": acc, "accepted_korean": acc_kor,
                             "accepted_scientific": acc_sci, "taxon_group": tx,
                             "alias_rank": "corsyn", "source": "ktsn_corsyn"})
            # 이명 학명(속+종소명 정규화키 → 원학명 stnm 앞 두 토큰)
            syn_mk = managed_key(r.get("stnm") or "")
            if syn_mk and (syn_mk, acc) not in seen and syn_mk != managed_key(acc_sci):
                seen.add((syn_mk, acc))
                rows.append({"alias_name": (r.get("stnm") or "").strip(), "alias_type": "sci",
                             "accepted_ktsn": acc, "accepted_korean": acc_kor,
                             "accepted_scientific": acc_sci, "taxon_group": tx,
                             "alias_rank": "corsyn", "source": "ktsn_corsyn"})

    rows.sort(key=lambda r: (r["taxon_group"], r["accepted_ktsn"], r["alias_type"]))
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["alias_name", "alias_type", "accepted_ktsn",
                                          "accepted_korean", "accepted_scientific",
                                          "taxon_group", "alias_rank", "source"])
        w.writeheader(); w.writerows(rows)

    has_all = (NIBR / "ktsn_ALL.ndjson").exists()
    print(f"이명(corsynSeYn=N) 총 {n_n:,}건 | 자기참조 제외 {n_self:,} · 정명 마스터부재 {n_no_master:,}")
    print(f"→ {OUT.name}: 유효 이명 {len(rows):,}행 (국명 {sum(1 for r in rows if r['alias_type']=='kor'):,} · "
          f"학명 {sum(1 for r in rows if r['alias_type']=='sci'):,})")
    if not has_all:
        print("  주의: ktsn_ALL.ndjson 없음 — 분류군별 데이터만 반영(이명 거의 없음).")
        print("        이명을 제대로 받으려면: python fetch_nibr_ktsn.py synprobe → (N 확인 시) synall")
    if not rows:
        print("  현재 데이터에 유효 이명 0 — API 분류군검색은 정명만 반환함을 재확인.")


if __name__ == "__main__":
    main()
