# -*- coding: utf-8 -*-
"""적색목록 파싱 손실 점검: 분류군-시작 레코드 중 파싱 실패행을 실제 파서 기준으로 식별."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_redlist as e

OUT = Path(__file__).resolve().parents[2] / "1_Data" / "processed" / "redlist_parse_losses.txt"

def fail_reason(rec):
    """parse_tonghap과 동일 조건(repair·unwrap·deglue 적용된 rec)으로 실패사유 검사."""
    toks = e.deglue(rec).split()
    if len(toks) < 4 or toks[0] not in e.TONG_TAXA:
        return "not_data"
    i = 1
    while i < len(toks) and e.HANGUL.search(toks[i]) and not e.is_latin(toks[i]):
        i += 1
    j = i
    while j < len(toks) and e.strip_punct(toks[j]) not in e.CODES:
        j += 1
    sci = " ".join(toks[i:j]).strip()
    code_idx = [k for k, t in enumerate(toks) if e.strip_punct(t) in e.CODES]
    if not sci:        return "no_sci(학명 추출 실패)"
    if not code_idx:   return "no_code(평가범주 코드 없음)"
    return None

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    lines = e.read_pdf_lines(e.PDF_TONG)
    records = e._unwrap_tonghap(e._repair_split_taxa(lines))   # 실제 파서와 동일 전처리
    started = [r for r in records if r.split() and r.split()[0] in e.TONG_TAXA]
    lost = [(fail_reason(r), r) for r in started]
    lost = [(w, r) for w, r in lost if w]
    rows = e.parse_tonghap(lines)

    buf = [f"통합본 분류군-시작 레코드: {len(started)}  /  파싱 성공행: {len(rows)}  /  실패: {len(lost)}"]
    if lost:
        buf.append("\n[남은 손실]")
        for w, r in lost:
            buf.append(f"  - ({w})  {r[:160]}")
    else:
        buf.append("\n손실 없음 — 분류군-시작 레코드 전부 파싱 성공.")
    txt = "\n".join(buf)
    print(txt)
    OUT.write_text(txt, encoding="utf-8")
    print("\n저장:", OUT)

if __name__ == "__main__":
    main()
