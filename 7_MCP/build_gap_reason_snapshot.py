# -*- coding: utf-8 -*-
"""발견공백 사유 태깅 스냅샷 — 자동 체크(fg_taxon_status_check, append-only)와 전문가 제보
(taxon_reference_reports, 승인분)를 합쳐 data/gap_reason.json 을 만든다. build_mcp_data.py 가
이를 읽어 fg_mcp.sqlite 에 반영하고, build_gap_reason_asset.py 가 프런트 배지 자산으로 쪼갠다.

한 종에 여러 판정이 있으면 우선순위: reference(전문가 논문 근거로 확인) > regionally_extinct
(국가적색목록) > synonym(GBIF 자동 매치) — 사람이 특정 논문으로 확인한 게 가장 신뢰도 높다.

원본 이력(fg_taxon_status_check·taxon_reference_reports)은 이 스냅샷이 지워도 그대로 남는다 —
스냅샷은 "지금 화면에 보여줄 현재 상태"일 뿐, 이력 자체가 아니다.

사용: python 7_MCP/build_gap_reason_snapshot.py
필요: SUPABASE_DB_URL 환경변수 (5_App/.env 또는 환경변수) — 둘 다 RLS로 잠겨 있어 REST로는 못 읽음.
미배포/조회 실패 시 기존 스냅샷을 보존한다(watch_counts.json 과 동일한 안전장치).
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "data" / "gap_reason.json"

STATUS_QUERY = """
select distinct on (ktsn, source) ktsn, source, taxonomic_status, matched_name, checked_at
from public.fg_taxon_status_check
order by ktsn, source, checked_at desc;
"""

# user_id 는 절대 select하지 않는다 — 이 결과가 그대로 공개 자산(gap_reason.json)이 된다.
REFERENCE_QUERY = """
select ktsn, to_name, ref_title, ref_authors, ref_year, ref_container, doi, ref_url, created_at
from public.taxon_reference_reports
where status = 'approved'
order by ktsn, created_at desc;
"""

SYNONYM_STATUSES = {"SYNONYM", "HOMOTYPIC_SYNONYM", "HETEROTYPIC_SYNONYM", "PROPARTE_SYNONYM"}


def env_val(name):
    env = ROOT / "5_App" / ".env"
    if not env.exists():
        return ""
    m = re.search(rf"^\s*{name}\s*=\s*(.+?)\s*$", env.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip().strip('"').strip("'") if m else ""


def get_db_url():
    return (os.environ.get("SUPABASE_DB_URL") or env_val("SUPABASE_DB_URL")).strip()


def fetch_latest():
    import psycopg2

    conn = psycopg2.connect(get_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(STATUS_QUERY)
            status_rows = cur.fetchall()
            cur.execute(REFERENCE_QUERY)
            reference_rows = cur.fetchall()
        return status_rows, reference_rows
    finally:
        conn.close()


def build_reasons(status_rows, reference_rows):
    by_ktsn = {}
    for ktsn, source, status, matched_name, checked_at in status_rows:
        entry = by_ktsn.setdefault(ktsn, {})
        if source == "redlist" and status == "RE":
            entry["regionally_extinct"] = {"checked_at": checked_at.isoformat()}
        elif source == "gbif_backbone" and status in SYNONYM_STATUSES:
            entry["synonym"] = {"matched_name": matched_name, "checked_at": checked_at.isoformat()}

    for ktsn, to_name, ref_title, ref_authors, ref_year, ref_container, doi, ref_url, created_at in reference_rows:
        entry = by_ktsn.setdefault(ktsn, {})
        if "reference" in entry:  # 한 종에 승인된 제보가 여럿이면 가장 최근 것만(쿼리가 created_at desc 로 옴)
            continue
        entry["reference"] = {
            "to_name": to_name,
            "citation": {"title": ref_title, "authors": ref_authors, "year": ref_year,
                         "container": ref_container, "doi": doi, "url": ref_url},
            "checked_at": created_at.isoformat(),
        }

    result = {}
    for ktsn, entry in by_ktsn.items():
        if "reference" in entry:
            result[ktsn] = {"reason": "reference", "detail": entry["reference"]}
        elif "regionally_extinct" in entry:
            result[ktsn] = {"reason": "regionally_extinct", "detail": entry["regionally_extinct"]}
        elif "synonym" in entry:
            result[ktsn] = {"reason": "synonym", "detail": entry["synonym"]}
    return result


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    url = get_db_url()
    if not url:
        print("(정보) SUPABASE_DB_URL 없음 → 조회 생략.")
        return 0 if not OUT.exists() else 1

    try:
        status_rows, reference_rows = fetch_latest()
    except Exception as ex:
        print(f"(경고) 조회 실패: {ex}")
        if OUT.exists():
            print(f"(보존) 기존 스냅샷 유지: {OUT.relative_to(ROOT)}")
            return 1
        return 1

    reasons = build_reasons(status_rows, reference_rows)
    n_syn = sum(1 for v in reasons.values() if v["reason"] == "synonym")
    n_re = sum(1 for v in reasons.values() if v["reason"] == "regionally_extinct")
    n_ref = sum(1 for v in reasons.values() if v["reason"] == "reference")
    OUT.write_text(json.dumps(reasons, ensure_ascii=False), encoding="utf-8")
    print(f"출력: {OUT.relative_to(ROOT)} · 이명 가능성 {n_syn}종 · 지역절멸 {n_re}종 · 전문가 확인 {n_ref}종")
    return 0


if __name__ == "__main__":
    sys.exit(main())