# -*- coding: utf-8 -*-
"""조사기록 종명 보정 매핑 — KTSN 정명 재배치·종분할로 자동매칭이 틀리는 케이스를 정명 ktsn으로 강제.

배경: KTSN 마스터는 '정명'만 목록화한다. API 응답엔 정명여부(corsynSeYn) 필드가 있으나, 분류군별
  검색(schTxgrpGroupCd)으로는 N(이명)이 거의 반환되지 않는다(실측 40,660건 중 N 9건·대부분 무효).
  따라서 조사기록이 옛 학명/통합명을 쓰면 (1) 다른 정명으로 잘못 매칭되거나(예: Parus major→큰박새)
  (2) 미매칭된다(예: 꼬리치레도롱뇽 분할). 이 표가 그런 이름을 정명 ktsn으로 직접 보정한다.
  (이명 자동 확보 경로는 build_synonyms.py + fetch_nibr_ktsn.py synall 참조 — ktsn_synonyms.csv)

우선순위: override > (학명·국명 일반 매칭/충돌판정). 즉 override에 걸리면 충돌이어도 지정 ktsn으로 확정.
확장: 4_References/ktsn_name_overrides.csv 에 행 추가(reconcile_unmatched.py 후보를 검토해 승격).

CSV 컬럼: match_name, match_type(sci|kor), accepted_ktsn, accepted_name, reason, note
"""
import csv
import re
from pathlib import Path
from taxon_key import managed_key

BASE = Path(__file__).resolve().parents[2]
OVERRIDES = BASE / "4_References" / "ktsn_name_overrides.csv"
ALIASES = BASE / "1_Data" / "processed" / "ktsn_aliases.csv"     # build_ktsn_master 산출(변종/품종 폴딩 복원)
SYNONYMS = BASE / "1_Data" / "processed" / "ktsn_synonyms.csv"   # build_synonyms 산출(KTSN corsynSeYn=N 이명)


def _kor(s):
    return re.sub(r"\s+", "", s or "")


def load_overrides():
    """→ (ov_sci: managed_key→ktsn, ov_kor: 정규화국명→ktsn). 파일 없으면 빈 dict."""
    ov_sci, ov_kor = {}, {}
    if not OVERRIDES.exists():
        return ov_sci, ov_kor
    for r in csv.DictReader(OVERRIDES.open(encoding="utf-8-sig")):
        nm = (r.get("match_name") or "").strip()
        ktsn = (r.get("accepted_ktsn") or "").strip()
        typ = (r.get("match_type") or "").strip().lower()
        if not nm or not ktsn:
            continue
        if typ == "sci":
            k = managed_key(nm)
            if k:
                ov_sci[k] = ktsn
        elif typ == "kor":
            ov_kor[_kor(nm)] = ktsn
    return ov_sci, ov_kor


def load_aliases():
    """이명/별칭 → (al_sci: managed_key→ktsn, al_kor: 정규화국명→ktsn). load_master 가 gap-fill.
    두 출처를 합산(존재하는 것만): ① ktsn_aliases.csv(변종/품종 폴딩 복원) ②
    ktsn_synonyms.csv(KTSN corsynSeYn=N 정식 이명, build_synonyms 산출). 먼저 들어온 키 우선."""
    al_sci, al_kor = {}, {}
    for path in (ALIASES, SYNONYMS):
        if not path.exists():
            continue
        for r in csv.DictReader(path.open(encoding="utf-8-sig")):
            nm = (r.get("alias_name") or "").strip()
            ktsn = (r.get("accepted_ktsn") or "").strip()
            typ = (r.get("alias_type") or "").strip().lower()
            if not nm or not ktsn:
                continue
            if typ == "sci":
                k = managed_key(nm)
                if k and k not in al_sci:
                    al_sci[k] = ktsn
            elif typ == "kor":
                kk = _kor(nm)
                if kk and kk not in al_kor:
                    al_kor[kk] = ktsn
    return al_sci, al_kor
