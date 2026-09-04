# -*- coding: utf-8 -*-
"""전국 걷기판을 굽는다.

세 구역만 걸을 수 있던 것을 남한 전체로 넓힌다. 칸은 여전히 서비스의 1km 격자
105,340칸이고, 칸에 붙는 값도 전부 서비스 자료에서 나온다.

좌표를 싣지 않는 것이 크기의 관건이다. 격자는 투영 좌표계에서 규칙적이라
칸 번호(행·열)에서 경위도를 3차 다항식으로 되살릴 수 있다 — 실측 최대 오차가
경도 13.6m·위도 7.1m 로 1km 칸의 1.4% 다. 좌표 배열 843KB 가 계수 20개로 줄어든다.

굽는 것
  mask   칸이 있는 자리(612x650 비트맵)   — 바다·격자 밖을 가른다
  dem    고도(m)
  ndvi   식생지수 x100
  ndwi   수분지수 x100
  sord   하천 차수 0~7
  bio01  연평균기온 x10        ─ 아래 넉 장은 칸에서 종을 되짚기 위한 것이다
  bio03  기온 하루 변동 x10
  bio14  가장 마른 달 강수량
  bio18  가장 더운 철 강수량
  env    일곱 층이 모두 있는 칸(1비트) — 없는 칸은 모형을 못 돌린다
  sg     시군구 인덱스
  hot    이 칸을 "잘 맞음" 으로 판정한 종 수(모형 있는 8,878종 합산)
  tier   도감 종별 후보 등급 0~3 (2비트)
  rec    도감 종별 기록 있는 칸 (1비트)

서식지 모형이 쓰는 변수는 일곱 개뿐이다(dem·ndvi·bio01 은 모든 종, bio18 69%,
bio03 53%, bio14 42%, sord 5%). 그 일곱을 원본 정밀도로 실으면 브라우저가 칸 하나에서
7,977종을 그 자리에서 채점할 수 있다 — 미리 구워 둔 종만 보여 주는 것과 다르다.
그래서 식생지수도 1/100 로 접지 않고 원본 1/1000 로 싣는다. 접으면 판정이 뒤집히는 칸이
0.23% 생기는데, 하필 문턱에 걸친 종들이라 목록 끝에서 종이 들락거린다.

출력 walkgrid.json(머리말) + walkgrid.bin.gz(본문).
"""
import gzip
import json
import os

import numpy as np

import paths
import suit

HERE = os.path.dirname(os.path.abspath(__file__))
STRIDE = 650
DEG = 3


def polyfit_lonlat(row, col, lon, lat):
    """칸 번호에서 경위도를 되살리는 계수. 항 순서는 화면 쪽과 맞춰야 한다."""
    rm, cm, s = float(row.mean()), float(col.mean()), 100.0
    rc, cc = (row - rm) / s, (col - cm) / s
    terms, names = [], []
    for i in range(DEG + 1):
        for j in range(DEG + 1 - i):
            terms.append((cc ** i) * (rc ** j))
            names.append((i, j))
    A = np.vstack(terms).T
    bl = np.linalg.lstsq(A, lon, rcond=None)[0]
    bt = np.linalg.lstsq(A, lat, rcond=None)[0]
    err_lon = float(np.abs(A @ bl - lon).max()) * 88000
    err_lat = float(np.abs(A @ bt - lat).max()) * 111000
    return {'deg': DEG, 'rmean': rm, 'cmean': cm, 'div': s,
            'terms': names, 'lon': bl.tolist(), 'lat': bt.tolist()}, err_lon, err_lat


def pack2(a):
    """0~3 값을 셀당 2비트로 접는다."""
    b = np.stack([(a >> 1) & 1, a & 1], axis=1).reshape(-1)
    return np.packbits(b)


def main():
    g = suit.grid()
    e = suit.envm()
    S = g['scale']
    cid = np.array(g['cid'], dtype=np.int64)
    assert (np.diff(cid) > 0).all(), '격자 번호가 오름차순이 아니다'
    n = len(cid)
    row, col = cid // STRIDE, cid % STRIDE
    R = int(row.max()) + 1

    lon = np.array(g['lon'], dtype=np.float64) / S['lon']
    lat = np.array(g['lat'], dtype=np.float64) / S['lat']
    poly, el, et = polyfit_lonlat(row.astype(float), col.astype(float), lon, lat)
    print('좌표 복원 오차 — 경도 %.1f m · 위도 %.1f m' % (el, et))

    # +650 이 남쪽인지 자료에 물어본다. 짐작하면 걸음이 뒤집힌다.
    pos = {int(c): i for i, c in enumerate(cid)}
    d = [lat[pos[int(c) + STRIDE]] - lat[pos[int(c)]] for c in cid[:4000] if int(c) + STRIDE in pos]
    south = bool(sum(d) / len(d) < 0)

    mask = np.zeros(R * STRIDE, dtype=bool)
    mask[row * STRIDE + col] = True

    def i16(v):
        return np.array([0 if q is None else q for q in v], dtype=np.int64).astype(np.int16)

    def i8(v, div):
        # 내림이 아니라 반올림이다. 음수인 수분지수에서 내림은 늘 한 칸 아래로 밀린다.
        a = np.rint(np.array([0 if q is None else q for q in v], dtype=np.float64) / div)
        return np.clip(a, -128, 127).astype(np.int8)

    hot = np.load(os.path.join(HERE, '_hotspot.npz'))['hi'].astype(np.uint16)

    # 모형이 쓰는 일곱 층. 빠진 값은 0 으로 채우고 어느 칸이 성한지는 따로 표시한다 —
    # 0 을 실제 값으로 읽으면 영하 0도·강수 0mm 인 칸이 되어 엉뚱한 종이 맞는다고 나온다.
    def raw(key, dt):
        src = g if isinstance(g.get(key), list) else e
        a = np.array([0 if q is None else q for q in src[key]], dtype=np.int64)
        assert a.min() >= np.iinfo(dt).min and a.max() <= np.iinfo(dt).max, key + ' 가 형식을 넘는다'
        return a.astype(dt)

    envok = np.ones(n, dtype=bool)
    for key in ('dem', 'ndvi', 'bio01', 'bio03', 'bio14', 'bio18', 'sord'):
        src = g if isinstance(g.get(key), list) else e
        envok &= np.array([q is not None for q in src[key]])
    print('일곱 층이 모두 있는 칸 %s / %s' % (format(int(envok.sum()), ','), format(n, ',')))

    dex = json.load(open(os.path.join(HERE, 'dex_full.json'), encoding='utf-8'))['dex']
    tiers, recs, has = [], [], []
    for x in dex:
        r = suit.candidate(x['t'], x['k'])
        tiers.append(pack2((r['tier'] if r else np.zeros(n, dtype=np.int8)).astype(np.uint8)))
        has.append(bool(r))
        oc = (suit.cells(x['t']).get(x['k']) or {}).get('c', [])
        m = np.zeros(n, dtype=bool)
        if oc:
            m = np.isin(cid, np.array(oc, dtype=np.int64))
        recs.append(np.packbits(m))
    print('도감 %d칸 중 후보 등급을 낼 수 있는 종 %d' % (len(dex), sum(has)))

    blocks = [
        ('mask', np.packbits(mask), 'u8', 1),
        ('dem', i16(g['dem']), 'i16', 1),
        ('ndvi', i16(g['ndvi']), 'i16', S['ndvi']),
        ('ndwi', i8(g['ndwi'], S['ndwi'] // 100), 'i8', 100),
        ('sord', np.array(e['sord'], dtype=np.uint8), 'u8', 1),
        ('bio01', raw('bio01', np.uint8), 'u8', 10),
        ('bio03', raw('bio03', np.uint16), 'u16', 10),
        ('bio14', raw('bio14', np.uint8), 'u8', 1),
        ('bio18', raw('bio18', np.uint16), 'u16', 1),
        ('env', np.packbits(envok), 'u8', 1),
        ('sg', np.array(g['sg'], dtype=np.int64).astype(np.uint8), 'u8', 1),
        ('hot', hot, 'u16', 1),
        ('tier', np.concatenate(tiers), 'u8', 1),
        ('rec', np.concatenate(recs), 'u8', 1),
    ]
    assert int(np.array(g['sg']).max()) < 255, '시군구 인덱스가 uint8 을 넘는다'

    # 형식배열은 시작 자리가 원소 크기의 배수여야 한다. 4바이트에 맞춰 채운다 —
    # 안 맞추면 브라우저가 Int16Array 를 만들 때 그대로 거부한다.
    buf, layers, off = bytearray(), [], 0
    for key, arr, kind, sc in blocks:
        pad = (-off) % 4
        buf += b'\0' * pad
        off += pad
        b = arr.tobytes()
        layers.append({'key': key, 'type': kind, 'off': off, 'bytes': len(b), 'scale': sc})
        buf += b
        off += len(b)
        print('  %-6s %-4s %10s B  자리 %s' % (key, kind, format(len(b), ','), format(off - len(b), ',')))

    raw = bytes(buf)
    gzb = gzip.compress(raw, 9)
    out_bin = os.path.join(paths.OUT, 'walkgrid.bin.gz')
    open(out_bin, 'wb').write(gzb)

    # 지역 이름표는 서비스가 쓰는 것을 그대로 옮긴다 — 화면에 코드가 뜨면 안 된다.
    import re
    RG = json.loads(re.sub(r'^window\.__REGGAP__=', '',
                           open(os.path.join(paths.DATA, 'region_gaps.js'), encoding='utf-8')
                           .read().strip().rstrip(';'), count=1))
    sido = RG.get('sido', {})
    sgname = {}
    for code, v in RG.get('sg', {}).items():
        pref = sido.get(v[1])
        pref = (pref[0] if isinstance(pref, list) else pref) or ''
        sgname[code] = (pref + ' ' + v[0]).strip()

    # 시군구마다 내려놓을 칸 하나. 전국 어디로든 걸어갈 수 있으니 자리를 찾아 주는 것이
    # 화면의 절반이다 — 이름으로 골라 그 칸에 내려놓는다.
    #
    # 그냥 한가운데를 잡으면 완도처럼 섬이 흩어진 곳에서 평균이 바다에 떨어져, 붙어 있는
    # 갯바위 칸으로 내려간다(맞을 만한 종 0종). 그래서 그 시군구에서 맞을 만한 종이
    # 중앙값 이상인 칸만 남기고 그중 한가운데에 가까운 것을 고른다 — 가운데이면서
    # 그 지역다운 칸이 된다.
    sgi = np.array(g['sg'], dtype=np.int64)
    center = {}
    for s in np.unique(sgi):
        idx = np.flatnonzero(sgi == s)
        mx, my = lon[idx].mean(), lat[idx].mean()
        keep = idx[hot[idx] >= np.median(hot[idx])] if len(idx) > 3 else idx
        j = keep[np.argmin((lon[keep] - mx) ** 2 + (lat[keep] - my) ** 2)]
        center[g['sgcodes'][int(s)]] = int(cid[j])

    # 골라 둔 출발지. 자료가 고른 것이라 설명이 곧 근거다.
    def pick(code, key, big=True):
        m = sgi == g['sgcodes'].index(code)
        idx = np.flatnonzero(m)
        return int(cid[idx[np.argmax(key[idx] if big else -key[idx])]])

    ndwi_v = np.array([-9 if q2 is None else q2 for q2 in g['ndwi']], dtype=np.float64) / S['ndwi']
    dem_v = np.array(g['dem'], dtype=np.float64)
    starts = [
        {'cid': center['11010'], 'title': '서울 종로구', 'why': '기록이 가장 촘촘한 곳 — 흔한 종이 어떻게 흔한지 보인다'},
        {'cid': center['35530'], 'title': '전북 무주군', 'why': '산이 높고 기록이 드문 곳 — 공백이 무엇인지 보인다'},
        {'cid': pick('36660', hot.astype(np.float64)), 'title': '전남 완도군', 'why': '맞을 만한 종이 가장 많은데 도감 종 기록은 없는 곳'},
        {'cid': pick('39020', ndwi_v), 'title': '제주 서귀포시', 'why': '전국에서 가장 젖은 칸 — 물가에 무엇이 오는지'},
        {'cid': pick('32590', dem_v), 'title': '강원 인제군', 'why': '가장 높은 곳 — 고도가 무엇을 가르는지'},
    ]

    q = [50, 75, 90, 95, 99]
    head = {
        # 지도(bin)-대화(fg_*) 자료 기준일 대조용. char-chat 이 요청의 dataVersion 을
        # fg_meta.generated 와 견줘 다르면 안내를 붙인다. 재빌드 때 meta.generated 와
        # 같은 날짜를 FG_GEN_DATE 로 넣어라(미설정=null=대조 꺼짐, 오탐 방지).
        'dataver': os.environ.get('FG_GEN_DATE') or None,
        'center': center, 'starts': starts,
        'n': n, 'rows': R, 'cols': STRIDE, 'stride': STRIDE, 'south': south,
        'poly': poly, 'polyErrM': {'lon': round(el, 1), 'lat': round(et, 1)},
        'layers': layers, 'bytes': len(raw), 'gz': len(gzb),
        'sgcodes': g['sgcodes'], 'sgname': sgname,
        'slots': [x['no'] for x in dex], 'hasModel': has,
        'hotBreaks': {str(k): int(np.percentile(hot, k)) for k in q},
        'demBreaks': {str(k): int(np.percentile(np.array(g['dem']), k)) for k in q},
        'ndwiP95': round(float(np.percentile(i8(g['ndwi'], S['ndwi'] // 100), 95)) / 100, 3),
        'nsp': int(json.load(open(os.path.join(HERE, '_hotspot_meta.json'), encoding='utf-8'))['nsp']),
    }
    json.dump(head, open(os.path.join(paths.OUT, 'walkgrid.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))
    print('walkgrid.bin.gz %s B (푼 크기 %s B) · walkgrid.json %s B'
          % (format(len(gzb), ','), format(len(raw), ','),
             format(os.path.getsize(os.path.join(paths.OUT, 'walkgrid.json')), ',')))


if __name__ == '__main__':
    main()
