# -*- coding: utf-8 -*-
"""
관찰 추천도 클라이언트 자산 빌드 — 공간 축(maxnet 계수) + 계절 축(월별 점수).

입력 : 1_Data/processed/{model_store/<T>.json, species_season.csv, env_grid_model.csv,
        env_grid.csv, ktsn_master.csv, ndwi_species.csv, cell_water.csv}
출력 : 5_App/demo/data/
  env_model.js    window.__ENVM__       — bio03·bio14·bio18 + wmask(수계 셀 비트맵)
  model_<T>.js    window.__MODEL__[T]   — 종별 maxnet 계수 묶음(w=1 수계 마스크 · w=2 해산종)
  season_<T>.js   window.__SEASON__[T]  — 종별 12개월 점수 0~100
  model_meta.js   window.__MODELMETA__  — 생성일·변수·신뢰등급 분포·분류군별 종수

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
지점의 점수(Youden J)이므로, 그 종에 대해 실제로 가장 잘 갈라내는 경계다. 대신 근거의 세기를 함께
실어 이 경계를 얼마나 믿을지 화면에서 밝힌다 — 값을 감추는 대신 신뢰도를 드러낸다.
임계값이 없는 종(교차검증이 성립하지 않은 6종)만 공간 축에서 뺀다.

신뢰 등급은 tss_cv 가 아니라 auc_cv 로 매긴다. 등급을 TSS 로 매기면 위에서 기준선을 걷어낸 것과
같은 편향이 화면에 그대로 남는다 — TSS 는 분포 넓이에 딸려 움직여(로그 점유칸과 ρ=-0.492) 전국에
고루 사는 종이 모형과 무관하게 낮은 등급을 받는다. AUC 는 같은 상관이 -0.099 다. 900종을 0.5°
공간 블록으로 다시 나눠 가 본 적 없는 지역을 맞히는 실력을 재 보면, 화면에 실제로 뜨는 것(상위
10% 후보의 정밀도)을 AUC 가 더 잘 예고한다(ρ +0.742 vs +0.687). 점유칸 구간을 고정해도 우위가
유지되고(+0.680/+0.648, +0.793/+0.761) 점유칸 수만으로는 정밀도가 예측되지 않으므로(ρ -0.018),
"분포가 좁아 AUC 가 거저 올랐다"는 설명은 성립하지 않는다. 경계는 AUC 관례값을 쓴다.

어류·저서무척추(ndwi_species.csv)는 두 겹으로 다룬다. 모형에는 하천 차수(sord)를 변수로 하나 더
주어 실개천과 큰 강을 구분하게 하고, 판정이 끝난 격자에는 수계 마스크(cell_water.csv)를 덧씌워
하천이 없는 칸을 뺀다. 마스크를 변수가 아니라 사후 처리로 두는 이유는 하천망이 실측이라
모형을 다시 적합할 일이 없어서다.

다만 그 목록의 '어류'는 종 마스터의 분류군이 '-P' 인 종 전부라 해산어까지 들어 있다. 참돔에게
하천 마스크를 씌우면 후보가 바다에서 내륙 하천으로 옮겨 붙는다. 그래서 기록이 하천 밖에 몰린
종(_sea_species)은 w=2 로 갈라 후보를 만들지 않고, 화면에서 그 이유를 밝힌다.

env_grid.js 는 건드리지 않는다 — 이미 배포된 발견공백 자산이 거기서 파생되므로 컬럼을 늘리면
전 종 자산이 함께 흔들린다. 새 변수는 옆에 따로 실어 이 기능을 쓸 때만 받게 한다.
env_model.js 의 배열은 env_grid.csv 행 순서(=__GRID__ 구성 순서)와 같고, 클라이언트가 확인할 수
있도록 첫/끝 cid 와 개수를 함께 싣는다.

사용 : python build_model_data.py [YYYY-MM-DD]   (model_species.py·build_season.py 이후)
"""
import sys, re, csv, json, base64
from pathlib import Path
from collections import defaultdict

APP = Path(__file__).resolve().parent
BASE = APP.parent
PROC = BASE / "1_Data" / "processed"
STORE = PROC / "model_store"
OUT = APP / "demo" / "data"
GEN = sys.argv[1] if len(sys.argv) > 1 else ""

# env_grid.js 에 없어서 여기서 따로 싣는 변수들. sord(하천 차수)는 수생종 모델만 쓰지만,
# 격자 열은 종과 무관하게 한 벌이므로 전 셀분을 함께 내린다(정수 0~7 이라 압축이 잘 먹는다).
ADD_VARS = ["bio03", "bio14", "bio18", "sord"]
ADD_SCALE = {"bio03": 10, "bio14": 1, "bio18": 1, "sord": 1}   # env_grid_model.R 의 SCALE 과 같아야 한다
GRADES = [(0.9, "A"), (0.8, "B"), (0.7, "C"), (0.6, "D")]   # 교차검증 AUC → 신뢰 등급(미만은 E)


def _txfile(t):
    """분류군 코드 → 파일명 토큰('-P'→'_P'). build_gap_data/service.html 규칙과 일치."""
    return re.sub(r"[^A-Za-z0-9]", "_", t)


def _taxon_codes():
    """파일명 토큰 → 실제 분류군 코드. model_store 의 파일명은 이미 토큰으로 씻겨 있어
    (어류 '-P' → '_P.json') 파일명을 그대로 쓰면 클라이언트가 찾는 키와 어긋난다."""
    codes = {r.get("taxon_group") for r in
             csv.DictReader(open(PROC / "ktsn_master.csv", encoding="utf-8-sig"))}
    return {_txfile(t): t for t in codes if t}


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


def _wet_cells():
    f = PROC / "cell_water.csv"
    if not f.exists():
        print(f"(경고) {f.name} 없음 — 수계 마스크 미수록(어류·저서무척추 후보가 뭍까지 잡힌다)")
        return set()
    return {r["cid"] for r in csv.DictReader(open(f, encoding="utf-8-sig"))}


def _water_mask(order, wet):
    """수계 셀 여부를 격자 행 순서 그대로 담은 비트맵(base64). cid 목록으로 실으면 1MB 가까이 되는데
    셀당 1비트면 13KB 다 — 클라이언트가 셀을 행 번호로 훑으므로 비트 위치도 그대로 쓰인다."""
    if not wet:
        return "", 0
    bits = bytearray((len(order) + 7) // 8)
    n = 0
    for i, c in enumerate(order):
        if c in wet:
            bits[i >> 3] |= 1 << (i & 7)
            n += 1
    return base64.b64encode(bytes(bits)).decode(), n


SEA_SHARE = 0.5


def _sea_species(wet_sp, wet_cells):
    """수생종 가운데 자기 발견 기록이 대부분 하천 밖에 있는 종을 가려낸다 — 바다에 사는 종이다.

    ndwi_species.csv 의 '어류'는 종 마스터의 분류군이 '-P' 인 종 전부라 참돔·고등어·홍어 같은
    해산어가 함께 들어 있다. 이들에게 하천 마스크를 씌우면 후보가 바다에서 내륙 하천으로
    옮겨 붙는다 — 있지도 않은 곳을 가리키는 셈이다. 육지 1km 격자에는 바다가 없으므로
    이 종들은 후보를 만들지 않고 그 이유를 밝히는 편이 맞다.

    별도 명단을 두지 않고 관측으로 판정한다. 명단은 종이 늘 때마다 손봐야 하지만
    "제 기록이 하천 밖에 있다"는 사실은 자료가 늘어도 스스로 맞는다. 경계 0.5 는 실측으로
    잡았다 — 0.5 위는 전부 해산 어종이고, 그 아래 0.4~0.5 구간부터 물잠자리·물땡땡이처럼
    하천망에 안 잡히는 웅덩이에 사는 담수종이 섞이기 시작한다."""
    f = PROC / "species_cells.csv"
    if not f.exists():
        print(f"(경고) {f.name} 없음 — 해산 어종 판정 생략(후보가 내륙 하천으로 잡힌다)")
        return set()
    tot, dry = defaultdict(int), defaultdict(int)
    for r in csv.DictReader(open(f, encoding="utf-8-sig")):
        k = r["ktsn"]
        if k not in wet_sp:
            continue
        tot[k] += 1
        if r["cid"] not in wet_cells:
            dry[k] += 1
    return {k for k, n in tot.items() if n and dry[k] / n >= SEA_SHARE}


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
    wcells = _wet_cells()
    payload["wmask"], nwat = _water_mask(order, wcells)
    p = OUT / "env_model.js"
    p.write_text("window.__ENVM__=" + json.dumps(payload, separators=(",", ":")) + ";",
                 encoding="utf-8")
    nmiss = sum(1 for v in ADD_VARS for x in cols[v] if x is None)
    print(f"env_model.js: {len(order):,}셀 × {len(ADD_VARS)}변수 · 결측 {nmiss:,} "
          f"· 수계셀 {nwat:,}({nwat/len(order)*100:.1f}%) · {p.stat().st_size/1e6:.2f} MB")

    # ── model_<T>.js : 종별 계수 + 자기 임계값 ─────────────────────────
    kept = nothr = failed = nwsp = nsea = 0
    gcnt = defaultdict(int)
    tcode = _taxon_codes()
    # 물에서만 사는 종(어류·저서무척추) 표식. w=1 인 종만 최종 판정에 수계 마스크를 덧씌우고,
    # 그중 기록이 하천 밖에 몰린 해산 어종은 w=2 로 갈라 후보를 아예 만들지 않는다.
    wet = {r["ktsn"] for r in csv.DictReader(open(PROC / "ndwi_species.csv", encoding="utf-8-sig"))}
    sea = _sea_species(wet, wcells)
    print(f"수생종 {len(wet):,}종 중 기록이 하천 밖 {SEA_SHARE:.0%} 이상 = 해산종 {len(sea):,}종 "
          f"— 후보 미제공(육지 격자에 서식지가 없다)")
    for f in sorted(STORE.glob("*.json")):
        t = tcode.get(f.stem, f.stem)
        js = json.loads(f.read_text(encoding="utf-8"))
        out = {}
        for x in js["sp"]:
            if x.get("failed"):
                failed += 1
                continue
            auc, thr = _num(x.get("auc_cv")), _num(x.get("thr_cv"))
            if auc is None or thr is None:      # 교차검증이 성립하지 않은 종 — 경계를 정할 수 없다
                nothr += 1
                continue
            # 계수는 반올림하지 않는다. 제곱항의 특징값이 10^5~10^6 규모(bio18^2 등)라
            # 절대값 6자리로 자르면 계수 오차 5e-7 이 link 에서 0.2 이상으로 증폭된다.
            out[x["k"]] = {"v": _lst(x["vars"]), "bn": _lst(x["beta_names"]),
                           "b": _lst(x["betas"]),
                           "a": x["alpha"], "e": x["entropy"],
                           "vmin": _lst(x["varmin"]), "vmax": _lst(x["varmax"]),
                           "fmin": _lst(x["fmin"]), "fmax": _lst(x["fmax"]),
                           "thr": round(thr, 6), "auc": round(auc, 3), "n": x["n"]}
            if x["k"] in sea:
                out[x["k"]]["w"] = 2
                nsea += 1
            elif x["k"] in wet:
                out[x["k"]]["w"] = 1
                nwsp += 1
            kept += 1
            gcnt[next((g for lo, g in GRADES if auc >= lo), "E")] += 1
        p = OUT / f"model_{_txfile(t)}.js"
        p.write_text(f'(window.__MODEL__=window.__MODEL__||{{}})["{t}"]='
                     + json.dumps(out, separators=(",", ":")) + ";", encoding="utf-8")
        print(f"  model_{_txfile(t)}.js: {len(out):,}종 · {p.stat().st_size/1e6:.2f} MB")
    print(f"공간 축: {kept:,}종 · 임계값 없음 {nothr:,} · 적합 실패 {failed:,} "
          f"· 수계 마스크 적용 {nwsp:,}종 · 해산종 {nsea:,}종")
    print("  신뢰 등급(교차검증 AUC): "
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
            "n_spatial": kept, "n_season": nrec, "n_water": nwsp}
    (OUT / "model_meta.js").write_text(
        "window.__MODELMETA__=" + json.dumps(meta, separators=(",", ":")) + ";", encoding="utf-8")
    print(f"model_meta.js: 공간 {kept:,}종 · 계절 {nrec:,}종 → {OUT}")


if __name__ == "__main__":
    main()
