# -*- coding: utf-8 -*-
"""
멸종위기 야생생물 등급별 종 목록.xlsx → endangered_species.csv
- 입력: 4_References/붙임.멸종위기 야생생물 등급별 종 목록.xlsx (Sheet1: 번호·분류군·등급·국명·학명)
- 출력: 1_Data/processed/endangered_species.csv (분류군·등급·국명·학명·sci_key)
- 종 마스터에 학명으로 endangered_grade 조인하기 위한 전처리.
"""
import sys, csv
from pathlib import Path
import openpyxl
from taxon_key import managed_key, sci_keys

BASE = Path(__file__).resolve().parents[2]
XLSX = BASE / "4_References" / "붙임.멸종위기 야생생물 등급별 종 목록.xlsx"
OUT  = BASE / "1_Data" / "processed" / "endangered_species.csv"


def norm_grade(v):
    """등급 문자열 → I / II (로마숫자 표준화)."""
    s = str(v or "").strip().upper().replace("Ⅰ", "I").replace("Ⅱ", "II")
    s = s.replace("급", "").replace(" ", "")
    if s in ("I", "1"):
        return "I"
    if s in ("II", "2"):
        return "II"
    return s or ""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb.worksheets[0]   # Sheet1: 등급별 종 목록
    rows = list(ws.iter_rows(values_only=True))

    # 헤더행 탐색(‘학명’ 포함 행)
    hidx = next((i for i, r in enumerate(rows)
                 if r and any("학명" in str(c) for c in r if c)), 1)
    header = [str(c).strip() if c else "" for c in rows[hidx]]
    col = {name: header.index(name) for name in ("분류군", "등급", "국명", "학명") if name in header}
    if not {"학명", "등급"} <= set(col):
        sys.exit(f"헤더 인식 실패: {header}")

    out, grades = [], {}
    for r in rows[hidx + 1:]:
        if not r or not r[col["학명"]]:
            continue
        sci = str(r[col["학명"]]).strip()
        grade = norm_grade(r[col["등급"]]) if "등급" in col else ""
        taxon = str(r[col["분류군"]]).strip() if "분류군" in col else ""
        kor = str(r[col["국명"]]).strip() if "국명" in col else ""
        binom, trinom = sci_keys(sci)
        out.append({"분류군": taxon, "등급": grade, "국명": kor, "학명": sci,
                    "sci_key": managed_key(sci) or "", "binom": binom or ""})
        grades[grade] = grades.get(grade, 0) + 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["분류군", "등급", "국명", "학명", "sci_key", "binom"])
        w.writeheader(); w.writerows(out)

    print(f"멸종위기종 {len(out)}건 → {OUT.name}")
    print("등급분포:", dict(sorted(grades.items())))
    # 분류군 분포
    from collections import Counter
    print("분류군분포:", dict(Counter(o["분류군"] for o in out)))
    nokey = [o for o in out if not o["sci_key"]]
    if nokey:
        print(f"학명키 생성 실패 {len(nokey)}건:", [o["학명"] for o in nokey[:5]])


if __name__ == "__main__":
    main()
