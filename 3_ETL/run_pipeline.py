# -*- coding: utf-8 -*-
"""
Finding gap 데이터 파이프라인 오케스트레이터 — 재빌드 체인을 순서대로·검증하며 실행.

목적: 6개월 갱신·부분 재빌드를 한 커맨드로. 각 단계는 이름으로 선택 실행 가능(--only/--from/--skip).
R 실행의 Windows 함정(공백경로·인용)은 subprocess 리스트 + `-e source()` 로 회피한다.

이 파이프라인의 범위: 환경·모형 자산 체인(관측 ETL은 스크립트 밖 — DATA_PIPELINE.md 3-A 참조).
각 단계:
  sentinel  : NDVI/NDWI zip → 평문 .tif 로컬 캐시 추출(**.ovr 제외** — 손상 오버뷰가 heap 크래시 유발)
  env_layers: 3_ETL/R/env_layers.R  → species_env_stats·env_national·env_grid·PNG
  species_cells: 3_ETL/R/species_cells.R → species_cells.csv (종별 1km 점유, cid=env_grid 일치)
  cell_sigungu: python/build_cell_sigungu.py → cell_sigungu.csv (셀→시군구, 비율표 분모)
  ndwi_sp   : python/build_ndwi_species.py → ndwi_species.csv (어류+저서무척추)
  cell_water: python/build_cell_water.py → cell_water.csv (수계 격자 마스크)
  env_data  : 5_App/build_env_data.py → species_env.js·env_meta.js
  gap_data  : 5_App/build_gap_data.py → env_grid.js·cells_<T>.js·gap_meta.js
  env_grid_model: 3_ETL/R/env_grid_model.R → env_grid_model.csv (모형용 격자 + bio변수)
  season    : python/build_season.py → species_season.csv (조사노력 보정)
  model     : 3_ETL/R/model_species.R → model_store/ (종별 maxnet 적합)
  model_data: 5_App/build_model_data.py → env_model.js·model_<T>.js·season_<T>.js
  mcp_data  : 7_MCP/build_mcp_data.py → fg_mcp.sqlite (MCP·대화형 참조본)
  fg_load   : Supabase fg_* 재적재 — obff(load_reference.py)+hmqd(char-app load_fg_remote.py)
  dist      : 5_App/build_dist.py --osm-only --out docs → docs/ 정적 배포본

전체 6개월 갱신 체인(관측 ETL은 DATA_PIPELINE.md 3-A 참조):
  관측 ETL(etl_observation·etl_national_park·etl_gbif·build_points_db·build_sigungu_agg)
  → build_demo_data → 이 파이프라인(위 12단계) → build_dist

사용:
  python 3_ETL/run_pipeline.py --list
  python 3_ETL/run_pipeline.py                     # 기본 12단계 모두 실행(sentinel ~ model_data)
  python 3_ETL/run_pipeline.py --only env_layers
  python 3_ETL/run_pipeline.py --from ndwi_sp
  python 3_ETL/run_pipeline.py --only dist         # 배포본만(기본 목록 밖)
"""
import argparse, os, subprocess, sys, time, zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYDIR = REPO / "3_ETL" / "python"
RDIR = REPO / "3_ETL" / "R"
SPATIAL = REPO / "1_Data" / "spatial"
PROC = REPO / "1_Data" / "processed"
APP = REPO / "5_App"
CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "fg_cache" / "sentinel"
RSCRIPT = os.environ.get("RSCRIPT_EXE", r"C:\Program Files\R\R-4.5.0\bin\Rscript.exe")

SENTINEL = [  # (zip, member .tif) — .ovr/.tfw/.aux 는 추출하지 않음(오버뷰 손상 → GDAL heap 크래시)
    ("Sentinel_위성영상의_정규식생지수_NDVI_2024.zip", "S2_NDVI.tif"),
    ("Sentinel_위성영상의_정규물지수_NDWI_2024.zip", "S2_NDWI.tif"),
]


def sh(cmd, cwd=None):
    """리스트 커맨드 실행(shell 미사용 → 공백경로/인용 안전). 실패 시 예외."""
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None, check=True)


def need(path, label):
    p = Path(path)
    if not p.exists():
        sys.exit(f"[검증 실패] {label} 없음: {p}")
    print(f"  ✓ {label}: {p.name}")


# ── 단계 함수 ─────────────────────────────────────────────────────────
def step_sentinel():
    """NDVI/NDWI 평문 .tif 를 로컬 캐시로 추출(없을 때만). .ovr 는 절대 추출하지 않는다."""
    CACHE.mkdir(parents=True, exist_ok=True)
    for zname, member in SENTINEL:
        dst = CACHE / member
        if dst.exists() and dst.stat().st_size > 0:
            print(f"  ✓ 캐시 존재: {member}")
            continue
        zpath = SPATIAL / zname
        need(zpath, f"원본 zip {zname}")
        print(f"  추출 {member} ← {zname}")
        with zipfile.ZipFile(zpath) as z:
            with z.open(member) as src, dst.open("wb") as out:
                while True:
                    buf = src.read(1 << 20)
                    if not buf:
                        break
                    out.write(buf)
    for _, member in SENTINEL:
        need(CACHE / member, f"캐시 {member}")


def step_env_layers():
    """R env_layers.R — 점추출·1km 집계·env_grid·PNG. 진행로그는 LOCALAPPDATA/fg_cache/env_layers_run.log."""
    script = (RDIR / "env_layers.R").as_posix()
    sh([RSCRIPT, "-e", f"source('{script}')"])
    for f in ("species_env_stats.csv", "env_national.csv", "env_grid.csv"):
        need(PROC / f, f)


def step_species_cells():
    """R species_cells.R — obs_points→agref 셀 매핑(cid=env_grid 일치), 종별 점유+최종연도.
    Sentinel 미접촉(bio01 read만). 진행로그 LOCALAPPDATA/fg_cache/species_cells_run.log."""
    script = (RDIR / "species_cells.R").as_posix()
    sh([RSCRIPT, "-e", f"source('{script}')"])
    need(PROC / "species_cells.csv", "species_cells.csv")


def step_cell_sigungu():
    """env_grid 1km 셀 → 시군구 코드(적합지 비율표·줌 분모). geopandas(build_sigungu_agg 재사용)."""
    sh([sys.executable, PYDIR / "build_cell_sigungu.py"])
    need(PROC / "cell_sigungu.csv", "cell_sigungu.csv")


def step_ndwi_sp():
    sh([sys.executable, PYDIR / "build_ndwi_species.py"])
    need(PROC / "ndwi_species.csv", "ndwi_species.csv")


def step_cell_water():
    """수계 격자 — 4_References/<시도>/Channel Network shp 통합 × 1km 셀 교차.
    어류·저서무척추의 최종 적합지 판정을 물길 지나는 셀로 자르는 마스크(env_grid 는 건드리지 않는다)."""
    sh([sys.executable, PYDIR / "build_cell_water.py"])
    need(PROC / "cell_water.csv", "cell_water.csv")


def step_env_data():
    sh([sys.executable, APP / "build_env_data.py"])
    need(APP / "demo" / "data" / "species_env.js", "species_env.js")


def step_gap_data():
    """발견공백 A 클라 자산 — env_grid.js·cells_<T>.js·gap_meta.js (env_layers·species_cells·cell_sigungu·ndwi_sp 이후)."""
    import datetime
    sh([sys.executable, APP / "build_gap_data.py", datetime.date.today().isoformat()])
    need(APP / "demo" / "data" / "env_grid.js", "env_grid.js")
    need(APP / "demo" / "data" / "gap_meta.js", "gap_meta.js")


def step_env_grid_model():
    """관찰 추천도 모델용 격자 — env_grid.csv + bio03·bio14·bio18, 배포 정밀도로 반올림.
    env_grid.csv 보다 최신이면 건너뛴다."""
    script = (RDIR / "env_grid_model.R").as_posix()
    sh([RSCRIPT, "-e", f"source('{script}')"])
    need(PROC / "env_grid_model.csv", "env_grid_model.csv")


def step_season():
    """종별 계절 적합성 — obs_month 를 (자료원×분류군) 조사 노력으로 보정한 12개월 점수."""
    sh([sys.executable, PYDIR / "build_season.py"])
    need(PROC / "species_season.csv", "species_season.csv")


def step_model():
    """종별 maxnet 증분 적합 + 4겹 CV. 점유 셀 지문이 같은 종은 건너뛰므로 갱신분만 다시 돈다.
    변수·특징·배경수·겹수·구간 규칙이나 환경 격자가 바뀌면 cfg 해시가 달라져 전량 재적합한다."""
    script = (RDIR / "model_species.R").as_posix()
    sh([RSCRIPT, "-e", f"source('{script}')"])
    need(PROC / "model_store", "model_store/")


def step_model_data():
    """관찰 추천도 클라 자산 — env_model.js·model_<T>.js·season_<T>.js·model_meta.js.
    공간 축은 종별 임계값(thr_cv)이 정해진 종을 모두 싣고, 교차검증 AUC 로 매긴
    신뢰 등급을 함께 내보낸다. 임계값이 없는 종만 계절 축으로 남는다."""
    import datetime
    sh([sys.executable, APP / "build_model_data.py", datetime.date.today().isoformat()])
    need(APP / "demo" / "data" / "model_meta.js", "model_meta.js")
    need(APP / "demo" / "data" / "env_model.js", "env_model.js")


def step_dist():
    """공개 배포본 — 반드시 --osm-only(vworld 키 미주입, docs/config.js 빈 키 유지)."""
    sh([sys.executable, APP / "build_dist.py", "--osm-only", "--out", "docs"])
    need(REPO / "docs" / "index.html", "docs/index.html")


def step_mcp_data():
    """MCP·대화형 참조 SQLite 재구움 — 관측 롤업(species_region)·종 마스터가 바뀌면 함께 새로 굽는다."""
    sh([sys.executable, REPO / "7_MCP" / "build_mcp_data.py"], cwd=REPO)
    need(REPO / "7_MCP" / "data" / "fg_mcp.sqlite", "fg_mcp.sqlite")


def step_fg_load():
    """대화형 백엔드 fg_* 재적재 — obff(5_App chat)와 hmqd(char-app char-chat) 둘 다.
    한쪽이 실패해도 다른 쪽은 마저 시도하되, 실패가 있으면 예외로 끝낸다 —
    조용히 exit 0 이면 스케줄러가 성공으로 오판해 옛 데이터가 무기한 방치된다."""
    errs = []
    try:
        sh([sys.executable, APP / "supabase" / "load_reference.py"], cwd=REPO)
    except Exception as e:
        errs.append(f"obff: {e}")
        print(f"  (경고) obff fg_* 적재 실패: {e}")
    hmqd = REPO / "char-app" / "scripts" / "load_fg_remote.py"
    if hmqd.exists():
        try:
            sh([sys.executable, hmqd], cwd=REPO)
        except Exception as e:
            errs.append(f"hmqd: {e}")
            print(f"  (경고) hmqd fg_* 적재 실패: {e}")
    if errs:
        raise RuntimeError("fg_* 적재 실패 — 해당 백엔드가 옛 데이터로 남았다: " + "; ".join(errs))


STEPS = [  # 순서 = 의존관계
    ("sentinel", "NDVI/NDWI zip→평문 .tif 캐시(.ovr 제외)", step_sentinel),
    ("env_layers", "env_layers.R (점추출·1km 집계·env_grid·PNG)", step_env_layers),
    ("species_cells", "species_cells.R (종별 1km 점유+최종연도, cid=env_grid)", step_species_cells),
    ("cell_sigungu", "build_cell_sigungu.py (셀→시군구 매핑, 비율표 분모)", step_cell_sigungu),
    ("ndwi_sp", "build_ndwi_species.py (어류+저서무척추)", step_ndwi_sp),
    ("cell_water", "build_cell_water.py (수계 격자 마스크, 하천망×1km 셀)", step_cell_water),
    ("env_data", "build_env_data.py (species_env.js·env_meta.js)", step_env_data),
    ("gap_data", "build_gap_data.py (env_grid.js·cells_<T>.js·gap_meta.js)", step_gap_data),
    ("env_grid_model", "env_grid_model.R (모델 격자 + bio03·bio14·bio18)", step_env_grid_model),
    ("season", "build_season.py (종별 12개월 점수, 조사노력 보정)", step_season),
    ("model", "model_species.R (종별 maxnet 증분 적합 + 4겹 CV)", step_model),
    ("model_data", "build_model_data.py (env_model.js·model_<T>.js·season_<T>.js)", step_model_data),
    ("mcp_data", "7_MCP/build_mcp_data.py (fg_mcp.sqlite 재구움)", step_mcp_data),
    ("fg_load", "Supabase fg_* 재적재 (obff load_reference + hmqd load_fg_remote)", step_fg_load),
    ("dist", "build_dist.py --osm-only --out docs (배포본)", step_dist),
]
# dist 는 명시 요청 시만. 나머지가 발견공백 A + 관찰 추천도 데이터 재빌드 체인.
# season 은 observations.sqlite 의 obs_month 만 쓰므로 앞 단계와 독립이다(관측 ETL 이후면 언제든).
# model 은 species_cells·env_grid_model 이후여야 한다.
# mcp_data→fg_load 는 대화형 백엔드(fg_*) 동기화 — 6개월 갱신 때 지도(bin)와 대화가 같은 판이 되게 한다.
DEFAULT = ["sentinel", "env_layers", "species_cells", "cell_sigungu", "ndwi_sp", "cell_water",
           "env_data", "gap_data", "env_grid_model", "season", "model", "model_data",
           "mcp_data", "fg_load"]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Finding gap 데이터 파이프라인")
    ap.add_argument("--list", action="store_true", help="단계 목록만 출력")
    ap.add_argument("--only", nargs="+", metavar="STEP", help="지정 단계만 실행")
    ap.add_argument("--from", dest="from_", metavar="STEP", help="해당 단계부터 끝까지")
    ap.add_argument("--skip", nargs="+", metavar="STEP", default=[], help="제외할 단계")
    a = ap.parse_args()
    names = [n for n, _, _ in STEPS]

    if a.list:
        print("단계(순서):")
        for n, d, _ in STEPS:
            tag = " [기본]" if n in DEFAULT else ""
            print(f"  {n:11s} {d}{tag}")
        return

    if a.only:
        run = [n for n in a.only if n in names] or sys.exit(f"알 수 없는 단계: {a.only}")
    elif a.from_:
        if a.from_ not in names:
            sys.exit(f"알 수 없는 단계: {a.from_}")
        run = names[names.index(a.from_):]
    else:
        run = list(DEFAULT)
    run = [n for n in run if n not in a.skip]

    fn = {n: f for n, _, f in STEPS}
    t0 = time.time()
    print(f"파이프라인 실행: {' → '.join(run)}\n")
    for n in run:
        print(f"[{n}] {dict((x, y) for x, y, _ in STEPS)[n]}")
        ts = time.time()
        fn[n]()
        print(f"  완료 ({time.time()-ts:.1f}s)\n")
    print(f"전체 완료 ({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
