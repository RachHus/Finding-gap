"""종 미디어 인덱스 병합

산출: 5_App/demo/data/media_<T>.js (분류군별 미디어, 브라우저용 지연 로드),
      5_App/demo/data/rep_<T>.js (분류군별 대표 이미지, 종 카드용),
      5_App/demo/data/species_media.json (디버그용 전체 레코드),
      5_App/demo/data/media_meta.js (분류군별 종 수)
입력: 1_Data/processed/media_nibr.json (build_media_nibr.py 산출),
      1_Data/processed/media_inat.json (build_media_inat.py 산출),
      1_Data/processed/ktsn_master.csv (분류체계: 속·과·목)

이 파일은 NIBR·iNaturalist 두 소스의 미디어를 병합해 웹 클라이언트가 쓸 수 있도록
정리한다. 퀴즈와 종 상세 화면에서 종별 사진·세밀화를 보여주는 데 쓰인다.

처리 흐름:
1. media_nibr.json + media_inat.json 을 종(ktsn)별로 합침
2. NIBR 우선 (공식 자료), 그 다음 iNaturalist
3. 중복 제거 (full URL 기준)
4. 분류군별로 분할해 별도 파일로 저장 (퀴즈가 해당 분류군만 지연 로드)
5. 대표 이미지(종 카드용)를 별도 추출해 rep_<T>.js 생성

옵션:
  --rep-only: 대표 이미지만 다시 생성 (무거운 media_<T>.js는 유지)

실행: 손으로 따로 실행 (run_pipeline.py 미포함, 하지만 NIBR·iNat 수집 이후)
배포: build_dist.py 의 DATA_GLOBS "media_*.js", "rep_*.js" 에서 자동 포함됨
참고: demo/data/species_media.json 은 웹에서 안 쓰는 디버그용 파일이지만,
      build_media_inat.py / build_media_nibr.py 의 입력이 아니므로 지워도 된다.
"""
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 프로젝트 루트
PROC = ROOT / "1_Data" / "processed"
OUT_DIR = ROOT / "5_App" / "demo" / "data"
MASTER = PROC / "ktsn_master.csv"                       # 분류체계(속/과/목)

SOURCES = [
    ("nibr", PROC / "media_nibr.json"),                # 공식 우선
    ("inat", PROC / "media_inat.json"),
]


def load(path):
    if not path.exists():
        print(f"  - {path.name}: 없음(건너뜀)")
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"  - {path.name}: {len(data)}종")
    return data


NIBR_PREFIX = "https://species.nibr.go.kr/gwsvc/digital/api/v1/minio/view?filePath="
REP_KINDS = ["photo", "drawing", "specimen"]      # 대표 이미지 선호 순서(소리·영상·3d 는 제외)


def build_rep(merged, groups, gen):
    """종 카드 대표 이미지 — rep_<T>.js(분류군별 지연 로드).

    media_<T>.js 는 종당 이미지를 전부 담아 곤충만 7MB 다. 카드는 한 장만 쓰므로
    종당 한 건으로 줄인 별도 자산을 낸다. NIBR URL 은 접두어가 모두 같아 뒷부분만,
    촬영자·라이선스는 419종뿐이라 표 색인으로 담는다.
    """
    def fname(t):
        return "rep_" + re.sub(r"[^A-Za-z0-9]", "_", t or "NA") + ".js"

    out = {}
    for t, ks in sorted(groups.items()):
        bys, lics, m = {}, {}, {}
        for k in ks:
            recs = merged[k]
            pick = next((r for kind in REP_KINDS for r in recs
                         if r.get("type") == kind and str(r.get("thumb", "")).startswith(NIBR_PREFIX)), None)
            if pick is None:
                continue
            by = pick.get("by") or ""
            lic = pick.get("lic") or ""
            m[k] = [pick["thumb"][len(NIBR_PREFIX):],
                    bys.setdefault(by, len(bys)),
                    lics.setdefault(lic, len(lics)),
                    REP_KINDS.index(pick["type"])]
        body = json.dumps({"g": gen, "t": t,
                           "p": list(bys), "l": list(lics), "m": m},
                          ensure_ascii=False, separators=(",", ":"))
        path = OUT_DIR / fname(t)
        path.write_text("window.__SPREP__=window.__SPREP__||{};window.__SPREP__[" +
                        json.dumps(t, ensure_ascii=False) + "]=" + body + ";\n", encoding="utf-8")
        out[t] = (len(m), path.stat().st_size)

    print(f"[출력] 분류군별 rep_<T>.js {len(out)}개 (종 카드 대표 이미지)")
    for t in sorted(out):
        n, sz = out[t]
        print(f"    {fname(t)}: {n}종 · {sz/1024:.0f} KB")


def main():
    print("[병합] 소스 로드")
    per_source = [(name, load(path)) for name, path in SOURCES]

    merged = {}                                        # ktsn -> [record]
    for name, data in per_source:                      # SOURCES 순서 = 우선순위
        for ktsn, recs in data.items():
            bucket = merged.setdefault(ktsn, [])
            seen = {r.get("full") for r in bucket}
            for r in recs:
                if r.get("full") in seen:
                    continue
                seen.add(r.get("full"))
                bucket.append(r)

    total_photos = sum(len(v) for v in merged.values())
    print(f"[병합] 종 {len(merged)} · 미디어 {total_photos}")

    # 분류체계 부착(퀴즈 오답: 속→과 폴백) + 분류군(분할 키). tax[ktsn]=[genus, family, order]
    tax = {}
    tgmap = {}
    if MASTER.exists():
        want = set(merged.keys())
        with open(MASTER, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                k = row.get("ktsn")
                if k in want:
                    tax[k] = [row.get("genus_la", ""), row.get("family_la", ""), row.get("order_la", "")]
                    tgmap[k] = row.get("taxon_group", "")
        print(f"[병합] 분류체계 부착: {len(tax)}종")
    else:
        print("  - ktsn_master.csv 없음 → tax 생략")

    gen = date.today().isoformat()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    groups = {}
    for k in merged:
        groups.setdefault(tgmap.get(k) or "NA", []).append(k)

    if "--rep-only" in sys.argv:                        # 대표 이미지만 재생성(무거운 media_<T>.js 는 건드리지 않음)
        build_rep(merged, groups, gen)
        return 0

    # 전체 결합본(기록·디버그용 json만; 브라우저는 분류군별 분할 로드)
    (OUT_DIR / "species_media.json").write_text(
        json.dumps({"generated": gen, "m": merged, "tax": tax}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")

    # 분류군별 분할: media_<T>.js — 퀴즈가 해당 분류군만 지연 로드(6MB 단일 로드 방지)
    def fname(t):
        return "media_" + re.sub(r"[^A-Za-z0-9]", "_", t or "NA") + ".js"
    meta = {}
    for t, ks in sorted(groups.items()):
        body = json.dumps({"generated": gen, "t": t,
                           "m": {k: merged[k] for k in ks},
                           "tax": {k: tax[k] for k in ks if k in tax}},
                          ensure_ascii=False, separators=(",", ":"))
        (OUT_DIR / fname(t)).write_text("window.__SPMEDIA__=" + body + ";\n", encoding="utf-8")
        meta[t] = len(ks)
    (OUT_DIR / "media_meta.js").write_text(
        "window.__SPMEDIA_META__=" + json.dumps({"generated": gen, "taxa": meta},
                                                ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8")

    # 스테일 결합본(.js, 6MB) 제거 — 더 이상 미사용
    stale = OUT_DIR / "species_media.js"
    if stale.exists():
        stale.unlink()

    print(f"[출력] 분류군별 media_<T>.js {len(meta)}개 + media_meta.js")
    for t in sorted(meta):
        print(f"    {fname(t)}: {meta[t]}종")

    build_rep(merged, groups, gen)

    if not merged:
        print("경고: 병합 결과가 비었습니다(입력 json 확인).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
