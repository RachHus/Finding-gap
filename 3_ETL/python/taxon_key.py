# -*- coding: utf-8 -*-
"""학명 정규화 키 — 종(2명법)/아종(3명법) 매칭용 공통 모듈.
- 저자명·연도·괄호 제거. 아종은 소문자 종소명일 때만 인정한다(저자명은 대문자로 시작한다).
- 이음줄 종소명(Vaccinium vitis-idaea·Nymphalis l-album)은 한 토큰으로 둔다. 자료마다 붙임표를
  하이픈·en dash 로 뒤섞어 쓰므로 모두 하이픈으로 맞춘 뒤에 자른다.
- 아종 자리에 올 수 없는 값(소문자 저자 접두사 van·von·d'·du…, 두 글자 이하)은 걸러 낸다.
- 가장 하위 관리 단위 = 아종. 변종/품종(var./forma)은 그 아래 이름까지 함께 버려 종·아종으로 폴드한다.
"""
import re

SUBSPECIES = {"subsp", "ssp"}                                   # 뒤에 오는 이름이 아종이다
VARIETY = {"var", "subvar", "forma", "fo", "f", "cv"}           # 뒤에 오는 이름은 관리 단위가 아니다
VAGUE = {"sp", "spp", "aff", "cf"}                              # 미동정 표기
CONNECTORS = SUBSPECIES | VARIETY | VAGUE

# 저자명에 붙는 소문자 접두사 — 소문자라서 아종처럼 보이지만 분류명이 아니다.
AUTHOR_PARTICLES = {"van", "von", "der", "den", "del", "della", "de", "da", "di", "do", "du",
                    "dos", "das", "la", "le", "les", "ten", "ter", "af", "av", "zu", "el", "al",
                    "ab", "abu", "bin", "ibn", "mac", "mc", "st", "saint", "san", "y", "e", "i", "o"}

DASHES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-",
                        "\u2013": "-", "\u2014": "-", "\u2212": "-"})


def norm_dash(s):
    """붙임표 표기 통일 — 자료마다 하이픈·en dash 를 섞어 쓴다."""
    return (s or "").translate(DASHES)


def _tokens(name):
    s = re.sub(r"\([^)]*\)", " ", norm_dash(name))   # 괄호(저자/아속) 제거
    return [t for t in (x.strip("-") for x in re.findall(r"[A-Za-z][A-Za-z-]*", s)) if t]


def _is_epithet(tok):
    """아종 자리에 올 수 있는 토큰인가 — 소문자 분류명이고 저자 접두사가 아니어야 한다."""
    t = (tok or "").lower()
    return len(t) >= 3 and tok[:1].islower() and t not in AUTHOR_PARTICLES


def sci_keys(name):
    """학명 문자열 → (binomial, trinomial|None)."""
    t = _tokens(name)
    if len(t) < 2:
        return None, None
    binom = f"{t[0].lower()} {t[1].lower()}"         # 속·종 자리는 연결어 판정을 하지 않는다(Xylota fo)
    sub = None
    i = 2
    while i < len(t):
        low = t[i].lower()
        if low in VARIETY:                           # 변종·품종부터는 관리 단위 밖이다
            break
        if low in SUBSPECIES:
            nxt = t[i + 1] if i + 1 < len(t) else ""
            if _is_epithet(nxt):
                sub = nxt.lower()
            break
        if low in VAGUE:
            i += 1
            continue
        if _is_epithet(t[i]):                        # 연결어 없는 3명법
            sub = low
        break
    return binom, (f"{binom} {sub}" if sub else None)


def is_variety(name):
    """변종·품종 이름인가 — 관리 단위(종·아종) 아래라서 그 위 이름을 대신하지 못한다."""
    t = _tokens(name)
    i = 2
    while i < len(t):
        low = t[i].lower()
        if low in SUBSPECIES:
            return False
        if low in VARIETY:
            return i + 1 < len(t) and _is_epithet(t[i + 1])
        i += 1
    return False


def managed_key(name):
    """가장 구체적인 관리키: 아종 있으면 3명법, 없으면 2명법."""
    b, tr = sci_keys(name)
    return tr or b


def ktsn_keys(gnus, specs, sspecs):
    """KTSN 정제 필드(속·종·아종)로 키 생성 — 저자명 없는 깨끗한 값."""
    g = norm_dash(gnus).strip().lower()
    sp = norm_dash(specs).strip().lower()
    ss = norm_dash(sspecs).strip().lower()
    if not (g and sp):
        return None, None
    binom = f"{g} {sp}"
    trinom = f"{g} {sp} {ss}" if ss else None
    return binom, trinom
