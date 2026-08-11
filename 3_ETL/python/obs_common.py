# -*- coding: utf-8 -*-
"""
관측 ETL 공통 모듈 — EcoBank(etl_observation)·국립공원(etl_national_park)·GBIF(etl_gbif) 가
공유하는 마스터 로드·이름 매칭·시도 spatial join 을 한곳에 모은다.

- load_master()      : ktsn_master + 변종/품종 별칭(alias) → (학명키→ktsn, 국명→ktsn, ktsn→taxon_group)
- resolve_ktsn(...)  : 학명·국명을 각각 ktsn 으로 해석 후 충돌 판정(확정불가 폐기), 보정 매핑(override) 최우선
- sido_lookup(...)   : 고유 (lon,lat) 목록 → {(lon,lat): sido명}  (BND_SIDO_PG point-in-polygon, 폴리곤 밖=미상)
- parse_ym(s)        : 조사일자 → (연 4자리, 월 1~12|None). YYYY-MM-DD · M/D/YYYY 공용
- write_months(...)  : 월별 집계 CSV (계절성 산출용; 시도 집계·점 DB 와 독립)
- _kor(s)            : 국명 정규화(공백 제거; 멱등)

세 ETL 의 source/스키마는 동일(ktsn,taxon_group,sido,year,source,obs_count) → build_demo_data 가 union.
"""
import re
import csv
from datetime import date, timedelta
from pathlib import Path

from taxon_key import managed_key
from name_overrides import load_aliases

BASE = Path(__file__).resolve().parents[2]
PROC = BASE / "1_Data" / "processed"
MASTER = PROC / "ktsn_master.csv"
SIDO_SHP = BASE / "1_Data" / "spatial" / "BND_SIDO_PG" / "BND_SIDO_PG.shp"


def _kor(s):
    """국명 정규화: 공백 제거(멱등 — 이미 정규화된 값에 다시 적용해도 동일)."""
    return re.sub(r"\s+", "", s or "")


_YMD = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_MDY = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_EXCEL_EPOCH = date(1899, 12, 30)      # Excel 1900 날짜계 기준일


def parse_ym(s):
    """조사일자 → (연 4자리 문자열, 월 1~12 int|None). 파싱 실패 시 ('', None).
    EcoBank examin_begin_de·GBIF eventDate·국립공원 zip 은 YYYY-MM-DD,
    국립공원 2024 csv 만 M/D/YYYY — 세 ETL 이 같은 규칙을 쓰도록 여기 둔다.
    연도만 있고 월이 없는 값(예: '2019')은 ('2019', None) — 계절 집계에서 제외되고 연도 집계는 그대로 살아난다.

    생태계정밀조사 저서무척추 레이어는 날짜가 Excel 일련번호(예: '42131' = 2015-05-07)로 내려온다.
    앞 4자리를 연도로 읽으면 4213년이 되므로 5자리 정수는 일련번호로 환산한다
    (4자리는 연도 그 자체라 건드리지 않는다)."""
    s = (s or "").strip()
    if not s:
        return "", None
    if len(s) == 5 and s.isdigit():
        d = _EXCEL_EPOCH + timedelta(days=int(s))
        return str(d.year), d.month
    m = _YMD.match(s)
    if m:
        mo = int(m.group(2))
        return m.group(1), (mo if 1 <= mo <= 12 else None)
    m = _MDY.match(s)
    if m:
        mo = int(m.group(1))
        return m.group(3), (mo if 1 <= mo <= 12 else None)
    m = re.search(r"(\d{4})", s)
    return (m.group(1) if m else ""), None


def load_master(master=MASTER):
    """ktsn_master → (학명키→ktsn, 국명→ktsn, ktsn→taxon_group). 변종/품종 별칭(alias)을 gap-fill."""
    sci, kor, tx = {}, {}, {}
    for r in csv.DictReader(master.open(encoding="utf-8-sig")):
        k = r["ktsn"]
        mk = (r.get("match_key") or "").strip()
        if mk and mk not in sci:
            sci[mk] = k
        kn = _kor(r.get("korean_name"))
        if kn and kn not in kor:
            kor[kn] = k
        tx[k] = r.get("taxon_group") or ""
    # 별칭 흡수(정명 우선 — 이미 있는 키는 덮어쓰지 않음)
    al_sci, al_kor = load_aliases()
    for k2, v in al_sci.items():
        sci.setdefault(k2, v)
    for k2, v in al_kor.items():
        kor.setdefault(k2, v)
    return sci, kor, tx


def resolve_ktsn(sci, kor, sciname, kor_name, ov_sci=None, ov_kor=None):
    """학명·국명을 각각 ktsn 으로 해석한 뒤 충돌 판정(확정불가 폐기). 보정 매핑(override)이 최우선.
    국명은 내부에서 _kor 로 정규화(멱등 — 호출부가 이미 정규화해 넘겨도 무방). kor_name=None 이면 학명 단독.
    반환: (ktsn|None, how) — how ∈ {'override','both','sci','kor','conflict','none'}.
      override : 보정 매핑 등록 이름(정명 재배치·종분할) → 지정 ktsn 확정(충돌보다 우선)
      both     : 학명·국명이 같은 ktsn → 매칭(가장 신뢰)
      sci/kor  : 한쪽만 해석됨 → 그것으로 매칭
      conflict : 둘 다 해석되나 서로 다른 ktsn → 확정불가 → 폐기
      none     : 둘 다 미해석 → 미매칭
    """
    kn = _kor(kor_name)
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


def sido_lookup(uniq_coords, shp=SIDO_SHP):
    """정렬된 고유 (lon,lat) 목록 → {(lon,lat): sido명}. BND_SIDO_PG point-in-polygon, 폴리곤 밖/실패=미상.
    geopandas/shapely 는 호출 시점에 import(가벼운 단계에서 불필요한 의존 회피)."""
    import geopandas as gpd
    from shapely.geometry import Point
    gdf = gpd.read_file(shp)
    name_col = next((c for c in gdf.columns
                     if c.upper() in ("CTP_KOR_NM", "SIDO_NM", "CTPRVN_NM", "SIDONM")), None)
    if name_col is None:
        name_col = next(c for c in gdf.columns if gdf[c].dtype == object and c != "geometry")
    gdf = gdf.to_crs(4326)[[name_col, "geometry"]].rename(columns={name_col: "sido"})
    pts = gpd.GeoDataFrame({"i": range(len(uniq_coords))},
                           geometry=[Point(lo, la) for lo, la in uniq_coords], crs=4326)
    joined = gpd.sjoin(pts, gdf, how="left", predicate="within")
    coord_sido = {}
    for i, sd in zip(joined["i"], joined["sido"]):
        coord_sido.setdefault(uniq_coords[i], sd if isinstance(sd, str) else "미상")
    return coord_sido


def write_points(out_path, grp):
    """좌표 보존 점 단위 기본 DB의 기반 — 집계용 grp{(ktsn,taxon_group,sido,year,source): set((lon,lat))}
    를 고유 좌표 1개당 1행으로 펼쳐 CSV(ktsn,taxon_group,source,year,sido,lon,lat)로 쓴다.
    이 점들을 (ktsn,taxon_group,sido,year,source)로 세면 obs_count 와 정확히 동일 → 시도 집계가 점 DB에서 파생된다.
    무좌표(lon=None)는 lon/lat 빈칸으로 보존(미상 시도). 반환: 기록 행 수."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ktsn", "taxon_group", "source", "year", "sido", "lon", "lat"])
        for (ktsn, tx, sido, year, src), coords in grp.items():
            for (lon, lat) in coords:
                w.writerow([ktsn, tx, src, year, sido,
                            "" if lon is None else lon, "" if lat is None else lat])
                n += 1
    return n


def write_months(out_path, mon):
    """계절성 산출용 월별 집계 — mon{(ktsn,taxon_group,source,year,month): set((lon,lat))} 를
    CSV(ktsn,taxon_group,source,year,month,n)로 쓴다. n 은 고유 좌표 수로, obs_count 와 같은 셈법이다.

    시도 집계(observation_*.csv)·점 DB(observation_points_*.csv)와 완전히 독립된 산출물이다.
    월을 좌표 dedup 키에 넣으면 같은 지점을 다른 달에 본 관측이 2건으로 갈라져 obs_count 가 바뀌고,
    그러면 발견/미발견 판정 자체가 달라진다 — 그래서 기존 집계는 건드리지 않고 옆에 따로 쌓는다.
    월을 못 읽은 기록(month=None)은 여기서 빠질 뿐 기존 집계에는 그대로 남는다. 반환: 기록 행 수."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ktsn", "taxon_group", "source", "year", "month", "n"])
        for (ktsn, tx, src, year, month), coords in mon.items():
            w.writerow([ktsn, tx, src, year, month, len(coords)])
            n += 1
    return n
