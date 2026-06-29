# -*- coding: utf-8 -*-
"""env 정적자산 빌드 — 종 페이지 "기후·지형 지위" 막대 + 지도 환경변수 레이어.
입력 : 1_Data/processed/{species_bioclim.csv, species_dem.csv, env_national.csv, env_layers_meta.csv}
출력 : 5_App/demo/data/species_env.js  (window.__ENV__  = {ktsn:[15수치]})
       5_App/demo/data/env_meta.js     (window.__ENVMETA__ = {vars, ref, layers})
PNG(env/*.png)은 env_layers.R 이 직접 demo/data/env 에 산출 — 여기선 메타만 묶음.
실행 : python 5_App/build_env_data.py   (env_layers.R 이후)
"""
import csv, json, gzip
from pathlib import Path

APP  = Path(__file__).resolve().parent           # 5_App
BASE = APP.parent
PROC = BASE / "1_Data" / "processed"
OUT  = APP / "demo" / "data"

# 표시 5변수: 종카드 막대 순서 + 지도 선택 순서. dec=소수자리(0=정수)
VARS = [
    {"key": "bio01", "label": "연평균기온",      "unit": "°C", "type": "temp",   "dec": 1},
    {"key": "bio05", "label": "최난월 최고기온", "unit": "°C", "type": "temp",   "dec": 1},
    {"key": "bio06", "label": "최한월 최저기온", "unit": "°C", "type": "temp",   "dec": 1},
    {"key": "bio12", "label": "연강수량",        "unit": "mm", "type": "precip", "dec": 0},
    {"key": "dem",   "label": "해발고도",        "unit": "m",  "type": "elev",   "dec": 0},
]
PAL = {
    "temp":   ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"],
    "precip": ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"],
    "elev":   ["#2b7a3d", "#a6d96a", "#ffffbf", "#e0a060", "#8c510a"],
}
KEYS = [v["key"] for v in VARS]
DEC  = {v["key"]: v["dec"] for v in VARS}
TYPE = {v["key"]: v["type"] for v in VARS}


def rnd(x, dec):
    f = float(x)
    return round(f, dec) if dec else int(round(f))


def read_summary(path, allow, sp):
    if not path.exists():
        print(f"(경고) 누락: {path.relative_to(BASE)}"); return
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            b = r["bio"]
            if b in allow:
                sp.setdefault(r["ktsn"], {})[b] = (r["min"], r["median"], r["max"])


def main():
    sp = {}
    read_summary(PROC / "species_bioclim.csv", {"bio01", "bio05", "bio06", "bio12"}, sp)
    read_summary(PROC / "species_dem.csv",     {"dem"}, sp)

    env = {}
    for k, d in sp.items():
        row, ok = [], False
        for key in KEYS:
            if key in d:
                mn, md, mx = d[key]; dec = DEC[key]
                row += [rnd(mn, dec), rnd(md, dec), rnd(mx, dec)]; ok = True
            else:
                row += [None, None, None]
        if ok:
            env[k] = row

    ref = {}
    with open(PROC / "env_national.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = r["var"]; dec = DEC[v]
            ref[v] = {c: rnd(r[c], dec) for c in ("p01", "q1", "median", "q3", "p99", "min", "max")}

    layers = {}
    with open(PROC / "env_layers_meta.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = r["var"]
            layers[v] = {
                "png": r["png"],
                "extent": [float(r["xmin"]), float(r["ymin"]), float(r["xmax"]), float(r["ymax"])],
                "vmin": float(r["vmin"]), "vmax": float(r["vmax"]), "palette": PAL[TYPE[v]],
            }

    meta = {"vars": VARS, "ref": ref, "layers": layers}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "env_meta.js").write_text(
        "window.__ENVMETA__=" + json.dumps(meta, ensure_ascii=False) + ";\n", encoding="utf-8")
    (OUT / "species_env.js").write_text(
        "window.__ENV__=" + json.dumps(env, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8")

    raw = (OUT / "species_env.js").stat().st_size
    gz = len(gzip.compress((OUT / "species_env.js").read_bytes()))
    print(f"species_env.js 종 {len(env):,} · {raw/1024:.0f}KB (gzip {gz/1024:.0f}KB)")
    print(f"env_meta.js 변수 {len(VARS)} · 레이어 {len(layers)} · 전국기준 {len(ref)}")


if __name__ == "__main__":
    main()
