# -*- coding: utf-8 -*-
"""
종별 계절 적합성 산출 — observations.sqlite 의 obs_month 에서 "언제 보이는 종인가"를 뽑는다.

관측 기록의 월 분포를 그대로 쓰면 종의 계절성이 아니라 조사자의 계절성을 재게 된다.
조사는 여름 주간에 몰려서(곤충 자연환경조사 기준 7월 20.2% vs 12월 0.014%) 어떤 종이든
여름이 높게 나온다. 그래서 같은 조사 맥락에서 조사가 실제로 이루어진 달의 분포로 나눈다.

  점수(m) ∝ 기록수(m) / (배경비율(m) + FLOOR)

FLOOR 가 핵심이다. 그냥 배경으로 나누면 조사가 거의 없던 달(12월 배경은 7월의 0.0007배)에서
분모가 0 에 수렴해 값이 폭발한다 — 12월에 한 건 찍힌 종이 "12월이 최적기"가 되어버린다.
분모에 바닥을 깔면 조사가 없던 달은 "정보 없음"이 되어 점수가 오르지 않는다.
분자에는 상수를 더하지 않는다. 기록이 없는 달은 0 이어야 하며, 관찰 시기를 추천하는 값이므로
"자료가 없어서 모른다"가 "가 볼 만하다"로 새면 안 된다.

배경 단위는 (자료원 × 분류군). 같은 자연환경조사라도 곤충은 여름 주간에, 조류는 겨울까지
조사하므로 자료원만으로는 부족하다. 표본이 얇은 칸(BG_MIN 미만)은 분류군 단독으로 폴백한다.
종의 배경은 그 종이 실제로 기록된 자료원 구성비로 가중한다 — GBIF 위주로 기록된 종에
자연환경조사의 조사 계절을 씌우면 배경이 틀리기 때문이다.

출력: 1_Data/processed/species_season.csv  (ktsn, taxon_group, m01..m12, n_rec, bg_level)
      m01~m12 = 0~100 정수(최대 달이 100). 값이 클수록 그 달에 관찰될 가능성이 높다.
사용: python build_season.py
"""
import sys, csv, sqlite3, time
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
PROC = BASE / "1_Data" / "processed"
DB = PROC / "observations.sqlite"
OUT = PROC / "species_season.csv"

BG_MIN = 1000        # (자료원×분류군) 배경의 최소 기록 수 — 미만이면 분류군 단독으로 폴백
FLOOR = 0.15         # 배경 분모의 바닥. 조사 노력이 이보다 적은 달은 근거가 얇다고 보고 눌러 둔다
SMOOTH_UNDER = 30    # 기록이 이보다 적은 종은 인접 3개월 순환 평활(12↔1 로 이어짐)


def norm(v):
    """12개월 벡터를 합 1 로 정규화. 합이 0 이면 균등분포."""
    s = sum(v)
    return [x / s for x in v] if s > 0 else [1 / 12] * 12


def circular3(v):
    """인접 3개월 순환 이동평균 — 기록 한두 건이 한 달에 튀는 것을 완화한다."""
    return [(v[(i - 1) % 12] + v[i] + v[(i + 1) % 12]) / 3 for i in range(12)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    con = sqlite3.connect(DB)

    # 1) 배경: (자료원, 분류군) 별 월 분포 + 분류군 단독 폴백
    bg_st, bg_tx = defaultdict(lambda: [0] * 12), defaultdict(lambda: [0] * 12)
    for src, tx, m, n in con.execute(
            "SELECT source, taxon_group, month, SUM(n) FROM obs_month GROUP BY 1,2,3"):
        bg_st[(src, tx)][m - 1] += n
        bg_tx[tx][m - 1] += n
    thin = {k for k, v in bg_st.items() if sum(v) < BG_MIN}
    print(f"배경: (자료원×분류군) {len(bg_st)}칸 · 폴백 {len(thin)}칸  ({time.time()-t0:.1f}s)")

    bgn_st = {k: norm(v) for k, v in bg_st.items()}
    bgn_tx = {k: norm(v) for k, v in bg_tx.items()}

    def bg_of(src, tx):
        """그 조사 맥락에서 조사가 실제로 이루어진 달의 분포. 얇은 칸은 분류군 단독으로."""
        if (src, tx) in bgn_st and (src, tx) not in thin:
            return bgn_st[(src, tx)], "st"
        return bgn_tx.get(tx, [1 / 12] * 12), "tx"

    # 2) 종별: 월 분포 + 자료원 구성비(배경 가중치)
    sp_m = defaultdict(lambda: [0] * 12)              # ktsn → 12개월 기록 수
    sp_src = defaultdict(lambda: defaultdict(int))    # ktsn → 자료원 → 기록 수
    sp_tx = {}
    for ktsn, tx, src, m, n in con.execute(
            "SELECT ktsn, taxon_group, source, month, SUM(n) FROM obs_month GROUP BY 1,2,3,4"):
        sp_m[ktsn][m - 1] += n
        sp_src[ktsn][src] += n
        sp_tx[ktsn] = tx
    print(f"종: {len(sp_m):,}종 집계  ({time.time()-t0:.1f}s)")

    # 3) 조사 노력 보정 → 0~100
    rows, lv_cnt = [], defaultdict(int)
    for ktsn, mv in sp_m.items():
        tx = sp_tx[ktsn]
        N = sum(mv)
        srcs = sp_src[ktsn]
        tot = sum(srcs.values())

        # 종이 실제로 기록된 자료원 구성비로 배경을 섞는다
        bmix, lv = [0.0] * 12, set()
        for src, c in srcs.items():
            b, tag = bg_of(src, tx)
            lv.add(tag)
            w = c / tot
            for i in range(12):
                bmix[i] += w * b[i]
        bmix = norm(bmix)

        obs = circular3(mv) if N < SMOOTH_UNDER else list(mv)
        r = [obs[i] / (bmix[i] + FLOOR) for i in range(12)]

        mx = max(r)
        s12 = [round(100 * x / mx) for x in r] if mx > 0 else [0] * 12
        level = "st" if lv == {"st"} else ("tx" if lv == {"tx"} else "mix")
        lv_cnt[level] += 1
        rows.append([ktsn, tx] + s12 + [N, level])

    rows.sort(key=lambda x: (x[1], x[0]))
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ktsn", "taxon_group"] + [f"m{i:02d}" for i in range(1, 13)]
                   + ["n_rec", "bg_level"])
        w.writerows(rows)
    print(f"저장 {OUT.name}: {len(rows):,}종 · 배경수준 {dict(lv_cnt)}  ({time.time()-t0:.1f}s)")

    # 4) 타당성 점검 — 분류군별 최성기가 생태적으로 말이 되는지가 이 산식의 유일한 검증이다
    print("\n분류군별 최성기(종별 최고점 달의 최빈값):")
    peak = defaultdict(lambda: [0] * 12)
    for r in rows:
        s12 = r[2:14]
        peak[r[1]][s12.index(max(s12))] += 1
    for tx in sorted(peak):
        v = peak[tx]
        top = sorted(range(12), key=lambda i: -v[i])[:3]
        print(f"  [{tx}] " + " · ".join(f"{i+1}월 {v[i]}종" for i in top))
    con.close()


if __name__ == "__main__":
    main()
