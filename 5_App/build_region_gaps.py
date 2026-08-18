# -*- coding: utf-8 -*-
"""시군구 × 분류군 발견/공백 요약 자산 생성

산출: 5_App/demo/data/region_gaps.js
입력: 7_MCP/data/fg_mcp.sqlite (대화형 서비스·지역 프로필 페이지 동일 소스)

이 파일은 웹 클라이언트가 알림과 활동지역 설정에서 시군구·분류군별 발견·공백 종수를 표시할 때
쓴다. 지도용 격자 자산(cells_*.js)은 종당 수 MB 이므로 한두 줄 숫자를 위해 내려받을 수 없다.
대신 이 스크립트가 지역·분류군 단위 합계를 미리 계산해 저장한다.

발견 정의(최근 10년)와 좌표미상(00000) 제외 규칙은 서비스와 동일하게 맞춰서
같은 화면 안에서 숫자가 어긋나지 않도록 한다.

실행: 손으로 따로 실행 (run_pipeline.py 미포함)
배포: build_dist.py 의 DATA_FILES 리스트에 있어 정적 배포본에 포함됨
"""
import json
import sqlite3
from pathlib import Path

APP = Path(__file__).resolve().parent
BASE = APP.parent
SQLITE = BASE / "7_MCP" / "data" / "fg_mcp.sqlite"
OUT = APP / "demo" / "data" / "region_gaps.js"

UNKNOWN = "00000"                              # 좌표미상 — 지역 통계에서 제외한다


def build():
    if not SQLITE.exists():
        raise SystemExit(f"소스 없음: {SQLITE}")
    con = sqlite3.connect(SQLITE)
    con.text_factory = str

    meta = dict(con.execute("select key, value from meta"))
    ref = int(meta.get("data_max_year") or 2026)
    cut = ref - 10                             # 서비스 mode A 와 같은 발견 창(최근 10년)

    tx = {g: [kor, int(n)] for g, kor, n in
          con.execute("select taxon_group, taxon_group_kor, n_species from taxa")}

    sido, sg = {}, {}
    for code, name, level, sido_cd in con.execute("select code, name, level, sido_cd from region"):
        if level == "sido":
            sido[code] = name
        else:
            sg[code] = [name, sido_cd]

    # 시군구별 발견 종수 — 같은 종이 여러 해 걸쳐 있어도 한 번만 센다(ktsn distinct).
    found = {}
    for region, group, n in con.execute(
            "select region, taxon_group, count(distinct ktsn) from species_region "
            "where maxyear >= ? and region <> ? group by region, taxon_group", (cut, UNKNOWN)):
        if region not in sg:
            continue
        found.setdefault(region, {})[group] = int(n)

    # 시도 합계는 시군구 합이 아니다 — 한 종이 여러 시군구에 있으면 시도에선 한 종이다.
    found_sido = {}
    for s, group, n in con.execute(
            "select sido, taxon_group, count(distinct ktsn) from species_region "
            "where maxyear >= ? and region <> ? group by sido, taxon_group", (cut, UNKNOWN)):
        if s not in sido:
            continue
        found_sido.setdefault(s, {})[group] = int(n)

    con.close()
    payload = {"gen": meta.get("generated", ""), "ref": ref, "cut": cut,
               "tx": tx, "sido": sido, "sg": sg, "found": found, "foundSido": found_sido}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.__REGGAP__=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"생성 {OUT.relative_to(BASE)} · 시군구 {len(sg)} · 분류군 {len(tx)} · 발견창 {cut}~{ref} · {kb:.1f} KB")


if __name__ == "__main__":
    build()
