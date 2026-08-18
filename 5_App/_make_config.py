# -*- coding: utf-8 -*-
"""임시 config.js 생성 (VWORLD_KEY 만 주입)

산출: 5_App/config.js
입력: 5_App/.env 의 VWORLD_KEY (V-World 지도 API 키)

이 스크립트는 개발/테스트 용 config.js 파일을 만든다. VWORLD_KEY 의 존재 여부만
확인해 window.VWORLD_KEY 변수에 저장한다. 키 값 자체는 보안상 출력하지 않는다.

주의: 이 파일은 임시용이다. 정식 배포본(build_dist.py 실행)은 이 파일을 덮어쓴다.
      build_dist.py 는 VWORLD_KEY 외에도 Supabase 키, GA4 ID, 대화형 도우미 플래그
      (SUPABASE_URL, SUPABASE_KEY, GA4_MEASUREMENT_ID, CHAT_ENABLED) 를 함께 주입하는
      완전한 config.js 를 생성한다.

실행: 손으로 따로 실행 (run_pipeline.py 미포함, 개발 중에만)
배포: build_dist.py 에서 완전한 config.js 가 생성되므로 배포본은 이 파일 무시"""
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
