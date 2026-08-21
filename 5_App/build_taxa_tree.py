# -*- coding: utf-8 -*-
"""분류군별 목→과 계통수 자산 생성 — 방사형 cladogram(분류군 선택 시 renderDash 옆에 그림)의 데이터.

산출: 5_App/demo/data/taxa_tree.js (목→과 집계, 전체 분류군 한 파일)
     + 5_App/demo/data/taxatree_sp_<T>.js (과→종 목록, 분류군별 지연 로드 — 계통수에서 과를 눌러 펼칠 때만)
입력: 7_MCP/data/fg_mcp.sqlite (species.order_la/family_la, species_region.maxyear)

KTSN이 정명으로 인정한 아종은 속한 종으로 접지 않고 자기 계급 그대로 잎에 놓는다 — 표범
Panthera pardus orientalis 처럼 보호 등급이 아종에 붙는 경우가 있어, 종으로 접으면 그 등급이
어디에 걸린 것인지 사라진다. 아종 잎에는 튜플 5번째 자리에 1을 실어 화면이 계급을 밝힐 수 있게 한다.

taxon_group(9, 서비스가 이미 쓰는 개념) → order_la → family_la 3단 계층에 각 노드의
종수·발견/휴면/미발견 건수를 매긴다. class_la(문·강)는 안 씀 — taxon_group이 이미
그 역할을 서비스 어휘로 하고 있어 중복. 발견 상태 계산은 finding_gap_mcp/tools.py의
get_species()와 같은 규칙(species_region.maxyear의 종별 최댓값, 최근 10년 창) — 화면
숫자가 다른 곳과 어긋나지 않게 맞춘다.

목→과 집계는 전체 분류군·과를 한 파일로 묶는다(과 2,910개 합쳐도 수백 KB대) — 종 단위
대용량이 아니라서 분류군별로 쪼갤 필요가 없다. 반면 과→종 목록은 분류군마다(특히 곤충류
20,423종) 합치면 무거워서 model_<T>.js·gapreason_<T>.js 와 같은 관례(분류군 파일명
토큰화 `_txfile`, `window.__X__=window.__X__||{}` 네임스페이스 병합)로 쪼갠다 — index.html
쪽에서 계통수의 과(잎)를 누른 순간에만 그 분류군 파일을 지연 로드한다.

실행: 손으로 따로 실행 (run_pipeline.py 미포함)
배포: build_dist.py 의 DATA_FILES(taxa_tree.js)·DATA_GLOBS(taxatree_sp_*.js)에 등록돼 정적 배포본에 포함됨
"""
import json
import re
import sqlite3
from pathlib import Path

APP = Path(__file__).resolve().parent
BASE = APP.parent
SQLITE = BASE / "7_MCP" / "data" / "fg_mcp.sqlite"
OUT = APP / "demo" / "data" / "taxa_tree.js"
OUT_SP_DIR = APP / "demo" / "data"


def _txfile(t):
    return re.sub(r"[^A-Za-z0-9]", "_", t)


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

    STATE_CODE = {"found": "f", "dormant": "d", "none": "n"}
    tree = {}
    sp_by_group = {}                           # group -> "order|family" -> [[ktsn, korean_name, code, genus_la, 아종이면 1], ...]
    n_species = n_subspecies = n_orders = n_families = 0
    seen_orders, seen_families, seen_genera = set(), set(), set()
    seen_order_genus, seen_family_genus = set(), set()
    for ktsn, korean_name, group, order_la, family_la, genus_la, rank in con.execute(
            "select ktsn, korean_name, taxon_group, order_la, family_la, genus_la, rank "
            "from species where rank in ('종', '아종')"):
        order_la = (order_la or "").strip() or "(미분류)"
        family_la = (family_la or "").strip() or "(미분류)"
        genus_la = (genus_la or "").strip() or "(미분류)"
        st = _state(maxyear.get(ktsn), cut)

        g_node = tree.setdefault(group, {"kor": tx_kor.get(group, group), "n": 0,
                                          "found": 0, "dormant": 0, "none": 0, "orders": {}})
        o_node = g_node["orders"].setdefault(order_la, {"n": 0, "found": 0, "dormant": 0, "none": 0, "families": {}})
        f_node = o_node["families"].setdefault(family_la, {"n": 0, "found": 0, "dormant": 0, "none": 0})

        for node in (g_node, o_node, f_node):
            node["n"] += 1
            node[st] += 1

        # 속(genus) 단위 별도 집계 트리(목→과처럼 개별 노드)는 안 만든다 — 과를 펼쳤을 때 실제 속
        # 그룹은 여전히 이 종 목록(genus_la)에서 브라우저가 즉석에서 묶는다. 다만 "이 목/과 아래
        # 속이 몇 개인지" 개수(genus_n)만은 분류군·목·과 세 단계 모두 미리 세어 둔다 — 계통도를
        # 드릴다운할 때마다(종 목록이 아직 지연 로드되기 전에도) 바로 보여줘야 해서.
        row = [ktsn, korean_name or "", STATE_CODE[st], genus_la]
        if rank == "아종":
            row.append(1)
        sp_by_group.setdefault(group, {}).setdefault(f"{order_la}|{family_la}", []).append(row)

        n_species += 1
        n_subspecies += (rank == "아종")
        seen_orders.add((group, order_la))
        seen_families.add((group, order_la, family_la))
        seen_genera.add((group, genus_la))
        seen_order_genus.add((group, order_la, genus_la))
        seen_family_genus.add((group, order_la, family_la, genus_la))

    con.close()
    n_orders, n_families = len(seen_orders), len(seen_families)

    genus_n_by_group, genus_n_by_order, genus_n_by_family = {}, {}, {}
    for group, genus_la in seen_genera:
        genus_n_by_group[group] = genus_n_by_group.get(group, 0) + 1
    for group, order_la, genus_la in seen_order_genus:
        genus_n_by_order[(group, order_la)] = genus_n_by_order.get((group, order_la), 0) + 1
    for group, order_la, family_la, genus_la in seen_family_genus:
        key = (group, order_la, family_la)
        genus_n_by_family[key] = genus_n_by_family.get(key, 0) + 1

    for group, g_node in tree.items():
        g_node["genus_n"] = genus_n_by_group.get(group, 0)
        for order_la, o_node in g_node["orders"].items():
            o_node["genus_n"] = genus_n_by_order.get((group, order_la), 0)
            for family_la, f_node in o_node["families"].items():
                f_node["genus_n"] = genus_n_by_family.get((group, order_la, family_la), 0)

    payload = {"gen": meta.get("generated", ""), "ref": ref, "cut": cut, "tree": tree}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.__TAXATREE__=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    n_genera = len(seen_genera)
    print(f"생성 {OUT.relative_to(BASE)} · 분류군 {len(tree)} · 목 {n_orders} · 과 {n_families} · 속 {n_genera} · "
          f"잎 {n_species}(아종 {n_subspecies}) · {kb:.1f} KB")

    OUT_SP_DIR.mkdir(parents=True, exist_ok=True)
    for g, by_key in sorted(sp_by_group.items()):
        p = OUT_SP_DIR / f"taxatree_sp_{_txfile(g)}.js"
        p.write_text(
            f'(window.__TAXATREE_SP__=window.__TAXATREE_SP__||{{}})["{g}"]='
            + json.dumps(by_key, ensure_ascii=False, separators=(",", ":")) + ";\n",
            encoding="utf-8")
        n_sp = sum(len(v) for v in by_key.values())
        n_sub = sum(1 for v in by_key.values() for r in v if len(r) > 4)
        print(f"  taxatree_sp_{_txfile(g)}.js: 과 {len(by_key)} · 잎 {n_sp}(아종 {n_sub}) · {p.stat().st_size/1024:.1f} KB")


if __name__ == "__main__":
    build()
