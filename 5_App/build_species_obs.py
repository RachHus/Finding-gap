# -*- coding: utf-8 -*-
"""웹 클라이언트용 종별 관측 수 자산 생성

산출: 5_App/demo/data/species_obs.js
입력: 7_MCP/data/fg_mcp.sqlite 의 species_region.obs_count (종×지역 → 종 단위로 합산)

시민과학 탭의 분류군별 관측 리더보드가 쓴다. 종별 관측 수는 이미 분류군별 관측 자산
(obs_<T>.js)에 들어 있지만 그 파일은 관측 하나하나를 다 싣기 때문에 무겁다(곤충류·관속식물이
각 13MB, 9개 합치면 34MB) — 리더보드는 종당 합계 하나만 있으면 되므로 그것만 따로 뽑는다.

관측이 한 번도 없는 종(발견공백)은 넣지 않는다 — 39,972종 중 기록이 있는 20,316종만 담겨
파일이 절반으로 준다. 웹에서는 없는 키를 0으로 읽으면 되므로 뜻이 달라지지 않는다.
관심도 자산(build_species_interest.py)과 같은 모양·같은 방식이라 함께 관리한다.

7_MCP/data/fg_mcp.sqlite.gz 가 있으면 자동 압축 해제.

실행: 손으로 따로 실행 (run_pipeline.py 미포함)
배포: build_dist.py 의 DATA_FILES 리스트에 있어 정적 배포본에 포함됨
"""
import gzip
import json
import shutil
import sqlite3
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent          # 5_App
BASE = APP.parent                              # repo root
DB = BASE / "7_MCP" / "data" / "fg_mcp.sqlite"
GZ = BASE / "7_MCP" / "data" / "fg_mcp.sqlite.gz"
OUT = APP / "demo" / "data" / "species_obs.js"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not DB.exists():
        if not GZ.exists():
            raise FileNotFoundError(f"MCP 데이터 없음: {DB} / {GZ}. 먼저 python 7_MCP/build_mcp_data.py 실행.")
        with gzip.open(GZ, "rb") as f, open(DB, "wb") as o:
            shutil.copyfileobj(f, o)
    con = sqlite3.connect(DB)
    rows = con.execute("""
        SELECT ktsn, SUM(obs_count) c FROM species_region
        WHERE obs_count IS NOT NULL GROUP BY ktsn HAVING c > 0""").fetchall()
    con.close()
    m = {k: int(c) for k, c in rows}
    OUT.write_text("window.__SPOBS__=" + json.dumps(m, separators=(",", ":")) + ";", encoding="utf-8")
    tot = sum(m.values())
    print(f"species_obs.js: 기록 있는 {len(m)}종 · 관측 합계 {tot:,} · {OUT.stat().st_size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
