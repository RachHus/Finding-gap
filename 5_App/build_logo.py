# -*- coding: utf-8 -*-
"""로고 및 아이콘 자산 생성

산출:
  기본 (옵션 없을 때):
    - 5_App/logo.png (헤더 로고, 높이 72px 고정)
    - 5_App/favicon.ico (16/32/48/64px 다중 해상도)
    - 5_App/apple-touch-icon.png (iOS 홈화면, 180×180px)
    - 5_App/icon-512.png (Android, 512×512px)

  --brands 옵션:
    - logo_nibr.png (NIBR 로고, 온라인 내려받기)
    - logo_ecobank.png (EcoBank 로고, 온라인 내려받기)
    - logo_naturing.png (Naturing 로고, 로컬 원본)
    - logo_report.png (발견제보 로고, 로컬 원본)
    - logo_quiz.png (종동정퀴즈 로고, 로컬 원본)

입력:
  - 4_References/finding_gap_logo.png (헤더/파비콘 원본, 1448×1086)
  - 4_References/naturing_logo.jfif (제보 기관 마크)
  - 4_References/발견제보_logo.png (제보 자산 로고)
  - 4_References/종동정퀴즈_logo.png (퀴즈 자산 로고)

처리:
1) 헤더 로고 (기본 실행)
   - 4_References/finding_gap_logo.png 의 흰 여백을 자르고 흰 배경을 투명으로 변환
   - CSS 표시 높이 72px 에 맞춰 2배 고밀도로 축약 (CSS 1x 픽셀 ≈ 실제 2x 픽셀)
   - 결과: 최적화된 PNG, 약 10~20KB

2) 파비콘류
   - 헤더 로고 중 배지(워드마크 앞의 돋보기+동물 아이콘, 좌상단)만 추출
   - 정사각형 캔버스에 배치: favicon.ico 64×64, icon-512.png 512×512
   - apple-touch-icon.png는 iOS 노치 고려해 180×180 투명 배경에 배치

3) 기관 마크 (--brands 옵션)
   - NIBR, EcoBank: 온라인 로고를 내려받아 최적화
   - Naturing, 발견제보, 종동정퀴즈: 로컬 원본 파일 사용 (안내 기관 제공)
   - 모든 로고를 표시 크기 높이 26~30px, 폭 30~116px로 정규화
   - 흰 배경/반투명 가장자리 처리: KEY_LO/KEY_HI 임계로 투명화

온라인 내려받기 링크가 끊기면 기존 파일 유지 (덮어쓰지 않음).
로컬 원본 파일이 없으면 해당 로고 건너뜀.

실행:
  python 5_App/build_logo.py           # 헤더 로고 + 파비콘류만
  python 5_App/build_logo.py --brands  # 모든 로고 (기관 마크 포함)

배포: build_dist.py 의 PAGES 리스트에 있어 정적 배포본에 포함됨
"""
import sys
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageOps

APP = Path(__file__).resolve().parent
SRC = APP.parent / "4_References" / "finding_gap_logo.png"
OUT = APP / "logo.png"

# 파비콘용 배지 크롭 — load_master() 크롭 좌표계 기준(원본이 바뀌면 재조정 필요).
# 워드마크 시작 전, 돋보기+동물 아이콘 배지만 담는 영역.
FAVICON_BADGE = (0, 0, 412, 469)
FAVICON_ICO = APP / "favicon.ico"
TOUCH_ICON = APP / "apple-touch-icon.png"
ICON_512 = APP / "icon-512.png"
TOUCH_BG = (250, 250, 248, 255)   # --bg — iOS는 투명배경을 임의로 채우므로 미리 채워둠

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


def load_master():
    """원본(4_References/finding_gap_logo.png)의 여백을 자르고 흰 배경을 투명화해
    원본 해상도 그대로 반환. 헤더 로고·OG 카드(build_profiles.py)가 함께 쓴다."""
    if not SRC.exists():
        return None
    im = Image.open(SRC).convert("RGBA")
    px = im.load()
    W, H = im.size
    minx, miny, maxx, maxy = W, H, 0, 0
    for y in range(H):
        for x in range(W):
            if 255 - min(px[x, y][:3]) > 12:
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
    box = (max(0, minx - PAD), max(0, miny - PAD), min(W, maxx + 1 + PAD), min(H, maxy + 1 + PAD))
    im = im.crop(box)
    return key_white(im, KEY_LO, KEY_HI)


def _fit_square(im, size, pad_ratio=0.08):
    """비율 유지한 채 size×size 투명 캔버스 중앙에 배치."""
    pad = round(size * pad_ratio)
    avail = size - 2 * pad
    s = min(avail / im.width, avail / im.height)
    w, h = max(1, round(im.width * s)), max(1, round(im.height * s))
    resized = im.resize((w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(resized, ((size - w) // 2, (size - h) // 2))
    return canvas


def build_favicons(master=None):
    """헤더 로고와 같은 원본에서 배지(워드마크 앞부분)만 잘라 파비콘류 생성."""
    master = master if master is not None else load_master()
    if master is None:
        print("  원본 없음 → 파비콘 건너뜀")
        return
    badge = master.crop(FAVICON_BADGE)

    _fit_square(badge, 512).save(ICON_512, optimize=True)
    _fit_square(badge, 256, pad_ratio=0.04).save(FAVICON_ICO, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

    touch = Image.new("RGBA", (180, 180), TOUCH_BG)
    inset = _fit_square(badge, 164, pad_ratio=0)
    touch.alpha_composite(inset, (8, 8))
    touch.convert("RGB").save(TOUCH_ICON)

    print(f"  favicon.ico · apple-touch-icon.png · icon-512.png (배지 {badge.size[0]}×{badge.size[1]} 기준)")


def main():
    if "--brands" in sys.argv:
        print("[기관 마크]")
        build_brands()
        print("[전달받은 마크]")
        build_locals()
        return 0
    im = load_master()
    if im is None:
        print(f"원본 없음: {SRC}")
        return 1
    w, h = im.size

    tw = round(w * (DISPLAY_H * SCALE) / h)
    header = im.resize((tw, DISPLAY_H * SCALE), Image.LANCZOS)
    header.save(OUT, optimize=True)
    print("[파비콘]")
    build_favicons(im)
    print(f"{OUT.name}: {header.size[0]}×{header.size[1]} · {OUT.stat().st_size/1024:.0f} KB "
          f"(표시 {tw//SCALE}×{DISPLAY_H})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
