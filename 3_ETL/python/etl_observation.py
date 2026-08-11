# -*- coding: utf-8 -*-
"""
EcoBank 관측 NDJSON → observation_agg.csv (시도 spatial join + obs_count 집계).
설계 근거: 개발계획_v1 §1.3/§1.4 (D2 확정).
- 매칭: spcs_scncenm(학명) → managed_key → ktsn. 미스 시 국명(spcs_korean_nm/lcnm) 폴백.
- 시도: _coords[lon,lat] EPSG:4326 → BND_SIDO_PG point-in-polygon → sido. 폴리곤 밖=미상.
- 연도: examin_year 우선, 없으면 examin_begin_de 시작연도(D5).
- obs_count = COUNT(DISTINCT 좌표) per (ktsn, taxon_group, sido, year, source)  — 종·연도·좌표 고유(D2).
- 월: examin_begin_de 의 월(계절성용) — 시도 집계와 독립된 observation_months_ecobank.csv 로 별도 산출.
- source = 조사사업 코드(bgts/ecpe/ntee/wtl). 미매칭 관측은 집계 제외 + 리포트(§1.5).
사용: python etl_observation.py <ndjson> [<ndjson> ...]
출력: 1_Data/processed/observation_agg.csv  (+ 콘솔 리포트)
"""
import sys, csv, json, time, re
from pathlib import Path
from collections import defaultdict, Counter
from name_overrides import load_overrides
from obs_common import (load_master, resolve_ktsn, _kor, sido_lookup,
                        write_points, parse_ym, write_months)
import fetch_ecobank as fe

BASE = Path(__file__).resolve().parents[2]
PROC = BASE / "1_Data" / "processed"
OUT = PROC / "observation_agg.csv"


def year_of(rec):
    """연도: examin_year → examin_begin_de 순. 습지(wtl) 레이어만 필드명에 wtl_ 접두사가 붙어
    앞의 두 키가 통째로 비므로 wtl_examin_year / wtl_examin_de 를 함께 본다."""
    for k in ("examin_year", "wtl_examin_year"):
        y = (rec.get(k) or "").strip()
        if re.fullmatch(r"\d{4}", y):
            return y
    for k in ("examin_begin_de", "wtl_examin_de"):
        y, _ = parse_ym(rec.get(k))      # Excel 일련번호 환산까지 parse_ym 에 위임
        if y:
            return y
    return ""


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
            # 연도는 examin_year 우선(year_of) · 월은 조사 시작일에서만 얻는다(습지는 wtl_ 접두사)
            _, month = parse_ym(r.get("examin_begin_de") or r.get("wtl_examin_de"))
            obs.append([ktsn, ktsn_tx.get(ktsn, ""), year_of(r), src, c[0], c[1], month])
    n_match = n_override + n_both + n_sci + n_kor
    n_discard = n_all - n_match
    print(f"매칭: 총 {n_all:,} | 매칭 {n_match:,} ({n_match/n_all*100:.1f}%) "
          f"[보정 {n_override:,} · 일치 {n_both:,} · 학명단독 {n_sci:,} · 국명단독 {n_kor:,}] | "
          f"폐기 {n_discard:,} (충돌 {n_conflict:,} · 미매칭 {n_discard-n_conflict:,})  ({time.time()-t1:.1f}s)")

    # 2) 시도 spatial join (고유 좌표만)
    t2 = time.time()
    uniq = sorted({(o[4], o[5]) for o in obs if o[4] is not None})
    coord_sido = sido_lookup(uniq)
    n_out = sum(1 for v in coord_sido.values() if v == "미상")
    print(f"시도조인: 고유좌표 {len(uniq):,} | 시도밖(미상) {n_out:,}  ({time.time()-t2:.1f}s)")

    # 3) 집계: obs_count = COUNT(DISTINCT 좌표) per (ktsn, taxon_group, sido, year, source)
    t3 = time.time()
    grp = defaultdict(set)
    mon = defaultdict(set)              # 계절성용 — grp 와 독립(월을 grp 키에 넣으면 obs_count 가 바뀐다)
    for ktsn, tx, year, src, lon, lat, month in obs:
        sd = coord_sido.get((lon, lat), "미상") if lon is not None else "미상"
        grp[(ktsn, tx, sd, year, src)].add((lon, lat))
        if month:
            mon[(ktsn, tx, src, year, month)].add((lon, lat))
    rows = [{"ktsn": k, "taxon_group": tx, "sido": s, "year": y, "source": sr, "obs_count": len(p)}
            for (k, tx, s, y, sr), p in grp.items()]
    rows.sort(key=lambda r: (r["taxon_group"], r["sido"], r["year"], -r["obs_count"]))
    PROC.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ktsn", "taxon_group", "sido", "year", "source", "obs_count"])
        w.writeheader(); w.writerows(rows)
    print(f"집계: observation_agg 행 {len(rows):,}  ({time.time()-t3:.1f}s) → {OUT.name}")

    # 좌표 보존 점 단위 기본 DB(파생: 위 시도 집계와 카운트 일치) — bioclim 등 점 기반 분석용
    npt = write_points(PROC / "observation_points_ecobank.csv", grp)
    print(f"점 DB: observation_points_ecobank.csv 행 {npt:,}")

    nmo = write_months(PROC / "observation_months_ecobank.csv", mon)
    n_nomonth = sum(1 for o in obs if not o[6])
    print(f"월 집계: observation_months_ecobank.csv 행 {nmo:,} · 월 미상 {n_nomonth:,}/{len(obs):,}")

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
