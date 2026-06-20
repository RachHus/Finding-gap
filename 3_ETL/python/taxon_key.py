# -*- coding: utf-8 -*-
"""학명 정규화 키 — 종(2명법)/아종(3명법) 매칭용 공통 모듈.
- 저자명·연도·괄호 제거. 아종은 3번째 토큰이 '소문자'일 때만(저자명은 대문자) 인정.
- 가장 하위 관리 단위 = 아종. 변종/품종(var./forma) 토큰은 연결어로 제거 → 종/아종으로 폴드.
"""
import re

CONNECTORS = {"subsp", "ssp", "var", "subvar", "forma", "fo", "f", "cv", "sp", "spp", "aff", "cf"}


def _tokens(name):
    s = re.sub(r"\([^)]*\)", " ", name or "")        # 괄호(저자/아속) 제거
    toks = re.findall(r"[A-Za-z]+", s)               # 알파 토큰(대소문자 보존)
    return [t for t in toks if t.lower() not in CONNECTORS]


def sci_keys(name):
    """학명 문자열 → (binomial, trinomial|None). 저자명이 아종으로 새지 않게 소문자 판정."""
    t = _tokens(name)
    if len(t) < 2:
        return None, None
    g, sp = t[0].lower(), t[1].lower()
    binom = f"{g} {sp}"
    trinom = f"{g} {sp} {t[2].lower()}" if len(t) >= 3 and t[2][:1].islower() else None
    return binom, trinom


def managed_key(name):
    """가장 구체적인 관리키: 아종 있으면 3명법, 없으면 2명법."""
    b, tr = sci_keys(name)
    return tr or b


def ktsn_keys(gnus, specs, sspecs):
    """KTSN 정제 필드(속·종·아종)로 키 생성 — 저자명 없는 깨끗한 값."""
    g = (gnus or "").strip().lower()
    sp = (specs or "").strip().lower()
    ss = (sspecs or "").strip().lower()
    if not (g and sp):
        return None, None
    binom = f"{g} {sp}"
    trinom = f"{g} {sp} {ss}" if ss else None
    return binom, trinom
