# -*- coding: utf-8 -*-
"""
수계 격자 산출 — 1km 셀 중 하천이 지나는 셀만 추린다 → cell_water.csv

어류·저서성무척추동물은 물에서만 산다. 그런데 적합 모형이 쓰는 변수(기온·강수·고도·식생)는
물이 있는지 없는지를 모른다. 그래서 하천 옆 산비탈도 "기후가 맞다"는 이유로 후보가 된다.
물길이 지나는 셀만 남기는 마스크를 최종 판정에 덧씌워 그 부분을 잘라낸다.

마스크를 환경격자(env_grid)의 새 변수로 넣지 않는 이유: 모형 설정 해시가 달라져
8,900여 종을 전부 다시 적합해야 한다. 판정이 끝난 뒤 격자를 자르는 쪽은 그럴 일이 없다.

입력 : 4_References/<시도>/Channel Network_<코드>.shp  — DEM 에서 유도한 하천망(EPSG:8997)
        1_Data/processed/env_grid.csv                   — 1km 셀 중심 경위도
출력 : 1_Data/processed/cell_water.csv                  — cid, ord(그 셀 최대 Strahler 차수)

격자는 EPSG:5186 에서 한 변 989.999m(30m 원본 × 33) 정사각이다 — 연속 cid 쌍의 변위로 실측해
확인했다(dx 989.999 · dy 0.00). env_grid.csv 의 경위도는 소수 5자리로 반올림돼 있어 되돌리면
±1.6m 흔들리므로 규칙격자에 스냅한 뒤 상자를 만든다.

차수(ord)는 문턱을 나중에 바꿀 수 있도록 함께 싣는다. 배포 마스크는 ord≥1(하천이 조금이라도
지나면 남김)이다. 문턱을 올리면 실제 어류 발견 셀까지 잘려 나간다 — 전국 어류 점유 셀 15,829칸
기준 ord≥1 은 90.3% 가 살아남지만 ord≥2 는 76.1%, ord≥3 은 49.8% 로 떨어진다.

사용 : python 3_ETL/python/build_cell_water.py
"""
import sys, glob, time
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box

REPO = Path(__file__).resolve().parents[2]
PROC = REPO / "1_Data" / "processed"
REF = REPO / "4_References"
OUT = PROC / "cell_water.csv"

GRID_CRS = "EPSG:5186"      # bio01 원본 래스터 CRS — 격자가 축에 나란한 유일한 좌표계
CELL = 989.999              # 셀 한 변(m)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()

    shps = sorted(glob.glob(str(REF / "*" / "Channel Network_*.shp")))
    if not shps:
        sys.exit(f"[입력 없음] {REF}/<시도>/Channel Network_*.shp")

    parts = []
    for p in shps:
        d = gpd.read_file(p)
        parts.append(d[["ORDER", "geometry"]])
        print(f"  {Path(p).parent.name:6s} {len(d):>7,}개 · 차수 1~{int(d['ORDER'].max())}")
    net = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
    net = net.set_geometry(net.geometry.force_2d()).to_crs(GRID_CRS)
    print(f"통합 하천망 {len(net):,}개 · 최대 차수 {int(net['ORDER'].max())}")

    g = pd.read_csv(PROC / "env_grid.csv", usecols=["cid", "lon", "lat"])
    pt = gpd.GeoSeries(gpd.points_from_xy(g.lon, g.lat), crs="EPSG:4326").to_crs(GRID_CRS)
    x0, y0 = pt.x.min(), pt.y.min()
    gx = x0 + np.round((pt.x.values - x0) / CELL) * CELL
    gy = y0 + np.round((pt.y.values - y0) / CELL) * CELL
    res = max(np.abs(pt.x.values - gx).max(), np.abs(pt.y.values - gy).max())
    if res > CELL / 4:
        sys.exit(f"[격자 어긋남] 스냅 잔차 {res:.1f}m — 격자 CRS/셀크기 가정을 확인할 것")
    h = CELL / 2
    cells = gpd.GeoDataFrame({"cid": g.cid.values},
                             geometry=[box(a - h, b - h, a + h, b + h) for a, b in zip(gx, gy)],
                             crs=GRID_CRS)

    j = gpd.sjoin(cells, net[["ORDER", "geometry"]], predicate="intersects", how="inner")
    w = j.groupby("cid")["ORDER"].max().astype(int).rename("ord").reset_index()
    w.to_csv(OUT, index=False, encoding="utf-8")

    print(f"cell_water.csv 수계셀 {len(w):,} / 전체 {len(cells):,} "
          f"({len(w)/len(cells)*100:.1f}%) · 스냅 잔차 {res:.1f}m ({time.time()-t0:.0f}초)")
    print("  차수 문턱별: " + " · ".join(
        f"≥{k} {int((w['ord'] >= k).sum()):,}" for k in range(1, int(w["ord"].max()) + 1)))


if __name__ == "__main__":
    main()
