# -*- coding: utf-8 -*-
"""웹 클라이언트용 관심도 자산 생성

산출: 5_App/demo/data/species_interest.js
입력: 7_MCP/data/fg_mcp.sqlite 의 species.interest 컬럼

이 파일은 웹 클라이언트가 발견공백 A(지도 모드)에서 종별 발견가능도(레이어 투명도)와
종 상세 화면의 숫자 표시에 쓴다. 관심도 정의·산식은 7_MCP/build_mcp_data.py 에서
한 곳만 계산하므로, 웹과 MCP 공개 읽기 서비스가 동일 값을 제공한다.

파일 크기를 줄이기 위해 0~1 범위의 부동소수를 0~1000 정수로 인코딩한다(웹에서 /1000 으로
역계산). 7_MCP/data/fg_mcp.sqlite.gz 가 있으면 자동 압축 해제.

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
OUT = APP / "demo" / "data" / "species_interest.js"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not DB.exists():
        if not GZ.exists():
            raise FileNotFoundError(f"MCP 데이터 없음: {DB} / {GZ}. 먼저 python 7_MCP/build_mcp_data.py 실행.")
        with gzip.open(GZ, "rb") as f, open(DB, "wb") as o:
            shutil.copyfileobj(f, o)
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT ktsn, interest FROM species WHERE interest IS NOT NULL").fetchall()
    con.close()
    m = {k: int(round(float(v) * 1000)) for k, v in rows}     # 0~1 → 0~1000 정수
    OUT.write_text("window.__SPINT__=" + json.dumps(m, separators=(",", ":")) + ";", encoding="utf-8")
    print(f"species_interest.js: {len(m)}종 · {OUT.stat().st_size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
