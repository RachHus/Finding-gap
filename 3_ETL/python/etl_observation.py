# -*- coding: utf-8 -*-
"""
EcoBank 관측 NDJSON → observation_agg.csv (시도 spatial join + obs_count 집계).
설계 근거: 개발계획_v1 §1.3/§1.4 (D2 확정).
- 매칭: spcs_scncenm(학명) → managed_key → ktsn. 미스 시 국명(spcs_korean_nm/lcnm) 폴백.
- 시도: _coords[lon,lat] EPSG:4326 → BND_SIDO_PG point-in-polygon → sido. 폴리곤 밖=미상.
- 연도: examin_year 우선, 없으면 examin_begin_de 시작연도(D5).
- obs_count = COUNT(DISTINCT 좌표) per (ktsn, taxon_group, sido, year, source)  — 종·연도·좌표 고유(D2).
- source = 조사사업 코드(bgts/ecpe/ntee/wtl). 미매칭 관측은 집계 제외 + 리포트(§1.5).
사용: python etl_observation.py <ndjson> [<ndjson> ...]
출력: 1_Data/processed/observation_agg.csv  (+ 콘솔 리포트)
"""
import sys, csv, json, time, re
from pathlib import Path
from collections import defaultdict, Counter
from taxon_key import managed_key
from name_overrides import load_overrides, load_aliases
import fetch_ecobank as fe

BASE = Path(__file__).resolve().parents[2]
PROC = BASE / "1_Data" / "processed"
MASTER = PROC / "ktsn_master.csv"
SIDO_SHP = BASE / "1_Data" / "spatial" / "BND_SIDO_PG" / "BND_SIDO_PG.shp"
OUT = PROC / "observation_agg.csv"


def _kor(s):
    return re.sub(r"\s+", "", s or "")


def resolve_ktsn(sci, kor, sciname, kn, ov_sci=None, ov_kor=None):
    """학명·국명(정규화키)을 각각 ktsn으로 해석 후 충돌 판정(확정불가 폐기). 보정 매핑(override) 최우선.
    반환: (ktsn|None, how) — how ∈ {'override','both','sci','kor','conflict','none'}.
      override = ktsn_name_overrides.csv 등록 이름 → 지정 ktsn 확정(충돌보다 우선)
      conflict = 학명·국명이 서로 다른 ktsn을 가리킴 → 폐기(국립공원 ETL과 동일 규칙)."""
    if ov_sci or ov_kor:
        ovk = (ov_sci or {}).get(managed_key(sciname)) if sciname else None
        if not ovk and kn:
            ovk = (ov_kor or {}).get(kn)
        if ovk:
            return ovk, "override"
    ks = sci.get(managed_key(sciname)) if sciname else None
    kk = kor.get(kn) if kn else None
    if ks and kk:
        return (ks, "both") if ks == kk else (None, "conflict")
    if ks:
        return ks, "sci"
    if kk:
        return kk, "kor"
    return None, "none"


def load_master():
    """ktsn_master → (학명키→ktsn, 국명→ktsn, ktsn→taxon_group). 변종/품종 별칭(alias)을 gap-fill."""
    sci, kor, tx = {}, {}, {}
    for r in csv.DictReader(MASTER.open(encoding="utf-8-sig")):
        k = r["ktsn"]
        mk = (r.get("match_key") or "").strip()
        if mk and mk not in sci:
            sci[mk] = k
        kn = _kor(r.get("korean_name"))
        if kn and kn not in kor:
            kor[kn] = k
        tx[k] = r.get("taxon_group") or ""
    al_sci, al_kor = load_aliases()
    for k2, v in al_sci.items():
        sci.setdefault(k2, v)
    for k2, v in al_kor.items():
        kor.setdefault(k2, v)
    return sci, kor, tx


def year_of(rec):
    y = (rec.get("examin_year") or "").strip()
    if re.fullmatch(r"\d{4}", y):
        return y
    m = re.match(r"(\d{4})", (rec.get("examin_begin_de") or "").strip())
    return m.group(1) if m else ""


def source_of(path):
    """NDJSON 파일명 → 조사사업 코드(bgts/ecpe/ntee/wtl)."""
    stem = path.stem.replace("ecobank_", "")
    info = fe.parse_layer(stem)
    return (info or {}).get("prog") or "etc"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    files = [Path(a) for a in sys.argv[1:]] or sys.exit("ndjson 경로 인자 필요")

    t0 = time.time()
    sci, kor, ktsn_tx = load_master()
    ov_sci, ov_kor = load_overrides()
    print(f"마스터 로드: 학명키 {len(sci):,} · 국명 {len(kor):,} · ktsn {len(ktsn_tx):,} | "
          f"보정매핑 학명 {len(ov_sci)} · 국명 {len(ov_kor)}  ({time.time()-t0:.1f}s)")

    # 1) 매칭 + 연도/좌표/source 추출
    t1 = time.time()
    obs = []                # (ktsn, taxon_group, sido?, year, source, lon, lat)  — sido는 2단계 후 채움
    n_all = n_override = n_both = n_sci = n_kor = n_conflict = 0
    unmatched = Counter()
    for fp in files:
        src = source_of(fp)
        for line in fp.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            n_all += 1
            sciname = (r.get("spcs_scncenm") or "").strip()
            kn = _kor(r.get("spcs_korean_nm") or r.get("spcs_lcnm"))
            ktsn, how = resolve_ktsn(sci, kor, sciname, kn, ov_sci, ov_kor)
            if how == "override":
                n_override += 1
            elif how == "both":
                n_both += 1
            elif how == "sci":
                n_sci += 1
            elif how == "kor":
                n_kor += 1
            else:                                   # conflict | none → 폐기
                if how == "conflict":
                    n_conflict += 1
                unmatched[sciname or kn or "(빈값)"] += 1
                continue
            c = r.get("_coords") or [None, None]
            obs.append([ktsn, ktsn_tx.get(ktsn, ""), year_of(r), src, c[0], c[1]])
    n_match = n_override + n_both + n_sci + n_kor
    n_discard = n_all - n_match
    print(f"매칭: 총 {n_all:,} | 매칭 {n_match:,} ({n_match/n_all*100:.1f}%) "
          f"[보정 {n_override:,} · 일치 {n_both:,} · 학명단독 {n_sci:,} · 국명단독 {n_kor:,}] | "
          f"폐기 {n_discard:,} (충돌 {n_conflict:,} · 미매칭 {n_discard-n_conflict:,})  ({time.time()-t1:.1f}s)")

    # 2) 시도 spatial join (고유 좌표만)
    import geopandas as gpd
    from shapely.geometry import Point
    t2 = time.time()
    uniq = sorted({(o[4], o[5]) for o in obs if o[4] is not None})
    sido_gdf = gpd.read_file(SIDO_SHP)
    name_col = next((c for c in sido_gdf.columns
                     if c.upper() in ("CTP_KOR_NM", "SIDO_NM", "CTPRVN_NM", "SIDONM")), None)
    if name_col is None:
        name_col = next(c for c in sido_gdf.columns if sido_gdf[c].dtype == object and c != "geometry")
    sido_gdf = sido_gdf.to_crs(4326)[[name_col, "geometry"]].rename(columns={name_col: "sido"})
    pts = gpd.GeoDataFrame({"i": range(len(uniq))},
                           geometry=[Point(lo, la) for lo, la in uniq], crs=4326)
    joined = gpd.sjoin(pts, sido_gdf, how="left", predicate="within")
    coord_sido = {}
    for i, sd in zip(joined["i"], joined["sido"]):
        coord_sido.setdefault(uniq[i], sd if isinstance(sd, str) else "미상")
    n_out = sum(1 for v in coord_sido.values() if v == "미상")
    print(f"시도조인: 고유좌표 {len(uniq):,} | 시도밖(미상) {n_out:,}  ({time.time()-t2:.1f}s)")

    # 3) 집계: obs_count = COUNT(DISTINCT 좌표) per (ktsn, taxon_group, sido, year, source)
    t3 = time.time()
    grp = defaultdict(set)
    for ktsn, tx, year, src, lon, lat in obs:
        sd = coord_sido.get((lon, lat), "미상") if lon is not None else "미상"
        grp[(ktsn, tx, sd, year, src)].add((lon, lat))
    rows = [{"ktsn": k, "taxon_group": tx, "sido": s, "year": y, "source": sr, "obs_count": len(p)}
            for (k, tx, s, y, sr), p in grp.items()]
    rows.sort(key=lambda r: (r["taxon_group"], r["sido"], r["year"], -r["obs_count"]))
    PROC.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ktsn", "taxon_group", "sido", "year", "source", "obs_count"])
        w.writeheader(); w.writerows(rows)
    print(f"집계: observation_agg 행 {len(rows):,}  ({time.time()-t3:.1f}s) → {OUT.name}")

    # 4) 리포트
    yr = sorted({r["year"] for r in rows if r["year"]})
    print(f"  연도 {yr[0]}~{yr[-1]}({len(yr)}) | 시도 {len({r['sido'] for r in rows})} | source {sorted({r['source'] for r in rows})}")
    for tx in sorted({r["taxon_group"] for r in rows}):
        sp = len({r["ktsn"] for r in rows if r["taxon_group"] == tx})
        print(f"  [{tx}] 관측 종수 {sp}")
    if unmatched:
        print(f"  미매칭 top: {[n for n,_ in unmatched.most_common(8)]}")
    print(f"\n총 ETL 소요 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
