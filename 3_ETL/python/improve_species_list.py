# -*- coding: utf-8 -*-
"""
서비스 대상 종 목록 개선 — MBRIS 해양종 제외 + 어류 관측기록 필터링.

입력:
  - 1_Data/processed/ktsn_master.csv (utf-8-sig)
    - 컬럼: ktsn, scientific_name, match_key, korean_name, taxon_group, ...
  - 1_Data/processed/mbris_marine.csv (utf-8-sig)
    - 컬럼: scientific_name, managed_key, korean_name, family, raw
  - 1_Data/processed/observation_agg.csv (utf-8-sig; required)
  - 1_Data/processed/observation_nps.csv (utf-8-sig; optional — 있으면 합침)

규칙(육상 생태계 종 위주):
  - MM (포유류): 해양포유류(분류학 Cetacea·기각/해우 과 + MBRIS) → False, exclude_reason=marine_mammal
  - -P (어류): 해양(MBRIS)∧무기록∧비적색목록 어류만 → False, exclude_reason=marine_fish_unrecorded
              (담수·관측종·국가적색목록 평가 어류는 유지)
  - UC (미삭동물): 멍게·미더덕 등 해양 피낭동물 → 전량 False, exclude_reason=tunicate_marine
  - 그 외: in_service=True, exclude_reason=''

산출물:
  - 1_Data/processed/species_service_flags.csv (utf-8-sig)
    - 컬럼: ktsn, taxon_group, korean_name, scientific_name, in_service, exclude_reason
  - 콘솔: 분류군별 집계 + 서비스 종수 총합

사용법:
  python improve_species_list.py
"""
import sys
import csv
import json
from pathlib import Path
from collections import defaultdict
from taxon_key import managed_key

BASE = Path(__file__).resolve().parents[2]
PROC = BASE / "1_Data" / "processed"

MASTER = PROC / "ktsn_master.csv"
MBRIS = PROC / "mbris_marine.csv"
OBS_AGG = PROC / "observation_agg.csv"
OBS_NPS = PROC / "observation_nps.csv"
OBS_GBIF = PROC / "observation_gbif.csv"   # GBIF 적재 시(현재 미적재) 자동 포함
OUT = PROC / "species_service_flags.csv"

# 해양 포유류 분류학적 식별(MBRIS API 미응답 시 폴백 — 육상 생태계 종 위주로 서비스).
#   Cetacea(고래목) 전체 + 기각류·해우류 과(family)는 해양 포유류.
MARINE_MM_ORDERS = {"Cetacea"}
MARINE_MM_FAMILIES = {"Otariidae", "Phocidae", "Odobenidae", "Dugongidae", "Trichechidae"}


def is_marine_mammal(row):
    return (row.get("order_la") or "").strip() in MARINE_MM_ORDERS \
        or (row.get("family_la") or "").strip() in MARINE_MM_FAMILIES


def load_mbris_marine_keys():
    """MBRIS 종목록 → managed_key 집합 (해양 포유류 필터링용)."""
    keys = set()
    if not MBRIS.exists():
        print(f"경고: {MBRIS.name} 미존재 — 해양 데이터 비교 불가")
        return keys

    with MBRIS.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mk = (row.get("managed_key") or "").strip()
            if mk:
                keys.add(mk)
    return keys


def load_master():
    """ktsn_master → (ktsn → row, 학명 → managed_key)."""
    ktsn_map = {}
    sci_to_mk = {}

    with MASTER.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            k = row.get("ktsn", "").strip()
            if k:
                ktsn_map[k] = row
                sci = (row.get("scientific_name") or "").strip()
                if sci:
                    mk = managed_key(sci)
                    if mk and mk not in sci_to_mk:
                        sci_to_mk[mk] = k

    return ktsn_map, sci_to_mk


def load_observations():
    """관측기록(agg + nps) → ktsn 집합."""
    ktsn_with_obs = set()

    # observation_agg 필수
    if OBS_AGG.exists():
        with OBS_AGG.open(encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                k = (row.get("ktsn") or "").strip()
                if k:
                    ktsn_with_obs.add(k)

    # observation_nps / observation_gbif 선택적(있으면 합침)
    for opt in (OBS_NPS, OBS_GBIF):
        if opt.exists():
            with opt.open(encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    k = (row.get("ktsn") or "").strip()
                    if k:
                        ktsn_with_obs.add(k)

    return ktsn_with_obs


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("서비스 종 목록 개선 시작...")

    # 1) 입력 데이터 로드
    mbris_keys = load_mbris_marine_keys()
    print(f"  MBRIS 해양종 managed_key: {len(mbris_keys)}")

    ktsn_map, sci_to_mk = load_master()
    print(f"  마스터: ktsn {len(ktsn_map)}")

    ktsn_with_obs = load_observations()
    print(f"  관측기록: ktsn {len(ktsn_with_obs)}")

    # 2) 플래그 생성
    flags = []
    taxon_counts = defaultdict(lambda: {"kept": 0, "excluded": 0})

    for ktsn, master_row in ktsn_map.items():
        taxon_group = (master_row.get("taxon_group") or "").strip()
        korean_name = (master_row.get("korean_name") or "").strip()
        scientific_name = (master_row.get("scientific_name") or "").strip()

        in_service = True
        exclude_reason = ""

        # 규칙 1: MM (포유류) — 해양 포유류 제외(분류학적 식별 + MBRIS 보강)
        if taxon_group == "MM":
            mk = managed_key(scientific_name) if scientific_name else None
            if is_marine_mammal(master_row) or (mk and mk in mbris_keys):
                in_service = False
                exclude_reason = "marine_mammal"

        # 규칙 2: -P (어류) — 해양어류(MBRIS) 중 '무기록 & 비적색목록' 종만 제외.
        #   유지: 담수/비해양 어류 · 조사기록(EcoBank·국립공원·GBIF) 있는 해양어류 · 국가적색목록 평가 어류.
        #   ※ MBRIS API 다운 시 marine set 비어 어류 전체 유지(해양종 식별 불가) → 복구 후 재실행 권장.
        elif taxon_group == "-P":
            mk = managed_key(scientific_name) if scientific_name else None
            is_marine = bool(mk and mk in mbris_keys)
            has_record = ktsn in ktsn_with_obs
            redlisted = bool((master_row.get("national_redlist_category") or "").strip())
            if is_marine and not has_record and not redlisted:
                in_service = False
                exclude_reason = "marine_fish_unrecorded"

        # 규칙 2.5: UC (미삭동물) — 멍게·미더덕 등 해양 피낭동물. 육상 생태계 집중 위해 전량 제외.
        elif taxon_group == "UC":
            in_service = False
            exclude_reason = "tunicate_marine"

        # 규칙 3: 그 외 — 서비스 포함
        # (기본값: in_service=True, exclude_reason="")

        flags.append({
            "ktsn": ktsn,
            "taxon_group": taxon_group,
            "korean_name": korean_name,
            "scientific_name": scientific_name,
            "in_service": "True" if in_service else "False",
            "exclude_reason": exclude_reason,
        })

        # 집계
        if in_service:
            taxon_counts[taxon_group or "unknown"]["kept"] += 1
        else:
            taxon_counts[taxon_group or "unknown"]["excluded"] += 1

    # 3) CSV 출력
    PROC.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "ktsn",
                "taxon_group",
                "korean_name",
                "scientific_name",
                "in_service",
                "exclude_reason",
            ],
        )
        w.writeheader()
        w.writerows(flags)

    # 4) 리포트
    print(f"\n결과: {OUT.name}")
    print(f"\n분류군별 집계:")
    total_kept = 0
    total_excluded = 0
    for taxon in sorted(taxon_counts.keys()):
        kept = taxon_counts[taxon]["kept"]
        excluded = taxon_counts[taxon]["excluded"]
        total_kept += kept
        total_excluded += excluded
        status = "유지" if kept > 0 else "모두제외"
        print(f"  [{taxon or '미분류'}]  유지 {kept:4d} | 제외 {excluded:4d}  [{status}]")

    print(f"\n합계:")
    print(f"  서비스 대상: {total_kept}")
    print(f"  제외됨: {total_excluded}")
    print(f"  전체: {total_kept + total_excluded}")
    print(f"\n소요시간: {Path(__file__).name} 완료")


if __name__ == "__main__":
    main()
