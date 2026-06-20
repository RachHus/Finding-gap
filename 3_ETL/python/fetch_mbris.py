# -*- coding: utf-8 -*-
"""
해양생물종목록(MBRIS) 수집 — 공공데이터포털 B553482.
- 키: 환경변수 MBRIS_API_KEY 또는 3_ETL/.env 의 MBRIS_API_KEY (채팅/깃에 노출 금지)
- API: 공공데이터포털 해양생물종 정보 조회 서비스(대신 NOAA, WORMS 등 대체 고려)

사용법:
  python fetch_mbris.py [--probe]  # --probe: 작은 요청으로 연결성 검증

산출물:
  1_Data/processed/mbris_marine.csv (utf-8-sig)
  - 컬럼: scientific_name, managed_key, korean_name, family, raw
"""
import os
import sys
import json
import csv
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from taxon_key import managed_key

BASE = Path(__file__).resolve().parents[2]
ENV = BASE / "3_ETL" / ".env"
OUT = BASE / "1_Data" / "processed" / "mbris_marine.csv"

# MBRIS API endpoint (공공데이터포털)
# https://www.data.go.kr/data/15057252/fileData.do - 공공데이터포털 상세 페이지에서 API 명세 확인 필요
ENDPOINT = "https://apis.data.go.kr/B553482/mbrisdataview3"


def load_key():
    """API 키 로드: 환경변수 또는 .env 파일."""
    k = os.environ.get("MBRIS_API_KEY")
    if k:
        return k.strip()
    if ENV.exists():
        for ln in ENV.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln.startswith("MBRIS_API_KEY=") and not ln.startswith("#"):
                val = ln.split("=", 1)[1]
                return val.split("#", 1)[0].strip().strip('"').strip("'")
    return None


def fetch_page(key, page_no, num_of_rows):
    """단일 페이지 수집."""
    params = {
        "serviceKey": key,
        "pageNo": str(page_no),
        "numOfRows": str(num_of_rows),
    }
    qs = urllib.parse.urlencode(params)
    url = f"{ENDPOINT}?{qs}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "finding-gap/0.1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        body = ex.read().decode("utf-8", "replace")
        return ex.code, {"error": f"HTTPError {ex.code}", "body": body[:300]}
    except Exception as ex:
        return None, {"error": str(ex)}


def fetch_all(key, page_size=100, max_tries=4):
    """전체 종목록 수집 — 페이지 순회."""
    rows = []
    page_no = 1
    total_count = None

    print(f"MBRIS 종목록 수집 시작 (API: {ENDPOINT})")
    print(f"page_size={page_size}")

    while True:
        status, data = fetch_page(key, page_no, page_size)

        if status != 200:
            print(f"\n[page {page_no}] HTTP {status}")
            if "error" in data:
                print(f"  Error: {data['error']}")
            return rows, total_count, f"Failed at page {page_no}: HTTP {status}"

        # 응답 구조 파악 (공공데이터포털 표준: 최상위 result/response 등)
        # 여기서는 data 필드를 기대 (표준 공공데이터포털 JSON 구조)
        result = data.get("response") or data.get("data") or data

        if isinstance(result, dict) and "resultCode" in result:
            if result.get("resultCode") != "00":
                return rows, total_count, f"API error: {result.get('resultMsg')}"

        items = (result.get("body") or result.get("items") or result.get("data") or [])
        if not isinstance(items, list):
            items = []

        if not items and page_no == 1:
            # 첫 페이지에 항목이 없으면 데이터 부재
            return rows, 0, "API returned empty result (may be unreachable or unsubscribed)"

        # 첫 페이지에서 총 개수 추출
        if page_no == 1:
            total_count = (result.get("totalCount") or result.get("total") or
                          result.get("pageInfo", {}).get("totalElements") or
                          result.get("pageInfo", {}).get("total") or None)

        if not items:
            break  # 더 이상 데이터 없음

        # 각 항목 처리
        for item in items:
            row = {
                "scientific_name": (item.get("spcScitfNm") or item.get("scientificName") or "").strip(),
                "managed_key": None,
                "korean_name": (item.get("CommKorNm") or item.get("koreanName") or "").strip(),
                "family": (item.get("Family") or item.get("FamilyKR") or item.get("family") or "").strip(),
                "raw": json.dumps(item, ensure_ascii=False, separators=(',', ':'))[:500],
            }
            # managed_key 계산
            if row["scientific_name"]:
                mk = managed_key(row["scientific_name"])
                row["managed_key"] = mk
            rows.append(row)

        if page_no % 10 == 0 or len(items) < page_size:
            print(f"  페이지 {page_no}: {len(items)} 항목 수집 (누계: {len(rows)})", flush=True)

        if len(items) < page_size:
            break  # 마지막 페이지

        page_no += 1
        time.sleep(0.5)

    return rows, total_count, None


def probe(key):
    """연결성 검증 — 작은 요청."""
    print("MBRIS API 연결성 검증...")
    status, data = fetch_page(key, 1, 5)
    print(f"  HTTP {status}")
    if status == 200:
        print(f"  응답 키: {list(data.keys())}")
        if "data" in data:
            print(f"  data 필드 타입: {type(data['data'])}")
        return True
    else:
        print(f"  에러: {data.get('error', data)}")
        return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    key = load_key()
    if not key or key.startswith("YOUR_"):
        print("ERROR: MBRIS_API_KEY 미설정. 3_ETL/.env 에 MBRIS_API_KEY=발급키 를 넣으세요.")
        sys.exit(1)

    # 진단 모드
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        ok = probe(key)
        sys.exit(0 if ok else 1)

    # 전체 수집
    t0 = time.time()
    rows, total_count, err = fetch_all(key)

    if err:
        print(f"\n경고: {err}")
        print("  [원인 분석]")
        print("  1. API 서비스가 내려가 있을 수 있음 (공공데이터포털 점검)")
        print("  2. MBRIS_API_KEY가 올바르지 않거나 등록되지 않음")
        print("  3. 공공데이터포털에서 서비스 구독이 해제됨")
        print("  → 공공데이터포털에서 B553482 서비스 확인 필요")

    # CSV 출력
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["scientific_name", "managed_key", "korean_name", "family", "raw"])
        w.writeheader()
        w.writerows(rows)

    print(f"\n결과:")
    print(f"  파일: {OUT.name}")
    print(f"  행 수: {len(rows)}")
    print(f"  API 응답 totalCount: {total_count}")
    if err:
        print(f"  상태: 오류 — {err}")
    else:
        print(f"  상태: 정상")
    print(f"  소요시간: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
