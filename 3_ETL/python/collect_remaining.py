# -*- coding: utf-8 -*-
"""EcoBank 미완료 점 레이어 전량 수집(데모 이후 서비스 적용 대비).
- fetch_ecobank.POINT_LAYERS 중 .done 없는 레이어만 수집.
- startIndex 레이어 → fetch_layer_full(이어받기), 습지(NO_STARTINDEX) → fetch_layer_bbox.
- 레이어별 8회 재시도(전송 끊김 시 진행파일에서 이어받기).
사용: python collect_remaining.py            # 남은 전부
      python collect_remaining.py <typeName> [...]   # 지정 레이어만
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8")   # 백그라운드 cp949 크래시 방지
import fetch_ecobank as fe

fe.RAW.mkdir(parents=True, exist_ok=True)
key = fe.load_key()
if not key or str(key).startswith("YOUR_"):
    sys.exit("ECOBANK_API_KEY 미설정")

targets = sys.argv[1:] or fe.POINT_LAYERS
pending = [l for l in targets if not (fe.RAW / f"ecobank_{l}.done").exists()]
print(f"수집 대상 {len(pending)}/{len(targets)} (이미 완료 {len(targets)-len(pending)} skip)", flush=True)
for ln in pending:
    print(f"=== {ln} 시작 ===", flush=True)
    t0 = time.time()
    done = fe.RAW / f"ecobank_{ln}.done"
    bbox_layer = ln in fe.NO_STARTINDEX     # 습지: startIndex 미지원 → bbox 타일링(재개 비지원)
    for attempt in range(1, 9):
        if bbox_layer:
            fe.fetch_layer_bbox(key, ln)
        else:
            fe.fetch_layer_full(key, ln)
        if done.exists():
            break
        print(f"  [{ln}] 중단 — 재시도 {attempt} (5s 후 이어받기)", flush=True)
        time.sleep(5)
    status = "완료" if done.exists() else "미완(8회 소진)"
    print(f"[{ln}] {status} 소요 {time.time()-t0:.1f}s", flush=True)
print("전체 수집 종료", flush=True)
