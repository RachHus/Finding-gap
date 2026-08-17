# -*- coding: utf-8 -*-
"""env 정적자산 빌드 — 종 페이지 "기후·지형 지위" 박스플롯 막대.
입력 : 1_Data/processed/{species_env_stats.csv, env_national.csv}
출력 : 5_App/demo/data/species_env.js  (window.__ENV__  = {ktsn:[변수당 min,q1,median,q3,max,mean,sd]})
       5_App/demo/data/env_meta.js     (window.__ENVMETA__ = {vars, ref})
실행 : python 5_App/build_env_data.py   (env_layers.R 이후)
"""
import csv, json, gzip
from pathlib import Path

APP  = Path(__file__).resolve().parent           # 5_App
BASE = APP.parent
PROC = BASE / "1_Data" / "processed"
OUT  = APP / "demo" / "data"

# 표시 7변수: 종카드 막대 순서. dec=소수자리(0=정수)
# NDVI(정규식생지수)·NDWI(정규수분지수)는 -1~1 무단위. 막대엔 전 종 일괄 표시(모델의 NDWI 종별 적용과 무관).
VARS = [
    {"key": "bio01", "label": "연평균기온",      "unit": "°C", "dec": 1},
    {"key": "bio05", "label": "최난월 최고기온", "unit": "°C", "dec": 1},
    {"key": "bio06", "label": "최한월 최저기온", "unit": "°C", "dec": 1},
    {"key": "bio12", "label": "연강수량",        "unit": "mm", "dec": 0},
    {"key": "dem",   "label": "해발고도",        "unit": "m",  "dec": 0},
    {"key": "ndvi",  "label": "정규식생지수",    "unit": "",   "dec": 2},
    {"key": "ndwi",  "label": "정규수분지수",    "unit": "",   "dec": 2},
]
KEYS = [v["key"] for v in VARS]
DEC  = {v["key"]: v["dec"] for v in VARS}


def rnd(x, dec):
    f = float(x)
    return round(f, dec) if dec else int(round(f))


# 변수당 인코딩 순서(프런트 envBars 가 동일 순서로 해석): 박스플롯 + 평균±표준편차
STATS = ("min", "q1", "median", "q3", "max", "mean", "sd")


def read_stats(path, allow):
    sp = {}
    if not path.exists():
        print(f"(경고) 누락: {path.relative_to(BASE)}"); return sp
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = r["var"]
            if v in allow:
                sp.setdefault(r["ktsn"], {})[v] = tuple(r[c] for c in STATS)
    return sp


def main():
    sp = read_stats(PROC / "species_env_stats.csv", set(KEYS))

    env = {}
    for k, d in sp.items():
        row, ok = [], False
        for key in KEYS:
            if key in d:
                dec = DEC[key]
                row += [rnd(x, dec) for x in d[key]]; ok = True
            else:
                row += [None] * len(STATS)
        if ok:
            env[k] = row

    ref = {}
    with open(PROC / "env_national.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = r["var"]; dec = DEC[v]
            ref[v] = {c: rnd(r[c], dec) for c in ("p01", "q1", "median", "q3", "p99", "min", "max")}

    meta = {"vars": VARS, "ref": ref}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "env_meta.js").write_text(
        "window.__ENVMETA__=" + json.dumps(meta, ensure_ascii=False) + ";\n", encoding="utf-8")
    (OUT / "species_env.js").write_text(
        "window.__ENV__=" + json.dumps(env, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8")

    raw = (OUT / "species_env.js").stat().st_size
    gz = len(gzip.compress((OUT / "species_env.js").read_bytes()))
    print(f"species_env.js 종 {len(env):,} · {raw/1024:.0f}KB (gzip {gz/1024:.0f}KB)")
    print(f"env_meta.js 변수 {len(VARS)} · 전국기준 {len(ref)}")


if __name__ == "__main__":
    main()
