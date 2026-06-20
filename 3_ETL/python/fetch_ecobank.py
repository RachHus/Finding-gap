# -*- coding: utf-8 -*-
"""
EcoBank 조사자료(종 출현정보) 수집 — WFS(GML/XML) 방식.
- 키: 환경변수 ECOBANK_API_KEY 또는 3_ETL/.env (채팅/깃 노출 금지)
- 엔드포인트: https://www.nie-ecobank.kr/ecoapi/{SERVICE}/wfs/get{Taxon}{Geom}WFS
  · 발급 typeName(레이어)으로부터 SERVICE/op 자동 도출.
  · 좌표계 EPSG:5186, 검색은 bbox(경계상자) 기반, maxFeatures 최대 100(기본 10).
- 응답은 GML featureMember. 필드명 미문서화 → smoke 로 실제 구조 확인.
사용법:
  python fetch_ecobank.py layers                         # 발급 레이어 레지스트리 출력
  python fetch_ecobank.py smoke [typeName] [bbox] [max]  # 기본: 백두대간 곤충(샘플 bbox)
"""
import os, sys, re
from pathlib import Path
from collections import Counter
import urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parents[2]
ENV  = BASE / "3_ETL" / ".env"
RAW  = BASE / "1_Data" / "raw" / "ecobank"
ECOAPI = "https://www.nie-ecobank.kr/ecoapi"

# 조사사업 프리픽스 → 서비스명
PROG_SERVICE = {"bgts": "BgtsInfoService", "ecpe": "EcpeInfoService",
                "ntee": "NteeInfoService", "wtl": "WtlInfoService"}
PROG_KOR = {"bgts": "백두대간", "ecpe": "생태계정밀조사", "ntee": "자연환경조사", "wtl": "습지"}
TAXON_CAMEL = {"insect": "Insect", "flr": "Flr", "vtn": "Vtn", "amnrp": "Amnrp",
               "fishes": "Fishes", "bnin": "Bnin", "birds": "Birds", "lchn": "Lchn",
               "mml": "Mml", "biota": "Biota"}
TAXON_KOR = {"insect": "곤충", "flr": "식물상", "vtn": "식생", "amnrp": "양서파충류",
             "fishes": "어류", "bnin": "저서무척추동물", "birds": "조류",
             "lchn": "지의류", "mml": "포유류", "biota": "생물상"}
GEOM_CAMEL = {"point": "Point", "pyn": "Pyn"}

# 발급 완료 레이어(typeName). _point(점) 위주 — 종 출현 좌표.
ISSUED_LAYERS = [
    "mv_map_bgts_insect_point", "mv_map_bgts_flr_point", "mv_map_bgts_vtn_pyn",
    "mv_map_bgts_amnrp_point", "mv_map_bgts_fishes_point", "mv_map_bgts_bnin_point",
    "mv_map_bgts_birds_point", "mv_map_bgts_lchn_point", "mv_map_bgts_mml_point",
    "mv_map_ecpe_amnrp_point", "mv_map_ecpe_fishes_point", "mv_map_ecpe_bnin_point",
    "mv_map_ecpe_birds_point", "mv_map_ecpe_mml_point", "mv_map_ecpe_insect_point",
    "mv_map_ecpe_flr_point", "mv_map_ecpe_fishes_pyn", "mv_map_ecpe_insect_pyn",
    "mv_map_ecpe_flr_pyn",
    "mv_map_ntee_insect_point", "mv_map_ntee_flr_point", "mv_map_ntee_amnrp_point",
    "mv_map_ntee_fishes_point", "mv_map_ntee_bnin_point", "mv_map_ntee_birds_point",
    "mv_map_ntee_mml_point",
    "mv_dat_wtl_biota_examin_dta_point_2022",
]

# 샘플 코드의 bbox(소규모 검증용, EPSG:5186)
SAMPLE_BBOX = "314548.9311225004,401742.29949240043,320867.0145135768,409072.0397406582"
# 남한 전역 커버용 광역 bbox(EPSG:5186, 대략)
KOREA_BBOX = "150000,150000,450000,850000"


# typeName → 실제 OpenAPI op 경로명 오버라이드(census에서 NO_OPENAPI_SERVICE_ERROR 난 레이어).
# 백두대간 양서파충류·지의류, 습지 생물상은 유추 op명이 미등록 → EcoBank 가이드의 정확한 서비스 URL로 채울 것.
OP_OVERRIDE = {
    # EcoBank 등록명에 비표준 철자/오타 존재 — 발급내역 상세에서 확인.
    "mv_map_bgts_amnrp_point": "getAmnrpPotinWFS",   # 검증 OK(1,968건) "Point"→"Potin" 오타
    "mv_map_bgts_lchn_point": "getIchnPointWFS",     # 검증 OK(664건) "Lchn"→"Ichn"
    "mv_dat_wtl_biota_examin_dta_point_2022": "getWtlBiotaExaminDtaPointWFS",  # 검증 OK(204,174건) typeName 전체 CamelCase
}


def parse_layer(type_name):
    """typeName → (service, op, prog, taxon, geom). 알 수 없으면 None."""
    m = re.match(r"mv_(?:map|dat)_([a-z]+)_(.+)_(point|pyn)(?:_\d+)?$", type_name)
    if not m:
        return None
    prog, mid, geom = m.group(1), m.group(2), m.group(3)
    taxon = mid.split("_")[0]
    service = PROG_SERVICE.get(prog)
    tc = TAXON_CAMEL.get(taxon)
    gc = GEOM_CAMEL.get(geom)
    ov = OP_OVERRIDE.get(type_name)
    if isinstance(ov, tuple):
        service, op = ov
    elif isinstance(ov, str):
        op = ov
    elif service and tc and gc:
        op = f"get{tc}{gc}WFS"
    else:
        op = None
    return {"service": service, "op": op, "prog": prog, "taxon": taxon, "geom": geom}


def load_key():
    k = os.environ.get("ECOBANK_API_KEY")
    if k:
        return k.strip()
    if ENV.exists():
        for ln in ENV.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln.startswith("ECOBANK_API_KEY=") and not ln.startswith("#"):
                val = ln.split("=", 1)[1]
                return val.split("#", 1)[0].strip().strip('"').strip("'")
    return None


def wfs_get(key, type_name, bbox, max_features=50, out_fmt=None, srs=None, extra=None,
            service=None, op=None):
    if not (service and op):
        info = parse_layer(type_name)
        if not info or not info["op"]:
            return None, f"레이어 파싱/매핑 실패: {type_name} → {info}", None
        service, op = info["service"], info["op"]
    url = f"{ECOAPI}/{service}/wfs/{op}"
    p = {"serviceKey": key, "typeName": type_name, "maxFeatures": max_features}
    if bbox and bbox.lower() not in ("none", "-"):   # bbox와 cql_filter는 상호배타
        p["bbox"] = bbox
    if out_fmt:
        p["outputFormat"] = out_fmt           # GeoServer: application/json → GeoJSON
    if srs:
        p["srsName"] = srs                    # 출력 좌표계 재투영(예: EPSG:4326)
    if extra:
        p.update(extra)                       # startIndex / cql_filter 등 검증용
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(p),
                                 headers={"User-Agent": "finding-gap/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            ct = r.headers.get("Content-Type", "")
            return r.status, r.read().decode("utf-8", "replace"), ct
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode("utf-8", "replace"), None
    except Exception as ex:
        return None, f"{type(ex).__name__}: {ex}", None


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _smoke_geojson(body):
    import json
    try:
        d = json.loads(body)
    except Exception as ex:
        print("JSON 파싱 실패:", ex, "\n앞 600자:\n", body[:600]); return
    feats = d.get("features") or []
    print(f"GeoJSON OK — features 수 : {len(feats)}  | crs : {d.get('crs')}")
    if d.get("totalFeatures") is not None:
        print("totalFeatures :", d.get("totalFeatures"))
    if not feats:
        print("피처 없음. 앞 400자:\n", body[:400]); return
    f0 = feats[0]
    geom = f0.get("geometry") or {}
    print("geometry :", geom.get("type"), str(geom.get("coordinates"))[:60])
    props = f0.get("properties") or {}
    print("\n첫 피처 properties:")
    for k, v in props.items():
        print(f"  {k:24s} = {str(v)[:70]}")
    print("\n필드 목록:", list(props.keys()))


def smoke(key, type_name, bbox, max_features, out_fmt=None, srs=None, extra=None):
    info = parse_layer(type_name)
    print(f"# {type_name}  →  {info}")
    print(f"  bbox={bbox}  max={max_features}  outputFormat={out_fmt}  srs={srs}  extra={extra}")
    status, body, ct = wfs_get(key, type_name, bbox, max_features, out_fmt, srs, extra)
    print("HTTP status :", status, "| Content-Type :", ct)
    head = body.lstrip()[:1]
    if head in ("{", "["):
        _smoke_geojson(body); return
    if head != "<":
        print("응답(XML/JSON 아님, 앞 800자):\n", body[:800]); return
    try:
        root = ET.fromstring(body)
    except Exception as ex:
        print("XML 파싱 실패:", ex, "\n앞 800자:\n", body[:800]); return

    if "Exception" in _local(root.tag) or "Exception" in body[:400]:
        print("서비스 예외 응답:\n", body[:800]); return

    members = root.findall(".//{http://www.opengis.net/gml}featureMember")
    nattr = root.attrib.get("numberOfFeatures") or root.attrib.get("numberMatched")
    print(f"featureMember 수 : {len(members)}  (root numberOfFeatures={nattr})")
    if not members:
        print("피처 없음. 응답 앞 600자:\n", body[:600]); return

    feat = list(members[0])[0] if list(members[0]) else members[0]
    print("\n첫 피처 필드(태그=값):")
    fields = []
    for el in feat:
        name = _local(el.tag)
        fields.append(name)
        txt = (el.text or "").strip()
        if not txt and len(list(el)):  # 지오메트리 등 중첩
            txt = f"<{len(list(el))} child el: " + ",".join(_local(c.tag) for c in el)[:60] + ">"
        print(f"  {name:24s} = {txt[:70]}")
    print("\n필드 목록:", fields)


# ── 생산용 수집 ─────────────────────────────────────────────
import json, time
from datetime import datetime, timezone

PAGE = 500                     # 서버 상한(요청당 최대 500건)
SRS = "EPSG:4326"              # 위경도로 재투영 저장(웹지도·GBIF와 일치)
POINT_LAYERS = [l for l in ISSUED_LAYERS if "_point" in l]   # 종 출현 점 레이어
# startIndex 페이징 미지원 레이어 → bbox 쿼드트리 타일링으로 수집(습지)
NO_STARTINDEX = {"mv_dat_wtl_biota_examin_dta_point_2022"}
WATERMARK = RAW / "_watermark.json"


def _read_wm():
    if WATERMARK.exists():
        return json.loads(WATERMARK.read_text(encoding="utf-8"))
    return {}


def _write_wm(wm):
    WATERMARK.write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_retry(key, type_name, page, start_index=None, cql=None, bbox=None, tries=4):
    extra = {}
    if start_index is not None:
        extra["startIndex"] = start_index
    if cql:
        extra["cql_filter"] = cql
    last = None
    for a in range(tries):
        status, body, ct = wfs_get(key, type_name, bbox, page, "application/json", SRS, extra or None)
        if status == 200 and body.lstrip()[:1] == "{":
            try:
                return json.loads(body)
            except Exception:
                last = body[:200]
        else:
            last = f"status={status} {body[:160]}"
        time.sleep(0.6 * (a + 1))
    where = f"startIndex={start_index}" if start_index is not None else f"bbox={bbox}"
    print(f"  [{type_name}] {where} 실패: {last}")
    return None


def _write_feats(fo, feats):
    for f in feats:
        rec = dict(f.get("properties") or {})
        g = f.get("geometry") or {}
        rec.pop("bbox", None)
        rec["_geom_type"] = g.get("type")
        rec["_coords"] = g.get("coordinates")   # [lon, lat] (EPSG:4326)
        fo.write(json.dumps(rec, ensure_ascii=False) + "\n")


def fetch_layer_full(key, type_name, sleep=0.15):
    """startIndex 페이징으로 레이어 전량 → NDJSON(이어받기)."""
    nd   = RAW / f"ecobank_{type_name}.ndjson"
    prog = RAW / f"ecobank_{type_name}.progress"
    done = RAW / f"ecobank_{type_name}.done"
    if done.exists():
        print(f"  [{type_name}] 이미 완료(skip)"); return
    si = int(prog.read_text().strip()) if prog.exists() else 0
    total, got = None, 0
    with open(nd, "a", encoding="utf-8") as fo:
        while True:
            d = _get_retry(key, type_name, PAGE, si)
            if d is None:
                print(f"  [{type_name}] startIndex={si}에서 중단 — 재실행 시 이어서"); return
            feats = d.get("features") or []
            total = d.get("totalFeatures", total)
            _write_feats(fo, feats)
            got += len(feats)
            si += PAGE
            prog.write_text(str(si))
            if got == len(feats) or si % (PAGE * 20) == 0:
                print(f"  [{type_name}] {got:,}/{total:,}", flush=True)
            if len(feats) < PAGE:
                break
            time.sleep(sleep)
    done.write_text(json.dumps({"total": total, "got": got}, ensure_ascii=False))
    print(f"  [{type_name}] 완료 {got:,}/{total:,}종출현")


def fetch_layer_bbox(key, type_name, sleep=0.15, max_depth=14):
    """startIndex 미지원 레이어(습지): bbox 쿼드트리 타일링. 경계중복은 feature id로 dedup. (재개 비지원)"""
    nd   = RAW / f"ecobank_{type_name}.ndjson"
    done = RAW / f"ecobank_{type_name}.done"
    if done.exists():
        print(f"  [{type_name}] 이미 완료(skip)"); return
    x0, y0, x1, y1 = map(float, KOREA_BBOX.split(","))
    stack = [(x0, y0, x1, y1, 0)]
    seen, saturated, next_mark = set(), 0, 5000
    with open(nd, "w", encoding="utf-8") as fo:
        while stack:
            ax, ay, bx, by, depth = stack.pop()
            d = _get_retry(key, type_name, PAGE, bbox=f"{ax},{ay},{bx},{by}")
            if d is None:
                continue
            feats = d.get("features") or []
            if len(feats) >= PAGE and depth < max_depth:     # 포화 → 4분할
                mx, my = (ax + bx) / 2, (ay + by) / 2
                stack.extend([(ax, ay, mx, my, depth + 1), (mx, ay, bx, my, depth + 1),
                              (ax, my, mx, by, depth + 1), (mx, my, bx, by, depth + 1)])
                continue
            if len(feats) >= PAGE:
                saturated += 1                               # 최대깊이 포화 — 일부 누락 가능
            for f in feats:
                fid = f.get("id")
                if fid in seen:
                    continue
                seen.add(fid)
                rec = dict(f.get("properties") or {})
                g = f.get("geometry") or {}
                rec.pop("bbox", None)
                rec["_geom_type"] = g.get("type")
                rec["_coords"] = g.get("coordinates")
                fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if len(seen) >= next_mark:
                print(f"  [{type_name}] bbox 타일링 {len(seen):,}건…", flush=True)
                next_mark += 5000
            time.sleep(sleep)
    done.write_text(json.dumps({"unique": len(seen), "saturated_tiles": saturated}, ensure_ascii=False))
    warn = f"  ⚠ 포화타일 {saturated}개(누락가능)" if saturated else ""
    print(f"  [{type_name}] bbox 타일링 완료 고유 {len(seen):,}건{warn}")


def fetch_layer_incr(key, type_name, since_date, sleep=0.15):
    """regist_dt > since_date(YYYY-MM-DD) 증분 → NDJSON. bbox 미사용(cql과 상호배타)."""
    nd  = RAW / f"ecobank_{type_name}_incr_{since_date}.ndjson"
    cql = f"regist_dt > '{since_date}'"
    if type_name in NO_STARTINDEX:                           # startIndex 미지원 → 단일 요청
        d = _get_retry(key, type_name, PAGE, cql=cql)
        feats = (d or {}).get("features") or []
        with open(nd, "a", encoding="utf-8") as fo:
            _write_feats(fo, feats)
        tail = " (상한 도달 — 정적 레이어라 통상 0)" if len(feats) >= PAGE else ""
        print(f"  [{type_name}] 증분 {len(feats)}건 (> {since_date}){tail}")
        return len(feats)
    si, total, got = 0, None, 0
    with open(nd, "a", encoding="utf-8") as fo:
        while True:
            d = _get_retry(key, type_name, PAGE, si, cql=cql)
            if d is None:
                print(f"  [{type_name}] 증분 startIndex={si} 중단"); return 0
            feats = d.get("features") or []
            total = d.get("totalFeatures", total)
            _write_feats(fo, feats)
            got += len(feats)
            si += PAGE
            if len(feats) < PAGE:
                break
            time.sleep(sleep)
    print(f"  [{type_name}] 증분 {got:,}/{total:,} (> {since_date})")
    return got


def fetch_all(mode_incr=False, since=None):
    RAW.mkdir(parents=True, exist_ok=True)
    key = load_key()
    if not key or key.startswith("YOUR_"):
        print("ECOBANK_API_KEY 미설정."); sys.exit(1)
    wm = _read_wm()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for ln in POINT_LAYERS:
        info = parse_layer(ln)
        if not info or not info["op"]:
            print(f"  [{ln}] 매핑 실패 skip"); continue
        if mode_incr:
            sd = since or wm.get(ln, {}).get("last_run") or "1900-01-01"
            fetch_layer_incr(key, ln, sd)
        elif ln in NO_STARTINDEX:
            fetch_layer_bbox(key, ln)
        else:
            fetch_layer_full(key, ln)
        wm[ln] = {"last_run": today}
        _write_wm(wm)
    print(f"종료 → {RAW}  (워터마크 {WATERMARK.name})")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    if mode == "all":
        fetch_all(mode_incr=False); return
    if mode == "incr":
        since = sys.argv[2] if len(sys.argv) > 2 else None
        fetch_all(mode_incr=True, since=since); return
    if mode == "probe":
        # probe <service> <op> <typeName> — 정확한 op 경로명 탐색용(1건 GeoJSON)
        key = load_key()
        if not key or key.startswith("YOUR_"):
            print("ECOBANK_API_KEY 미설정."); sys.exit(1)
        service, op, tn = sys.argv[2], sys.argv[3], sys.argv[4]
        status, body, ct = wfs_get(key, tn, None, 1, "application/json", "EPSG:4326",
                                   service=service, op=op)
        head = body.lstrip()[:1]
        if head == "{":
            try:
                tot = json.loads(body).get("totalFeatures")
            except Exception:
                tot = "?"
            print(f"OK  {service}/{op}  typeName={tn}  totalFeatures={tot}")
        else:
            msg = body.replace("\n", " ")
            import re as _re
            m = _re.search(r"ExceptionText>([^<]+)", msg) or _re.search(r"ServiceException[^>]*>([^<]+)", msg)
            print(f"ERR {service}/{op}  → {(m.group(1) if m else msg)[:120]}")
        return
    if mode == "census":
        key = load_key()
        if not key or key.startswith("YOUR_"):
            print("ECOBANK_API_KEY 미설정."); sys.exit(1)
        grand = 0
        print(f"{'layer':40s} {'조사사업':10s} {'분류군':10s} {'건수':>10s}")
        for ln in POINT_LAYERS:
            info = parse_layer(ln)
            si = None if ln in NO_STARTINDEX else 0   # 습지는 startIndex 미지원
            d = _get_retry(key, ln, 1, si)
            tot = (d or {}).get("totalFeatures")
            tot = tot if isinstance(tot, int) else -1
            if tot > 0:
                grand += tot
            pk = PROG_KOR.get(info["prog"], info["prog"])
            tk = TAXON_KOR.get(info["taxon"], info["taxon"])
            print(f"{ln:40s} {pk:10s} {tk:10s} {tot:>10,}")
        print(f"{'─'*74}\n{'점 레이어 23개 총 종출현 건수':54s} {grand:>10,}")
        return
    if mode == "layers":
        for ln in ISSUED_LAYERS:
            info = parse_layer(ln)
            tk = TAXON_KOR.get(info["taxon"], info["taxon"]) if info else "?"
            pk = PROG_KOR.get(info["prog"], info["prog"]) if info else "?"
            op = info["op"] if info else None
            print(f"  {ln:42s} {pk:9s} {tk:8s} {info['service'] if info else '-':16s} {op}")
        return
    key = load_key()
    if not key or key.startswith("YOUR_"):
        print("ECOBANK_API_KEY 미설정. 3_ETL/.env 에 ECOBANK_API_KEY=발급키 를 넣으세요.")
        sys.exit(1)
    type_name = sys.argv[2] if len(sys.argv) > 2 else "mv_map_bgts_insect_point"
    bbox      = sys.argv[3] if len(sys.argv) > 3 else SAMPLE_BBOX
    if bbox in ("korea", "KOREA"):
        bbox = KOREA_BBOX
    max_feat  = int(sys.argv[4]) if len(sys.argv) > 4 else 50
    out_fmt   = sys.argv[5] if len(sys.argv) > 5 else None   # 예: application/json
    srs       = sys.argv[6] if len(sys.argv) > 6 else None   # 예: EPSG:4326
    # argv[7:] 중 key=value 토큰은 extra 파라미터로(startIndex/cql_filter 검증)
    extra = {}
    for tok in sys.argv[7:]:
        if "=" in tok:
            k, v = tok.split("=", 1)
            extra[k] = v
    smoke(key, type_name, bbox, max_feat, out_fmt, srs, extra or None)


if __name__ == "__main__":
    main()
