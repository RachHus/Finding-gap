# -*- coding: utf-8 -*-
"""
관찰 추천도 클라이언트 자산 빌드 — 공간 축(maxnet 계수) + 계절 축(월별 점수).

입력 : 1_Data/processed/{model_store/<T>.json, species_season.csv, env_grid_model.csv,
        env_grid.csv, ktsn_master.csv}
출력 : 5_App/demo/data/
  env_model.js    window.__ENVM__       — bio03·bio14·bio18 (dem·ndvi·bio01 은 __GRID__ 에 이미 있음)
  model_<T>.js    window.__MODEL__[T]   — 종별 maxnet 계수 묶음(게이트 통과 종만)
  season_<T>.js   window.__SEASON__[T]  — 종별 12개월 점수 0~100
  model_meta.js   window.__MODELMETA__  — 생성일·변수·게이트·분류군별 종수

브라우저가 점수를 직접 계산한다. maxnet 의 predict 는 특징을 정규화하지 않고 범위로 자르기만 하므로
아래 값만 있으면 예측이 정확히 재현된다(R 대조 검증: 최대오차 0.00e+00).
  x   = clamp(값, vmin, vmax)                       변수별 관측범위로 자르기
  f   = [x, x^2] 중 계수가 남은 항                   (classes="lq" → linear + quadratic)
  f   = clamp(f, fmin, fmax)                        특징별 범위로 자르기
  s   = 1 - exp(-exp(e + sum(f*b) + a))             cloglog

적합 여부의 경계는 종마다 다르다. 예전에는 교차검증 TSS 가 0.4 에 못 미치는 종을 통째로 뺐는데,
그러면 8,935종 중 4,086종이 사라진다. 미달의 원인을 보면 표본이 얇아서가 아니라 분포가 넓어서다
(점유 셀 1,000칸 이상 구간은 83.0% 가 미달, 10~29칸 구간은 20.4% 만 미달). 전국에 고루 사는 종은
환경으로 갈라낼 것이 애초에 적어 TSS 가 낮게 나오는 것이고, 그렇다고 그 종의 적합지 판정이
불가능한 것은 아니다.

그래서 고정 기준선을 버리고 종마다 자기 임계값을 쓴다. thr_cv 는 교차검증에서 TSS 가 최대가 되는
지점의 점수(Youden J)이므로, 그 종에 대해 실제로 가장 잘 갈라내는 경계다. 대신 tss_cv 를 함께
실어 이 경계가 얼마나 믿을 만한지 화면에서 밝힌다 — 값을 감추는 대신 근거의 세기를 드러낸다.
임계값이 없는 종(교차검증이 성립하지 않은 6종)만 공간 축에서 뺀다.

env_grid.js 는 건드리지 않는다 — 이미 배포된 발견공백 자산이 거기서 파생되므로 컬럼을 늘리면
전 종 자산이 함께 흔들린다. 새 변수는 옆에 따로 실어 이 기능을 쓸 때만 받게 한다.
env_model.js 의 배열은 env_grid.csv 행 순서(=__GRID__ 구성 순서)와 같고, 클라이언트가 확인할 수
있도록 첫/끝 cid 와 개수를 함께 싣는다.

사용 : python build_model_data.py [YYYY-MM-DD]   (model_species.py·build_season.py 이후)
"""
import sys, re, csv, json
from pathlib import Path
from collections import defaultdict

APP = Path(__file__).resolve().parent
BASE = APP.parent
PROC = BASE / "1_Data" / "processed"
STORE = PROC / "model_store"
OUT = APP / "demo" / "data"
GEN = sys.argv[1] if len(sys.argv) > 1 else ""

ADD_VARS = ["bio03", "bio14", "bio18"]
ADD_SCALE = {"bio03": 10, "bio14": 1, "bio18": 1}    # env_grid_model.R 의 SCALE 과 같아야 한다
GRADES = [(0.8, "A"), (0.6, "B"), (0.4, "C"), (0.2, "D")]   # 교차검증 TSS → 신뢰 등급(미만은 E)


def _txfile(t):
    """분류군 코드 → 파일명 토큰('-P'→'_P'). build_gap_data/service.html 규칙과 일치."""
    return re.sub(r"[^A-Za-z0-9]", "_", t)


def _q(x, s):
    if x is None or x == "":
        return None
    try:
        f = float(x)
    except ValueError:
        return None
    return None if f != f else int(round(f * s))


def _lst(x):
    """길이 1 배열은 R jsonlite 의 auto_unbox 로 스칼라가 되어 돌아온다 — 계수가 하나뿐인 종이 그렇다.
    클라이언트는 항상 배열을 기대하므로 여기서 되돌린다."""
    return x if isinstance(x, list) else [x]


def _num(x):
    """R 의 NaN/NA 는 jsonlite 에서 문자열 "NaN"/"NA" 로 내려온다. 수치가 아니면 None."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    csv.field_size_limit(10 ** 7)
    OUT.mkdir(parents=True, exist_ok=True)

    # ── env_model.js : __GRID__ 와 같은 행 순서로 3개 변수 ──────────────
    order = [r["cid"] for r in csv.DictReader(open(PROC / "env_grid.csv", encoding="utf-8-sig"))]
    em = {r["cid"]: r for r in csv.DictReader(open(PROC / "env_grid_model.csv", encoding="utf-8-sig"))}
    if len(order) != len(em):
        sys.exit(f"[불일치] env_grid {len(order)}행 vs env_grid_model {len(em)}행")
    cols = {v: [_q(em[c].get(v), ADD_SCALE[v]) for c in order] for v in ADD_VARS}
    payload = {**cols, "scale": ADD_SCALE, "n": len(order),
               "cid0": int(order[0]), "cid1": int(order[-1])}
    p = OUT / "env_model.js"
    p.write_text("window.__ENVM__=" + json.dumps(payload, separators=(",", ":")) + ";",
                 encoding="utf-8")
    nmiss = sum(1 for v in ADD_VARS for x in cols[v] if x is None)
    print(f"env_model.js: {len(order):,}셀 × {len(ADD_VARS)}변수 · 결측 {nmiss:,} "
          f"· {p.stat().st_size/1e6:.2f} MB")

    # ── model_<T>.js : 종별 계수 + 자기 임계값 ─────────────────────────
    kept = nothr = failed = 0
    gcnt = defaultdict(int)
    for f in sorted(STORE.glob("*.json")):
        t = f.stem
        js = json.loads(f.read_text(encoding="utf-8"))
        out = {}
        for x in js["sp"]:
            if x.get("failed"):
                failed += 1
                continue
            tss, thr = _num(x.get("tss_cv")), _num(x.get("thr_cv"))
            if tss is None or thr is None:      # 교차검증이 성립하지 않은 종 — 경계를 정할 수 없다
                nothr += 1
                continue
            # 계수는 반올림하지 않는다. 제곱항의 특징값이 10^5~10^6 규모(bio18^2 등)라
            # 절대값 6자리로 자르면 계수 오차 5e-7 이 link 에서 0.2 이상으로 증폭된다.
            out[x["k"]] = {"v": _lst(x["vars"]), "bn": _lst(x["beta_names"]),
                           "b": _lst(x["betas"]),
                           "a": x["alpha"], "e": x["entropy"],
                           "vmin": _lst(x["varmin"]), "vmax": _lst(x["varmax"]),
                           "fmin": _lst(x["fmin"]), "fmax": _lst(x["fmax"]),
                           "thr": round(thr, 6), "tss": round(tss, 3), "n": x["n"]}
            kept += 1
            gcnt[next((g for lo, g in GRADES if tss >= lo), "E")] += 1
        p = OUT / f"model_{_txfile(t)}.js"
        p.write_text(f'(window.__MODEL__=window.__MODEL__||{{}})["{t}"]='
                     + json.dumps(out, separators=(",", ":")) + ";", encoding="utf-8")
        print(f"  model_{_txfile(t)}.js: {len(out):,}종 · {p.stat().st_size/1e6:.2f} MB")
    print(f"공간 축: {kept:,}종 · 임계값 없음 {nothr:,} · 적합 실패 {failed:,}")
    print("  신뢰 등급(교차검증 TSS): "
          + " · ".join(f"{g} {gcnt[g]:,}" for g in ("A", "B", "C", "D", "E")))

    # ── season_<T>.js : 종별 12개월 점수 ──────────────────────────────
    ssn = defaultdict(dict)
    nrec = 0
    for r in csv.DictReader(open(PROC / "species_season.csv", encoding="utf-8-sig")):
        ssn[r["taxon_group"]][r["ktsn"]] = [int(r[f"m{i:02d}"]) for i in range(1, 13)]
        nrec += 1
    for t, d in sorted(ssn.items()):
        p = OUT / f"season_{_txfile(t)}.js"
        p.write_text(f'(window.__SEASON__=window.__SEASON__||{{}})["{t}"]='
                     + json.dumps(d, separators=(",", ":")) + ";", encoding="utf-8")
        print(f"  season_{_txfile(t)}.js: {len(d):,}종 · {p.stat().st_size/1e6:.2f} MB")
    print(f"계절 축: {nrec:,}종")

    meta = {"generated": GEN, "grades": {g: gcnt[g] for g in ("A", "B", "C", "D", "E")},
            "vars_grid": ["dem", "ndvi", "bio01"], "vars_model": ADD_VARS,
            "n_spatial": kept, "n_season": nrec}
    (OUT / "model_meta.js").write_text(
        "window.__MODELMETA__=" + json.dumps(meta, separators=(",", ":")) + ";", encoding="utf-8")
    print(f"model_meta.js: 공간 {kept:,}종 · 계절 {nrec:,}종 → {OUT}")


if __name__ == "__main__":
    main()
