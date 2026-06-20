# -*- coding: utf-8 -*-
"""
NIBR 국가생물종목록(KTSN) 수집 — 관리분류군 1~11번.
- 키: 환경변수 NIBR_API_KEY 또는 3_ETL/.env 의 NIBR_API_KEY (채팅/깃에 노출 금지)
- 허용 IP: NIBR에 등록한 IP에서 실행해야 함(이 PC에서 실행 → 이 PC의 공인 IP)
사용법:
  python fetch_nibr_ktsn.py smoke        # 키/IP/페이지 동작 검증(MM 1페이지)
  python fetch_nibr_ktsn.py all [size]   # 1~11 전체 수집 → 1_Data/raw/nibr/ktsn_*.json
  python fetch_nibr_ktsn.py synprobe     # 분류군 미지정 전체질의로 corsynSeYn 분포 표본확인(이명 존재여부 판정)
  python fetch_nibr_ktsn.py synall       # 분류군 미지정 전체 수집(61,230) → ktsn_ALL.ndjson (이명 포함 가능)
"""
import os, sys, json, time
from pathlib import Path
import urllib.request, urllib.parse, urllib.error

BASE = Path(__file__).resolve().parents[2]
ENV  = BASE / "3_ETL" / ".env"
RAW  = BASE / "1_Data" / "raw" / "nibr"
ENDPOINT = "https://species.nibr.go.kr/gwsvc/openapi/rest/ktsn/taxons/search"

TAXA = {"MM":"포유류","AV":"조류","RP":"파충류","AM":"양서류","-P":"어류",
        "UC":"미삭동물","CC":"두삭동물","IV":"무척추동물(곤충제외)","IN":"곤충류",
        "VP":"관속식물","MS":"선태류"}

def load_key():
    k = os.environ.get("NIBR_API_KEY")
    if k: return k.strip()
    if ENV.exists():
        for ln in ENV.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln.startswith("NIBR_API_KEY=") and not ln.startswith("#"):
                val = ln.split("=", 1)[1]
                val = val.split("#", 1)[0].strip().strip('"').strip("'")  # 인라인 주석/따옴표 제거
                return val
    return None

def fetch_page(key, code, page, size):
    params = {"oapiAcsUnqNo": key, "page": page, "size": size, "responseType": "json"}
    if code is not None:                         # code=None → 분류군 미지정 전체질의
        params["schTxgrpGroupCd"] = code
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(ENDPOINT + "?" + qs,
                                 headers={"User-Agent": "finding-gap/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        body = ex.read().decode("utf-8", "replace")[:300]
        return {"status": ex.code, "message": f"HTTPError {ex.code}", "_body": body}

def smoke(key):
    d = fetch_page(key, "MM", 1, 100)
    pi = (d.get("data") or {}).get("pageInfo") or {}
    content = (d.get("data") or {}).get("content") or []
    print("status :", d.get("status"), d.get("message"))
    if d.get("_body"): print("body   :", d["_body"])
    print("size/totalElements/totalPages :", pi.get("size"), pi.get("totalElements"), pi.get("totalPages"))
    print("이번 응답 행수 :", len(content))
    if content:
        c = content[0]
        print("샘플 :", c.get("ktsn"), "|", c.get("stnm"), "|", c.get("ktsnKrnNm"), "|", c.get("txgrpGroupCd"))
    print("\n→ 정상(status 200, 행수>0)이면 'all' 로 전체 수집하세요.")

def fetch_page_retry(key, code, page, size=10, tries=4):
    last = None
    for a in range(tries):
        d = fetch_page(key, code, page, size)
        if d.get("status") == 200:
            return d
        last = d
        time.sleep(0.6 * (a + 1))
    print(f"  [{code}] page {page} 실패 status={last.get('status')} {last.get('message')}")
    return None

def fetch_taxon(key, code, name, sleep=0.12):
    """NDJSON에 페이지단위 append + .progress 체크포인트 → 중단 시 이어받기."""
    nd   = RAW / f"ktsn_{code}.ndjson"
    prog = RAW / f"ktsn_{code}.progress"
    done = RAW / f"ktsn_{code}.done"
    if done.exists():
        print(f"  [{code}] {name}: 이미 완료(skip)")
        return
    start = (int(prog.read_text().strip()) + 1) if prog.exists() else 1
    page, total = start, None
    with open(nd, "a", encoding="utf-8") as fo:
        while True:
            d = fetch_page_retry(key, code, page)
            if d is None:
                print(f"  [{code}] {name}: page {page}에서 중단 — 재실행 시 이어서 수집")
                return
            data = d.get("data") or {}
            for r in (data.get("content") or []):
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            pi = data.get("pageInfo") or {}
            total = pi.get("totalElements", total)
            prog.write_text(str(page))
            if page % 100 == 0:
                print(f"  [{code}] {name}: {page}/{pi.get('totalPages')}p", flush=True)
            if not pi.get("hasNext"):
                break
            page += 1
            time.sleep(sleep)
    done.write_text(str(total))
    print(f"  [{code}] {name}: 완료 ~{total:,}종")

def fetch_all(key, size=10, sleep=0.12):
    RAW.mkdir(parents=True, exist_ok=True)
    for code, name in TAXA.items():
        fetch_taxon(key, code, name, sleep=sleep)
    print(f"전체 수집 종료 → {RAW}  (각 ktsn_*.ndjson)")


def synprobe(key, pages=(1, 2, 3, 50, 100, 500, 1000, 3000, 6000)):
    """분류군 미지정 전체질의로 표본 페이지를 받아 corsynSeYn(정명여부) 분포를 본다.
    N(이명) 레코드가 specsKtsn(상위 종)을 가리키면 → synall 전수집 가치 있음."""
    from collections import Counter
    c = Counter(); n_syn_usable = 0; samples = []
    for p in pages:
        d = fetch_page(key, None, p, 10)   # schTxgrpGroupCd 생략(아래 fetch_page 수정 반영)
        if d.get("status") != 200:
            print(f"  page {p}: status={d.get('status')} {d.get('message')} {d.get('_body','')[:120]}")
            continue
        for r in (d.get("data") or {}).get("content") or []:
            v = r.get("corsynSeYn"); c[v] += 1
            if v == "N":
                sk = r.get("specsKtsn")
                if sk and str(sk) != str(r.get("ktsn")):
                    n_syn_usable += 1
                    if len(samples) < 8:
                        samples.append((r.get("ktsnKrnNm"), r.get("stnm"), "→종", sk))
    print(f"표본 corsynSeYn 분포: {dict(c)} | 이명(N)→상위종 매핑 가능 {n_syn_usable}건")
    for s in samples:
        print("   이명:", s)
    print("\n→ N(이명)이 의미있게 나오면 'synall' 로 전수집하세요. 거의 Y뿐이면 API엔 이명 없음(웹 상세만 보유).")


def fetch_all_unfiltered(key, sleep=0.12):
    """분류군 미지정 전체 수집 → ktsn_ALL.ndjson. corsynSeYn=N(이명) 레코드 포착이 목적."""
    RAW.mkdir(parents=True, exist_ok=True)
    nd = RAW / "ktsn_ALL.ndjson"; prog = RAW / "ktsn_ALL.progress"; done = RAW / "ktsn_ALL.done"
    if done.exists():
        print("  ktsn_ALL: 이미 완료(skip)"); return
    start = (int(prog.read_text().strip()) + 1) if prog.exists() else 1
    page, total = start, None
    with open(nd, "a", encoding="utf-8") as fo:
        while True:
            d = fetch_page_retry(key, None, page)
            if d is None:
                print(f"  ktsn_ALL: page {page}에서 중단 — 재실행 시 이어서 수집"); return
            data = d.get("data") or {}
            for r in (data.get("content") or []):
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            pi = data.get("pageInfo") or {}
            total = pi.get("totalElements", total)
            prog.write_text(str(page))
            if page % 200 == 0:
                print(f"  ktsn_ALL: {page}/{pi.get('totalPages')}p", flush=True)
            if not pi.get("hasNext"):
                break
            page += 1; time.sleep(sleep)
    done.write_text(str(total))
    print(f"  ktsn_ALL: 완료 ~{total:,}건 → {nd.name}")

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    key = load_key()
    if not key or key.startswith("YOUR_"):
        print("NIBR_API_KEY 미설정. 3_ETL/.env 에 NIBR_API_KEY=발급키 를 넣으세요.")
        sys.exit(1)
    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    if mode == "all":
        size = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        fetch_all(key, size=size)
    elif mode == "synprobe":
        synprobe(key)
    elif mode == "synall":
        fetch_all_unfiltered(key)
    else:
        smoke(key)

if __name__ == "__main__":
    main()
