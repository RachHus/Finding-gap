# -*- coding: utf-8 -*-
"""
KTSN 학명을 GBIF Backbone Taxonomy(species/match, 무료·키 불필요)에 대조해
이명(synonym) 여부를 확인하고, 국가적색목록 지역절멸(RE) 종을 함께 표시 —
"발견공백 사유 태깅"(synonym·지역절멸 배지)의 근거 데이터를 만든다.

배경: "미발견"이라는 판정 하나에 (1) 진짜 조사부족 (2) 분류학적 이명 잔재
(3) 이미 지역절멸(RE)된 종이 섞여 있다. 이 스크립트는 (2)(3)을 걸러내는 배치 체크다.

용어: 자체 라벨 대신 Darwin Core taxonomicStatus 어휘를 그대로 저장한다
(ACCEPTED/SYNONYM/HOMOTYPIC_SYNONYM/... — GBIF가 반환하는 값 그대로).
`bucket`은 이 스크립트의 콘솔 요약을 위한 내부 분류일 뿐, DB에는 안 감.

적재 방식(append-only): --push 시 로컬 CSV와 별개로 Supabase `fg_taxon_status_check`에
INSERT만 한다 — UPDATE/TRUNCATE 없음. 같은 종을 다시 체크해도 새 행이 쌓이고,
"현재 상태"는 (ktsn, source)별 최신 checked_at 행으로 조회한다(레이어 3의 스냅숏 스크립트 몫).
ERROR(네트워크 실패)는 판정이 아니므로 push하지 않는다 — 재실행 시 자연히 채워짐.

사용:
  python 7_MCP/check_gbif_synonyms.py --smoke                       # 스크립트 자체 점검(그룹당 5종)
  python 7_MCP/check_gbif_synonyms.py --seed 42 --sleep 0.2         # 표본 조사(투자 전 규모 파악용)
  python 7_MCP/check_gbif_synonyms.py --taxon-group RP --push       # 전종 GBIF 체크 + DB 적재(분류군 단위로 나눠 여러 세션에 걸쳐 실행 가능)
  python 7_MCP/check_gbif_synonyms.py --redlist --push              # GBIF 호출 없이 지역절멸(RE) 플래그만 적재
필요(--push 시): SUPABASE_DB_URL 환경변수 (5_App/.env 또는 환경변수)
"""
import argparse
import csv
import os
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

SQLITE = Path(__file__).resolve().parent / "data" / "fg_mcp.sqlite"
OUT_CSV = Path(__file__).resolve().parent / "gbif_synonym_report.csv"
MATCH_URL = "https://api.gbif.org/v1/species/match"
USAGE_URL = "https://api.gbif.org/v1/species/{key}"

# 분류군 → GBIF kingdom (매칭 정확도용)
KINGDOM = {"MM": "Animalia", "AV": "Animalia", "RP": "Animalia", "AM": "Animalia",
           "-P": "Animalia", "IN": "Animalia", "IV": "Animalia",
           "VP": "Plantae", "MS": "Plantae"}

# 표본 조사(--sample-cap 지정 시)에서 척추동물처럼 작은 그룹은 항상 전체를 본다.
FULL_GROUPS = {"MM", "RP", "AM", "AV"}

SYNONYM_STATUSES = {"SYNONYM", "HOMOTYPIC_SYNONYM", "HETEROTYPIC_SYNONYM", "PROPARTE_SYNONYM"}


def env_val(name):
    env = Path(__file__).resolve().parent.parent / "5_App" / ".env"
    if not env.exists():
        return ""
    m = re.search(rf"^\s*{name}\s*=\s*(.+?)\s*$", env.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip().strip('"').strip("'") if m else ""


def get_db_url():
    url = (os.environ.get("SUPABASE_DB_URL") or env_val("SUPABASE_DB_URL")).strip()
    if not url:
        print("""SUPABASE_DB_URL이 설정되지 않았습니다.
Supabase Dashboard → Project Settings → Database → Connection string에서
직접 연결(Direct connection) 또는 세션 풀러(Session pooler) URI를 복사하여
환경변수로 설정하세요. (port 6543 제외)""")
        sys.exit(1)
    return url


def load_species(taxon_groups):
    con = sqlite3.connect(SQLITE)
    cur = con.cursor()
    q = "select ktsn, korean_name, scientific_name, taxon_group, national_redlist_category from species where rank='종'"
    if taxon_groups:
        q += f" and taxon_group in ({','.join('?' * len(taxon_groups))})"
        cur.execute(q, list(taxon_groups))
    else:
        cur.execute(q)
    rows = cur.fetchall()
    con.close()
    return rows


def load_sample(seed, taxon_groups, sample_cap):
    rows = load_species(taxon_groups)
    by_group = {}
    for r in rows:
        by_group.setdefault(r[3], []).append(r)
    rng = random.Random(seed)
    sample = []
    for group, group_rows in by_group.items():
        n = None if (sample_cap is None or group in FULL_GROUPS) else sample_cap
        if n is None or n >= len(group_rows):
            sample.extend(group_rows)
        else:
            sample.extend(rng.sample(group_rows, n))
    return sample


def match_one(name, kingdom, session):
    try:
        r = session.get(MATCH_URL, params={"name": name, "kingdom": kingdom, "strict": "false"}, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"  경고: GBIF match 실패 ({name}): {e}", file=sys.stderr)
        return None


def resolve_accepted(key, session, cache):
    if key in cache:
        return cache[key]
    name = None
    try:
        r = session.get(USAGE_URL.format(key=key), timeout=10)
        r.raise_for_status()
        name = r.json().get("canonicalName")
    except requests.RequestException as e:
        print(f"  경고: GBIF usage 조회 실패 ({key}): {e}", file=sys.stderr)
    cache[key] = name
    return name


def classify(match):
    """콘솔 요약용 내부 버킷 — DB에는 안 들어감(DB엔 GBIF status 원본을 그대로 저장)."""
    if match is None:
        return "ERROR"
    if match.get("matchType") == "NONE":
        return "NO_MATCH"
    status = match.get("status") or ""
    if status in SYNONYM_STATUSES:
        return "SYNONYM"
    if status == "ACCEPTED" and match.get("matchType") == "EXACT":
        return "EXACT_ACCEPTED"
    return "OTHER"


def push_gbif_rows(conn, checks):
    """checks: [(ktsn, taxonomic_status, matched_name, detail_dict), ...]. ERROR는 호출 전에 걸러져 있어야 함."""
    import json
    from psycopg2.extras import execute_values

    with conn.cursor() as cur:
        execute_values(
            cur,
            "insert into public.fg_taxon_status_check (ktsn, source, taxonomic_status, matched_name, detail) values %s",
            [(k, "gbif_backbone", st, mn, json.dumps(detail, ensure_ascii=False)) for k, st, mn, detail in checks],
            template="(%s, %s, %s, %s, %s::jsonb)",
        )
    conn.commit()


def push_redlist_rows(conn, ktsn_list):
    from psycopg2.extras import execute_values

    with conn.cursor() as cur:
        execute_values(
            cur,
            "insert into public.fg_taxon_status_check (ktsn, source, taxonomic_status) values %s",
            [(k, "redlist", "RE") for k in ktsn_list],
        )
    conn.commit()


def run_redlist(push):
    rows = load_species(None)
    re_rows = [r for r in rows if (r[4] or "") == "RE"]
    print(f"국가적색목록 지역절멸(RE) 종: {len(re_rows)}개")
    for ktsn, ko, sci, group, _ in re_rows:
        print(f"  [{group}] {ko} — {sci}")
    if push and re_rows:
        import psycopg2

        conn = psycopg2.connect(get_db_url())
        try:
            push_redlist_rows(conn, [r[0] for r in re_rows])
            print(f"→ fg_taxon_status_check에 {len(re_rows)}행 적재(source='redlist').")
        finally:
            conn.close()


def run_gbif(seed, sleep_s, smoke, taxon_groups, sample_cap, push):
    sample = load_sample(seed, taxon_groups, sample_cap)
    if smoke:
        by_group = {}
        for r in sample:
            by_group.setdefault(r[3], []).append(r)
        sample = [r for rows in by_group.values() for r in rows[:5]]
    print(f"표본 {len(sample)}종 조회 시작 (seed={seed}, sleep={sleep_s}s, push={push})...")

    session = requests.Session()
    accepted_cache = {}
    summary = {}  # group -> {bucket: count}
    synonym_examples = []
    rows_out = []
    push_checks = []  # (ktsn, taxonomic_status, matched_name, detail) — ERROR 제외

    for i, (ktsn, korean_name, sci_name, group, _redlist) in enumerate(sample, 1):
        kingdom = KINGDOM.get(group, "Animalia")
        match = match_one(sci_name, kingdom, session)
        bucket = classify(match)
        accepted_name = ""
        if bucket == "SYNONYM" and match.get("acceptedUsageKey"):
            accepted_name = resolve_accepted(match["acceptedUsageKey"], session, accepted_cache) or ""
            synonym_examples.append((group, korean_name, sci_name, accepted_name))

        summary.setdefault(group, {}).setdefault(bucket, 0)
        summary[group][bucket] += 1

        rows_out.append([
            ktsn, korean_name, sci_name, group, bucket,
            (match or {}).get("matchType", ""), (match or {}).get("status", ""),
            (match or {}).get("canonicalName", ""), accepted_name,
            (match or {}).get("confidence", ""),
        ])

        if bucket != "ERROR":
            detail = {k: match.get(k) for k in ("matchType", "confidence", "usageKey", "acceptedUsageKey") if match.get(k) is not None}
            push_checks.append((ktsn, match.get("status") or "", accepted_name or None, detail))

        if i % 100 == 0:
            print(f"  {i}/{len(sample)}...")
        time.sleep(sleep_s)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ktsn", "korean_name", "scientific_name", "taxon_group", "bucket",
                    "gbif_matchType", "gbif_status", "gbif_matched_name",
                    "gbif_accepted_name_if_synonym", "gbif_confidence"])
        w.writerows(rows_out)

    print(f"\n=== 분류군별 요약 (표본 기준, CSV: {OUT_CSV.name}) ===")
    header = f"{'분류군':<6}{'표본수':>6}{'EXACT_ACCEPTED':>16}{'SYNONYM':>10}{'NO_MATCH':>10}{'OTHER':>8}{'ERROR':>7}"
    print(header)
    for group in sorted(summary, key=lambda g: -sum(summary[g].values())):
        counts = summary[group]
        total = sum(counts.values())
        line = f"{group:<6}{total:>6}"
        for bucket in ("EXACT_ACCEPTED", "SYNONYM", "NO_MATCH", "OTHER", "ERROR"):
            n = counts.get(bucket, 0)
            pct = f"{n}({n/total*100:.0f}%)" if total else "0"
            width = 16 if bucket == "EXACT_ACCEPTED" else 10 if bucket in ("SYNONYM", "NO_MATCH") else 8 if bucket == "OTHER" else 7
            line += f"{pct:>{width}}"
        print(line)

    if synonym_examples:
        print("\n=== SYNONYM 예시 (최대 20개) ===")
        for group, ko, sci, accepted in synonym_examples[:20]:
            print(f"  [{group}] {ko} — KTSN: {sci}  ->  GBIF 현재명: {accepted}")

    if push:
        import psycopg2

        conn = psycopg2.connect(get_db_url())
        try:
            push_gbif_rows(conn, push_checks)
            print(f"\n→ fg_taxon_status_check에 {len(push_checks)}행 적재(source='gbif_backbone').")
        finally:
            conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--smoke", action="store_true", help="그룹당 5종만 빠르게 점검")
    ap.add_argument("--taxon-group", help="쉼표로 구분된 분류군 코드만 처리(예: RP,MM) — 여러 세션에 나눠 돌릴 때 사용")
    ap.add_argument("--sample-cap", type=int, default=None, help="그룹당 표본 상한(기본: 전종). 척추동물 소그룹은 항상 전종")
    ap.add_argument("--push", action="store_true", help="Supabase fg_taxon_status_check에 결과를 적재(append-only)")
    ap.add_argument("--redlist", action="store_true", help="GBIF 호출 없이 국가적색목록 지역절멸(RE) 플래그만 처리")
    args = ap.parse_args()

    taxon_groups = [g.strip() for g in args.taxon_group.split(",")] if args.taxon_group else None

    if args.redlist:
        run_redlist(args.push)
    else:
        run_gbif(args.seed, args.sleep, args.smoke, taxon_groups, args.sample_cap, args.push)


if __name__ == "__main__":
    main()