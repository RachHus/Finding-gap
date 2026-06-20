# -*- coding: utf-8 -*-
"""
국가생물적색목록 추출·병합
- 입력: 4_References/2024 국가생물적색자료집_통합본.pdf  (찾아보기: 초판/개정판 평가범주)
        4_References/국가생물적색자료집 제12권_곤충iv.pdf (2025 곤충 적색목록, 단일 평가범주)
- 로직: 통합본(개정판 평가범주) 추출 → 곤충IV(2025)와 학명/한글명 대조
        중복이면 2025 자료로 업데이트, 비중복이면 row-bind(분류군=곤충4)
- 출력: 1_Data/processed/national_redlist.csv  (분류군명·학명·한글명·적색목록코드 + 부가)
"""
import re, csv, sys
from pathlib import Path
from pypdf import PdfReader

BASE = Path(__file__).resolve().parents[2]          # 프로젝트 루트
REF  = BASE / "4_References"
OUT  = BASE / "1_Data" / "processed" / "national_redlist.csv"
PDF_TONG = REF / "2024 국가생물적색자료집_통합본.pdf"
PDF_GON  = REF / "국가생물적색자료집 제12권_곤충iv.pdf"

CODES = {"CR","EN","VU","NT","LC","DD","RE","EW","EX","NA","NE"}
TONG_TAXA = {"연체동물","거미","관속식물","곤충1","곤충2","곤충3",
             "조류","어류","포유류","파충류","양서류"}
HANGUL = re.compile(r"[가-힣]")

def read_pdf_lines(path):
    r = PdfReader(str(path))
    lines = []
    for p in r.pages:
        for ln in (p.extract_text() or "").splitlines():
            ln = ln.strip()
            if ln:
                lines.append(ln)
    return lines

def is_latin(tok):  # 학명 시작(라틴 대문자 속명 등)
    return bool(re.match(r"^[A-Za-z]", tok))

def strip_punct(tok):
    return tok.strip(".,;:()[]")

def norm_sci(sci):
    """속명+종소명 2단어로 정규화(괄호·저자·연도 제거)"""
    s = re.sub(r"\([^)]*\)", " ", sci)               # 괄호(아속/저자) 제거
    toks = [t for t in re.split(r"\s+", s) if re.match(r"^[A-Za-z]", t)]
    return " ".join(toks[:2]).lower()

def norm_kor(k):
    return re.sub(r"\s+", "", k)

# 코드가 저자/괄호/숫자에 공백없이 붙은 경우 분리 (예: 'ShinEN','1823)CR','(i)VU')
_DEGLUE = re.compile(r"([a-z0-9\)\],])(" + "|".join(CODES) + r")\b")
def deglue(s):
    return _DEGLUE.sub(r"\1 \2", s)

def _repair_split_taxa(lines):
    """분류군 토큰이 페이지 경계에서 쪼개진 경우 복원 (예: '관속식'+'물? 옥구슬이끼…')."""
    out, i = [], 0
    while i < len(lines):
        cur = lines[i].strip()
        merged = False
        if i + 1 < len(lines) and len(cur) >= 2:
            for T in TONG_TAXA:
                if cur != T and T.startswith(cur):
                    suf = T[len(cur):]
                    if lines[i + 1].startswith(suf):
                        rest = lines[i + 1][len(suf):].lstrip(" ?")
                        out.append(f"{T} {rest}")
                        i += 2; merged = True; break
        if not merged:
            out.append(lines[i]); i += 1
    return out

def _is_header(ln):
    if "•" in ln or ln.startswith("====="):
        return True
    return ln.startswith(("분류군","초판","개정판","범주","현황","페이지",
                          "평가범주","평가기준","찾아보기","4. 찾아보기"))

def _unwrap_tonghap(lines):
    """분류군으로 시작하는 행을 레코드 시작으로 보고, 줄바꿈된 연속행을 병합."""
    records, buf = [], None
    for ln in lines:
        toks = ln.split()
        if toks and toks[0] in TONG_TAXA:
            if buf: records.append(buf)
            buf = ln
        elif buf is not None and not _is_header(ln):
            buf += " " + ln                          # 연속행(저자·기준 등) 병합
    if buf: records.append(buf)
    return records

def parse_tonghap(lines):
    rows = []
    for ln in _unwrap_tonghap(_repair_split_taxa(lines)):
        toks = deglue(ln).split()                    # 붙은 코드 분리 후 토큰화
        if len(toks) < 4 or toks[0] not in TONG_TAXA:
            continue
        taxon = toks[0]
        # 한글명: 분류군 다음부터 첫 라틴 토큰 전까지 (없을 수 있음 — 학명만 있는 종)
        i = 1
        while i < len(toks) and HANGUL.search(toks[i]) and not is_latin(toks[i]):
            i += 1
        kor = " ".join(toks[1:i])
        # 학명: 첫 라틴 ~ 첫 코드 토큰 전까지
        j = i
        while j < len(toks) and strip_punct(toks[j]) not in CODES:
            j += 1
        sci = " ".join(toks[i:j]).strip()
        # 개정판 평가범주 = 가장 오른쪽 코드 토큰
        code_idx = [k for k,t in enumerate(toks) if strip_punct(t) in CODES]
        if not sci or not code_idx:                  # 학명+코드 없으면 비데이터행
            continue
        code = strip_punct(toks[code_idx[-1]])
        rows.append({"분류군명":taxon, "학명":sci, "한글명":kor,
                     "적색목록코드":code, "source_year":"2024(통합본)"})
    return rows

def parse_gonchung(lines):
    rows = []
    for ln in lines:
        toks = deglue(ln).split()
        if len(toks) < 3 or not toks[-1].lstrip("-").isdigit():
            continue
        if not HANGUL.search(toks[0]) or is_latin(toks[0]):  # 한글명으로 시작
            continue
        i = 0
        while i < len(toks) and HANGUL.search(toks[i]) and not is_latin(toks[i]):
            i += 1
        kor = " ".join(toks[:i])
        j = i
        while j < len(toks) and strip_punct(toks[j]) not in CODES:
            j += 1
        sci = " ".join(toks[i:j]).strip()
        code_idx = [k for k,t in enumerate(toks) if strip_punct(t) in CODES]
        if not kor or not sci or not code_idx:
            continue
        code = strip_punct(toks[code_idx[0]])        # 곤충IV는 단일 범주(첫 코드)
        rows.append({"학명":sci, "한글명":kor, "적색목록코드":code})
    return rows

def main():
    tong = parse_tonghap(read_pdf_lines(PDF_TONG))
    gon  = parse_gonchung(read_pdf_lines(PDF_GON))

    # 통합본 인덱스(학명/한글명 → row)
    by_sci = {norm_sci(r["학명"]): r for r in tong if norm_sci(r["학명"])}
    by_kor = {norm_kor(r["한글명"]): r for r in tong}

    updated = appended = 0
    for g in gon:
        ks, kk = norm_sci(g["학명"]), norm_kor(g["한글명"])
        hit = by_sci.get(ks) or by_kor.get(kk)
        if hit:                                       # 중복 → 2025로 업데이트
            hit["적색목록코드"] = g["적색목록코드"]
            hit["source_year"] = "2025(곤충IV)"
            updated += 1
        else:                                         # 비중복 → row-bind
            tong.append({"분류군명":"곤충4", "학명":g["학명"], "한글명":g["한글명"],
                         "적색목록코드":g["적색목록코드"], "source_year":"2025(곤충IV)"})
            appended += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["분류군명","학명","한글명","적색목록코드","source_year"])
        w.writeheader(); w.writerows(tong)

    # 요약
    from collections import Counter
    print(f"통합본 파싱: {len(tong)-appended}행 | 곤충IV 파싱: {len(gon)}행")
    print(f"병합: 업데이트 {updated} · 신규추가 {appended} · 최종 {len(tong)}행")
    print("분류군 분포:", dict(Counter(r['분류군명'] for r in tong)))
    print("적색목록코드 분포:", dict(Counter(r['적색목록코드'] for r in tong)))
    print("출력:", OUT)
    print("\n[샘플 5행]")
    for r in tong[:5]:
        print(" ", r)
    print("\n[곤충4 신규 샘플 3행]")
    for r in [x for x in tong if x['분류군명']=='곤충4'][:3]:
        print(" ", r)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
