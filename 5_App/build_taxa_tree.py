# -*- coding: utf-8 -*-
"""분류군별 목→과 계통수 자산 생성 — 방사형 cladogram(분류군 선택 시 renderDash 옆에 그림)의 데이터.

산출: 5_App/demo/data/taxa_tree.js
입력: 7_MCP/data/fg_mcp.sqlite (species.order_la/family_la, species_region.maxyear)

taxon_group(9, 서비스가 이미 쓰는 개념) → order_la → family_la 3단 계층에 각 노드의
종수·발견/휴면/미발견 건수를 매긴다. class_la(문·강)는 안 씀 — taxon_group이 이미
그 역할을 서비스 어휘로 하고 있어 중복. 발견 상태 계산은 finding_gap_mcp/tools.py의
get_species()와 같은 규칙(species_region.maxyear의 종별 최댓값, 최근 10년 창) — 화면
숫자가 다른 곳과 어긋나지 않게 맞춘다.

전체 분류군·과를 한 파일로 묶는다(과 2,910개 합쳐도 수백 KB대) — gapreason_<T>.js처럼
종 단위 대용량이 아니라서 분류군별로 쪼갤 필요가 없다.

실행: 손으로 따로 실행 (run_pipeline.py 미포함)
배포: build_dist.py 의 DATA_FILES 리스트에 있어 정적 배포본에 포함됨
"""
import json
import sqlite3
from pathlib import Path

APP = Path(__file__).resolve().parent
BASE = APP.parent
SQLITE = BASE / "7_MCP" / "data" / "fg_mcp.sqlite"
OUT = APP / "demo" / "data" / "taxa_tree.js"


def _state(maxyear, cutoff):
    if maxyear is None:
        return "none"
    return "found" if maxyear >= cutoff else "dormant"


def build():
    if not SQLITE.exists():
        raise SystemExit(f"소스 없음: {SQLITE}")
    con = sqlite3.connect(SQLITE)
    con.text_factory = str

    meta = dict(con.execute("select key, value from meta"))
    ref = int(meta.get("data_max_year") or 2026)
    cut = ref - 10                             # 서비스 mode A 와 같은 발견 창(최근 10년)

    tx_kor = {g: kor for g, kor in con.execute("select taxon_group, taxon_group_kor from taxa")}

    maxyear = {ktsn: my for ktsn, my in
               con.execute("select ktsn, max(maxyear) from species_region group by ktsn")}

    tree = {}
    n_species = n_orders = n_families = 0
    seen_orders, seen_families = set(), set()
    for ktsn, group, order_la, family_la in con.execute(
            "select ktsn, taxon_group, order_la, family_la from species where rank='종'"):
        order_la = (order_la or "").strip() or "(미분류)"
        family_la = (family_la or "").strip() or "(미분류)"
        st = _state(maxyear.get(ktsn), cut)

        g_node = tree.setdefault(group, {"kor": tx_kor.get(group, group), "n": 0,
                                          "found": 0, "dormant": 0, "none": 0, "orders": {}})
        o_node = g_node["orders"].setdefault(order_la, {"n": 0, "found": 0, "dormant": 0, "none": 0, "families": {}})
        f_node = o_node["families"].setdefault(family_la, {"n": 0, "found": 0, "dormant": 0, "none": 0})

        for node in (g_node, o_node, f_node):
            node["n"] += 1
            node[st] += 1

        n_species += 1
        seen_orders.add((group, order_la))
        seen_families.add((group, order_la, family_la))

    con.close()
    n_orders, n_families = len(seen_orders), len(seen_families)

    payload = {"gen": meta.get("generated", ""), "ref": ref, "cut": cut, "tree": tree}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.__TAXATREE__=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"생성 {OUT.relative_to(BASE)} · 분류군 {len(tree)} · 목 {n_orders} · 과 {n_families} · 종 {n_species} · {kb:.1f} KB")


if __name__ == "__main__":
    build()
