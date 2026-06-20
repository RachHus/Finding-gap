# -*- coding: utf-8 -*-
"""미매칭 조사종 → 정명 후보 자동 추천(사용자 검토·override 승격용).

배경: KTSN 마스터는 정명만, 별칭(ktsn_aliases)으로 변종/품종은 복원했으나, 그래도 남는 미매칭이 있다
  (옛 통합명·이표기·종분할·KTSN 미수록 등). 이 스크립트가 남은 미매칭 각각에 대해 마스터에서
  '그럴듯한 정명'을 자동 제안한다. 사람이 보고 맞으면 4_References/ktsn_name_overrides.csv 에 승격.

추천 근거:
  - 국명 부분일치: 미매칭 국명이 마스터 국명의 부분문자열(또는 그 역). 예 '꼬리치레도롱뇽' ⊂ '한국꼬리치레도롱뇽'.
  - 동일 속(genus): 미매칭 학명의 속명이 마스터에 존재 → 같은 속 종들 제안(종분할·재배치 단서).

입력: 1_Data/processed/observation_nps_unmatched.csv (etl_national_park 산출), ktsn_master.csv
출력: 1_Data/processed/observation_nps_unmatched_candidates.csv
  (종명, 분류명_국명, 생물분류, 사유, 폐기_건수, 후보근거, 후보_ktsn, 후보_국명, 후보_학명, 후보_분류군)
사용: python reconcile_unmatched.py
"""
import sys, csv, re
from pathlib import Path
from taxon_key import managed_key

BASE = Path(__file__).resolve().parents[2]
PROC = BASE / "1_Data" / "processed"
MASTER = PROC / "ktsn_master.csv"
UNMATCHED = PROC / "observation_nps_unmatched.csv"
OUT = PROC / "observation_nps_unmatched_candidates.csv"

MAX_CAND = 6          # 미매칭 1건당 후보 상한
MIN_KOR_LEN = 2       # 국명 부분일치 최소 길이(노이즈 방지)


def _kor(s):
    return re.sub(r"\s+", "", s or "")


def load_master():
    rows = []
    for r in csv.DictReader(MASTER.open(encoding="utf-8-sig")):
        rows.append({
            "ktsn": r["ktsn"],
            "kor": (r.get("korean_name") or "").strip(),
            "kor_n": _kor(r.get("korean_name")),
            "sci": (r.get("scientific_name") or "").strip(),
            "genus": (r.get("genus_la") or "").strip().lower(),
            "tx": r.get("taxon_group") or "",
        })
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not UNMATCHED.exists():
        sys.exit(f"{UNMATCHED.name} 없음 — etl_national_park.py 먼저 실행")

    master = load_master()
    by_genus = {}
    for m in master:
        if m["genus"]:
            by_genus.setdefault(m["genus"], []).append(m)
    # 국명 후보용: 길이순 정렬(짧은 마스터명이 긴 미매칭명에 포함되는 경우 빠른 탐색은 아니지만 단순 스캔)
    master_kor = [m for m in master if m["kor_n"]]

    unmatched = list(csv.DictReader(UNMATCHED.open(encoding="utf-8-sig")))
    out_rows = []
    n_with = 0

    for u in unmatched:
        jong = (u.get("종명") or "").strip()
        kn = (u.get("분류명_국명") or "").strip()
        cands, seen = [], set()

        # 1) 국명 부분일치 — 미매칭 국명(둘 중 한글이 있는 쪽)
        u_kor = _kor(kn) or (_kor(jong) if re.search(r"[가-힣]", jong) else "")
        if len(u_kor) >= MIN_KOR_LEN:
            for m in master_kor:
                mk = m["kor_n"]
                if len(mk) < MIN_KOR_LEN:
                    continue
                if (u_kor in mk) or (mk in u_kor):
                    if m["ktsn"] in seen:
                        continue
                    seen.add(m["ktsn"])
                    cands.append(("국명부분일치", m))
                    if len(cands) >= MAX_CAND:
                        break

        # 2) 동일 속(genus) — 미매칭 종명이 학명(2명법)일 때
        if len(cands) < MAX_CAND and re.search(r"[A-Za-z]", jong):
            toks = re.findall(r"[A-Za-z]+", jong)
            if toks:
                gen = toks[0].lower()
                for m in by_genus.get(gen, []):
                    if m["ktsn"] in seen:
                        continue
                    seen.add(m["ktsn"])
                    cands.append(("동일속", m))
                    if len(cands) >= MAX_CAND:
                        break

        if cands:
            n_with += 1
            for basis, m in cands:
                out_rows.append({
                    "종명": jong, "분류명_국명": kn, "생물분류": u.get("생물분류") or "",
                    "사유": u.get("사유") or "", "폐기_건수": u.get("폐기_건수") or "",
                    "후보근거": basis, "후보_ktsn": m["ktsn"], "후보_국명": m["kor"],
                    "후보_학명": m["sci"], "후보_분류군": m["tx"],
                })

    # 폐기 건수 내림차순(있을 때) — 큰 것부터 검토
    def _cnt(r):
        try:
            return int(r["폐기_건수"])
        except (ValueError, TypeError):
            return 0
    out_rows.sort(key=lambda r: -_cnt(r))

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["종명", "분류명_국명", "생물분류", "사유", "폐기_건수",
                                          "후보근거", "후보_ktsn", "후보_국명", "후보_학명", "후보_분류군"])
        w.writeheader()
        w.writerows(out_rows)

    print(f"미매칭 {len(unmatched):,}건 중 후보 있음 {n_with:,}건 / 없음 {len(unmatched)-n_with:,}건")
    print(f"→ {OUT.name} ({len(out_rows):,} 후보행) — 검토 후 맞는 항목을 ktsn_name_overrides.csv 로 승격하세요.")


if __name__ == "__main__":
    main()
