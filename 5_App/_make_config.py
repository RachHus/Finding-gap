# -*- coding: utf-8 -*-
"""5_App/.env 의 VWORLD_KEY 를 읽어 웹 클라이언트용 config.js 를 생성.
키 값은 출력하지 않음(존재 여부 boolean만). 배포 시엔 호스트의 env 로 동일 파일을 생성."""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent          # 5_App
env = BASE / ".env"
out = BASE / "config.js"

key = ""
if env.exists():
    m = re.search(r"^\s*VWORLD_KEY\s*=\s*(.+?)\s*$", env.read_text(encoding="utf-8"), re.M)
    if m:
        key = m.group(1).strip().strip('"').strip("'")

out.write_text(f'window.VWORLD_KEY = "{key}";\n', encoding="utf-8")
print(f"config.js written | VWORLD_KEY present: {bool(key)}")
