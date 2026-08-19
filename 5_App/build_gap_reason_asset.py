# -*- coding: utf-8 -*-
"""발견공백 사유 배지 프런트 자산 — 7_MCP/data/gap_reason.json(build_gap_reason_snapshot.py 산출)을
분류군별 지연로드 파일(demo/data/gapreason_<T>.js)로 쪼갠다.

model_<T>.js·cells_<T>.js 와 같은 관례(분류군 파일명 토큰화 `_txfile`, `window.__X__=window.__X__||{}`
네임스페이스 병합, 종당 데이터는 ktsn 키)를 그대로 따른다 — index.html 의 loadGapReason() 이
동일한 _loadScript 패턴으로 불러온다. 사유가 없는 종은 아예 담지 않는다(대부분이라 자산이 작다).

사용: python 5_App/build_gap_reason_asset.py
전제: 7_MCP/data/fg_mcp.sqlite(.gz) 로 ktsn→taxon_group 매핑, gap_reason.json 없으면 빈 자산 생성.
"""
import json
import re
import sqlite3
from pathlib import Path

APP = Path(__file__).resolve().parent
BASE = APP.parent
OUT = APP / "demo" / "data"
SQLITE = BASE / "7_MCP" / "data" / "fg_mcp.sqlite"
GAP_REASON_JSON = BASE / "7_MCP" / "data" / "gap_reason.json"


def _txfile(t):
    return re.sub(r"[^A-Za-z0-9]", "_", t)


def _ktsn_taxon_map():
    con = sqlite3.connect(f"file:{SQLITE}?mode=ro", uri=True)
    try:
        return dict(con.execute("select ktsn, taxon_group from species").fetchall())
    finally:
        con.close()


def _format_citation(citation):
    """전문가 제보(reference)의 서지 정보를 짧은 인용문 하나로 — 풀 CSL 렌더링은 이번 범위 밖."""
    if not citation:
        return ""
    parts = []
    who = (citation.get("authors") or "").strip()
    year = citation.get("year")
    if who:
        parts.append(f"{who} ({year})" if year else who)
    elif year:
        parts.append(str(year))
    title = (citation.get("title") or "").strip()
    if title:
        parts.append(title)
    container = (citation.get("container") or "").strip()
    if container:
        parts.append(container)
    return ". ".join(parts)


def main():
    if not GAP_REASON_JSON.exists():
        print(f"(정보) {GAP_REASON_JSON.relative_to(BASE)} 없음 — build_gap_reason_snapshot.py 먼저 실행. 자산 생성 생략.")
        return
    reasons = json.loads(GAP_REASON_JSON.read_text(encoding="utf-8"))
    if not reasons:
        print("(정보) gap_reason.json이 비어있음 — 생성할 배지 없음.")
        return

    taxon_of = _ktsn_taxon_map()
    by_group = {}
    unmapped = 0
    for ktsn, r in reasons.items():
        t = taxon_of.get(ktsn)
        if not t:
            unmapped += 1
            continue
        detail = r.get("detail") or {}
        entry = {"r": r["reason"]}
        if r["reason"] == "reference":
            if detail.get("to_name"):
                entry["n"] = detail["to_name"]
            cite = _format_citation(detail.get("citation"))
            if cite:
                entry["c"] = cite
        else:
            note = detail.get("matched_name")
            if note:
                entry["n"] = note
        by_group.setdefault(t, {})[ktsn] = entry

    OUT.mkdir(parents=True, exist_ok=True)
    for t, d in sorted(by_group.items()):
        p = OUT / f"gapreason_{_txfile(t)}.js"
        p.write_text(
            f'(window.__GAPREASON__=window.__GAPREASON__||{{}})["{t}"]='
            + json.dumps(d, separators=(",", ":"), ensure_ascii=False) + ";",
            encoding="utf-8")
        print(f"  gapreason_{_txfile(t)}.js: {len(d)}종")

    if unmapped:
        print(f"(경고) taxon_group 매핑 실패 {unmapped}건(sqlite에 없는 ktsn) — 스킵됨.")
    print(f"발견공백 사유 배지: {sum(len(d) for d in by_group.values())}종 · {len(by_group)}개 분류군 파일 → {OUT}")


if __name__ == "__main__":
    main()
