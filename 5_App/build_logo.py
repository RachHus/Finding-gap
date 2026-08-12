# -*- coding: utf-8 -*-
"""로고 자산 생성

1) 헤더 로고 — 4_References/finding_gap_logo.png → 5_App/logo.png
   원본은 1448×1086 에 흰 여백이 절반 가까이라 그대로 쓰면 870KB 다. 여백을 잘라내고
   흰 배경을 투명으로 바꿔(페이지 배경이 순백이 아니라 네모가 드러난다) 표시 높이의 2배로 줄인다.

2) 제보·상세 링크의 기관 마크 — `--brands` 로 각 사이트에서 내려받아 5_App/logo_*.png 생성.
   핫링크하지 않는 이유: naturing 은 짧은 시간에 여러 번 요청하면 IP 를 막고,
   기관 사이트는 리퍼러 검사가 바뀔 수 있다. 링크가 끊기면 버튼이 빈칸이 된다.

3) 전달받은 원본 마크 — `--brands` 에 함께 딸려 나온다. 내려받은 것과 달리 알파가 없고
   흰 배경에 얹힌 그림이라, 헤더 로고와 같은 흰색 키잉을 거쳐야 버튼 위에서 네모가 되지 않는다.

사용: python 5_App/build_logo.py [--brands]
"""
import sys
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageOps

APP = Path(__file__).resolve().parent
SRC = APP.parent / "4_References" / "finding_gap_logo.png"
OUT = APP / "logo.png"

BRAND_H = 26        # 버튼 안 마크의 표시 높이(px) 상한
BRAND_W = 116       # 같은 폭 상한 — 가로로 긴 워드마크가 상자를 넘지 않게
BRANDS = [
    # (출력명, 원본 URL, 칠할 색 or None, 알파 반전 여부)
    ("logo_nibr.png", "https://species.nibr.go.kr/nibr/images/common/head_logo.png", None, False),
    ("logo_ecobank.png", "https://www.nie-ecobank.kr/static/img/2022/images/m_ecobank_logo.png", None, False),
    # naturing 마크는 내려받지 않는다 — 전달받은 원본이 4_References 에 있고(LOCAL), 그쪽이 정본이다.
]


def build_brands():
    ua = {"User-Agent": "Mozilla/5.0"}
    for name, url, tint, invert in BRANDS:
        try:
            with urlopen(Request(url, headers=ua), timeout=25) as r:
                data = r.read()
            im = Image.open(BytesIO(data)).convert("RGBA")
        except Exception as e:                      # 기존 파일을 남겨 둔다 — 덮어써서 깨뜨리지 않는다
            print(f"  - {name}: 내려받기 실패({e}) → 기존 파일 유지")
            continue
        bbox = im.split()[3].getbbox() or im.getbbox()
        im = im.crop(bbox)
        if invert:
            im.putalpha(ImageOps.invert(im.split()[3]))
            im = im.crop(im.split()[3].getbbox() or im.getbbox())
        if tint:
            a = im.split()[3]
            im = Image.new("RGBA", im.size, tint + (255,))
            im.putalpha(a)
        w, h = im.size
        s = min(BRAND_W / w, BRAND_H / h)
        dw, dh = max(1, round(w * s)), max(1, round(h * s))
        im = im.resize((dw * 2, dh * 2), Image.LANCZOS)
        p = APP / name
        im.save(p, optimize=True)
        print(f"  - {name}: {im.size[0]}×{im.size[1]} · {p.stat().st_size/1024:.1f} KB (표시 {dw}×{dh})")

DISPLAY_H = 72          # CSS 표시 높이(px)
SCALE = 2               # 고밀도 화면 대비
PAD = 6                 # 잘라낸 뒤 남길 여백(원본 픽셀)
KEY_LO, KEY_HI = 6, 30  # 흰색 판정: 흰색과의 거리 ≤LO 는 완전 투명, ≥HI 는 불투명, 사이는 가장자리 보간

# 전달받은 원본 마크 — (출력명, 원본 파일명, 표시 폭 상한, 표시 높이 상한, 흰색 판정 하한·상한)
# jfif 는 JPEG 라 글자 둘레에 링잉이 남는다. 하한을 6 으로 두면 그 링잉이 흐린 테로 살아남아
# 흰 버튼 위에 회색 얼룩이 생긴다 — 판정 폭을 넓혀 걷어낸다.
LOCAL = [
    ("logo_naturing.png", "naturing_logo.jfif", BRAND_W, BRAND_H, 16, 52),
    ("logo_report.png", "발견제보_logo.png", 30, 30, 8, 34),
    ("logo_quiz.png", "종동정퀴즈_logo.png", 26, 26, 8, 34),
]


def key_white(im, lo, hi):
    """흰 배경 → 투명. 가장자리(반투명)는 색을 되돌려(unpremultiply) 흰 테두리가 남지 않게 한다."""
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            d = 255 - min(r, g, b)
            if d <= lo:
                px[x, y] = (255, 255, 255, 0)
            elif d < hi:
                a = round(255 * (d - lo) / (hi - lo))
                f = 255 / a
                px[x, y] = (max(0, min(255, round(255 + (r - 255) * f))),
                            max(0, min(255, round(255 + (g - 255) * f))),
                            max(0, min(255, round(255 + (b - 255) * f))), a)
    return im


def build_locals():
    for name, src, mw, mh, lo, hi in LOCAL:
        p_src = APP.parent / "4_References" / src
        if not p_src.exists():
            print(f"  - {name}: 원본 없음({src}) → 기존 파일 유지")
            continue
        im = key_white(Image.open(p_src).convert("RGBA"), lo, hi)
        im = im.crop(im.split()[3].getbbox() or im.getbbox())
        w, h = im.size
        s = min(mw / w, mh / h)
        dw, dh = max(1, round(w * s)), max(1, round(h * s))
        im = im.resize((dw * SCALE, dh * SCALE), Image.LANCZOS)
        p = APP / name
        im.save(p, optimize=True)
        print(f"  - {name}: {im.size[0]}×{im.size[1]} · {p.stat().st_size/1024:.1f} KB (표시 {dw}×{dh})")


def main():
    if "--brands" in sys.argv:
        print("[기관 마크]")
        build_brands()
        print("[전달받은 마크]")
        build_locals()
        return 0
    if not SRC.exists():
        print(f"원본 없음: {SRC}")
        return 1
    im = Image.open(SRC).convert("RGBA")
    px = im.load()
    W, H = im.size

    # 내용 경계
    minx, miny, maxx, maxy = W, H, 0, 0
    for y in range(H):
        for x in range(W):
            if 255 - min(px[x, y][:3]) > 12:
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
    box = (max(0, minx - PAD), max(0, miny - PAD), min(W, maxx + 1 + PAD), min(H, maxy + 1 + PAD))
    im = im.crop(box)

    im = key_white(im, KEY_LO, KEY_HI)
    w, h = im.size

    tw = round(w * (DISPLAY_H * SCALE) / h)
    im = im.resize((tw, DISPLAY_H * SCALE), Image.LANCZOS)
    im.save(OUT, optimize=True)
    print(f"{OUT.name}: {im.size[0]}×{im.size[1]} · {OUT.stat().st_size/1024:.0f} KB "
          f"(표시 {tw//SCALE}×{DISPLAY_H})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
