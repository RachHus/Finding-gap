# -*- coding: utf-8 -*-
"""지정 EcoBank 레이어 전량 수집(이어받기+재시도). 사용: python collect_layers.py <typeName> [...]"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8")   # 백그라운드 cp949 크래시 방지
import fetch_ecobank as fe

fe.RAW.mkdir(parents=True, exist_ok=True)
key = fe.load_key()
if not key or str(key).startswith("YOUR_"):
    sys.exit("ECOBANK_API_KEY 미설정")

for ln in sys.argv[1:]:
    done = fe.RAW / f"ecobank_{ln}.done"
    t0 = time.time()
    for attempt in range(1, 9):                 # 전송 끊김 시 이어받기 재개
        fe.fetch_layer_full(key, ln)
        if done.exists():
            break
        print(f"  [{ln}] 네트워크 중단 — 재시도 {attempt} (5s 후 이어받기)", flush=True)
        time.sleep(5)
    status = "완료" if done.exists() else "미완(8회 시도 소진)"
    print(f"[{ln}] {status} 소요 {time.time()-t0:.1f}s", flush=True)
print("수집 종료", flush=True)
