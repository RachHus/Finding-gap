# -*- coding: utf-8 -*-
"""
발견공백 MCP SQLite → Supabase Postgres 참고 테이블 벌크 로드.
사용법: python 5_App/supabase/load_reference.py                              # 전체 재적재
        python 5_App/supabase/load_reference.py --only fg_taxon_name,fg_species  # 지정 테이블만
필요: SUPABASE_DB_URL 환경변수 (Supabase Dashboard → Database → URI)
참고: fg_species_region 을 재적재하면 전국 롤업 MV(fg_species_national)를 자동 refresh 한다.
"""

import os
import re
import sys
import gzip
import csv
import io
import json
import sqlite3
from pathlib import Path

try:
    import psycopg2
except ImportError:
    print("pip install psycopg2-binary")
    sys.exit(1)


def env_val(name):
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return ""
    m = re.search(rf"^\s*{name}\s*=\s*(.+?)\s*$", env.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip().strip('"').strip("'") if m else ""


def get_db_url():
    url = (os.environ.get('SUPABASE_DB_URL') or env_val('SUPABASE_DB_URL')).strip()
    if not url:
        print("""SUPABASE_DB_URL이 설정되지 않았습니다.
Supabase Dashboard → Project Settings → Database → Connection string에서
직접 연결(Direct connection) 또는 세션 풀러(Session pooler) URI를 복사하여
환경변수로 설정하세요. (port 6543 제외)""")
        sys.exit(1)
    return url


def ensure_sqlite():
    db_path = Path('7_MCP/data/fg_mcp.sqlite')
    gz_path = Path('7_MCP/data/fg_mcp.sqlite.gz')

    if db_path.exists():
        return db_path

    if gz_path.exists():
        print(f"압축 해제 중: {gz_path}")
        with gzip.open(gz_path, 'rb') as f_in, open(db_path, 'wb') as f_out:
            f_out.write(f_in.read())
        print(f"생성됨: {db_path}")
        return db_path

    print(f"오류: {db_path} 또는 {gz_path}를 찾을 수 없습니다.")
    sys.exit(1)


def load_table(sqlite_conn, pg_cursor, table_name, columns, query):
    """테이블 벌크 로드 — 배치 단위 COPY 로 메모리 억제(590k행 대비)."""
    pg_cursor.execute(f"TRUNCATE public.{table_name};")
    src = sqlite_conn.cursor()
    src.execute(query)
    copy_sql = f"COPY public.{table_name} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv)"
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    while True:
        rows = src.fetchmany(20000)
        if not rows:
            break
        buf.seek(0)
        buf.truncate(0)
        writer.writerows(rows)
        buf.seek(0)
        pg_cursor.copy_expert(copy_sql, buf)


def load_taxon_name(pg_cursor):
    """KTSN 전체(강·목·과·속 라틴↔한글)를 fg_taxon_name 에 적재.
    출처: 7_MCP/data/taxon_names.json.gz (python 7_MCP/build_taxon_names.py 로 생성)."""
    path = Path('7_MCP/data/taxon_names.json.gz')
    if not path.exists():
        print(f"(경고) 건너뜀: {path} 없음 — python 7_MCP/build_taxon_names.py 로 먼저 생성하세요.")
        return
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        data = json.load(f)
    rows = [(rank, la, ko)
            for rank in ('class', 'order', 'family', 'genus')
            for la, ko in data.get(rank, {}).items()]
    pg_cursor.execute("TRUNCATE public.fg_taxon_name;")
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerows(rows)
    buf.seek(0)
    pg_cursor.copy_expert(
        "COPY public.fg_taxon_name (rank, latin, korean) FROM STDIN WITH (FORMAT csv)", buf)


KNOWN_TABLES = ['fg_species', 'fg_species_region', 'fg_region', 'fg_taxa', 'fg_taxon_name']


def parse_only(argv):
    """--only a,b / --only=a,b / 나열된 테이블명 → set(대상) 또는 None(전체)."""
    vals = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--only':
            i += 1
            if i < len(argv):
                vals.extend(argv[i].split(','))
        elif a.startswith('--only='):
            vals.extend(a[len('--only='):].split(','))
        else:
            vals.append(a)
        i += 1
    vals = [v.strip() for v in vals if v.strip()]
    if not vals:
        return None
    unknown = [v for v in vals if v not in KNOWN_TABLES]
    if unknown:
        print(f"오류: 알 수 없는 테이블 {unknown}. 가능: {KNOWN_TABLES}", file=sys.stderr)
        sys.exit(2)
    return set(vals)


def refresh_national(pg_cursor):
    """fg_species_region 변경 후 전국 롤업 MV(fg_species_national) 재계산."""
    try:
        pg_cursor.execute("REFRESH MATERIALIZED VIEW public.fg_species_national;")
        print("  fg_species_national: refreshed")
    except Exception as e:
        print(f"  (경고) fg_species_national refresh 실패(MV 미생성?): {e}", file=sys.stderr)


def verify_tables(pg_cursor):
    """로드된 행 수 확인."""
    for table in KNOWN_TABLES:
        pg_cursor.execute(f"SELECT count(*) FROM public.{table};")
        count = pg_cursor.fetchone()[0]
        print(f"  {table}: {count}행")


def main():
    db_url = get_db_url()
    sqlite_path = ensure_sqlite()

    sqlite_conn = None
    pg_conn = None

    try:
        sqlite_conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        sqlite_conn.row_factory = sqlite3.Row

        pg_conn = psycopg2.connect(db_url)
        pg_cursor = pg_conn.cursor()

        only = parse_only(sys.argv[1:])   # None=전체, set=지정 테이블만
        want = lambda t: only is None or t in only

        # (테이블, 적재 함수) — --only 로 선택 적재. 순서 유지(스키마 의존 없음이나 가독성).
        steps = [
            ('fg_species', lambda: load_table(sqlite_conn, pg_cursor, 'fg_species',
                ['ktsn', 'korean_name', 'scientific_name', 'taxon_group',
                 'taxon_group_kor', 'class_la', 'order_la', 'family_la', 'genus_la',
                 'endangered_grade', 'national_redlist_category',
                 'has_media', 'interest'],
                "SELECT ktsn, korean_name, scientific_name, taxon_group, "
                "taxon_group_kor, class_la, order_la, family_la, genus_la, "
                "endangered_grade, national_redlist_category, "
                "has_media, interest FROM species")),
            ('fg_species_region', lambda: load_table(sqlite_conn, pg_cursor, 'fg_species_region',
                ['ktsn', 'taxon_group', 'region', 'sido', 'maxyear', 'obs_count'],
                "SELECT ktsn, taxon_group, region, sido, maxyear, obs_count "
                "FROM species_region")),
            ('fg_region', lambda: load_table(sqlite_conn, pg_cursor, 'fg_region',
                ['code', 'name', 'level', 'sido_cd'],
                "SELECT code, name, level, sido_cd FROM region")),
            ('fg_taxa', lambda: load_table(sqlite_conn, pg_cursor, 'fg_taxa',
                ['taxon_group', 'taxon_group_kor', 'n_species'],
                "SELECT taxon_group, taxon_group_kor, n_species FROM taxa")),
            ('fg_taxon_name', lambda: load_taxon_name(pg_cursor)),
        ]

        print(f"데이터 로드 중... ({'전체' if only is None else '선택: ' + ', '.join(sorted(only))})")
        loaded = []
        for name, fn in steps:
            if want(name):
                print(f"  적재: {name}")
                fn()
                loaded.append(name)

        # 전국 롤업 MV 는 fg_species_region 에 의존 — 재적재됐을 때만 refresh.
        if 'fg_species_region' in loaded:
            refresh_national(pg_cursor)

        print("검증:")
        verify_tables(pg_cursor)

        pg_conn.commit()
        print("완료!")
        return 0

    except Exception as e:
        if pg_conn:
            pg_conn.rollback()
        print(f"오류: {e}", file=sys.stderr)
        return 1
    finally:
        if sqlite_conn:
            sqlite_conn.close()
        if pg_conn:
            pg_conn.close()


if __name__ == "__main__":
    sys.exit(main())
