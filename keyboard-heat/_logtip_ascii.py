"""把柴堆素材转成 ASCII 分类图，定位"炭化黑尖"的确切范围。

黑尖和木头暗面都是暗色，单看亮度分不开。区别在暖度：木柴是棕的（r 远大于 b），
炭化区是黑灰的（r≈b）。所以判据是二维的：亮度 + (r-b)。

ASCII 图里每个格子一格字符，直接看形状：
    '.' = 背景   '#' = 炭化黑尖   'w' = 木头

    .pyenv\\Scripts\\python.exe _logtip_ascii.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

ASSET = HERE / "assets" / "log-pile.png"

COLS = 76          # ASCII 图宽度
LUMA_BG = 40       # < 它 = 背景
DARK_MAX = 120     # 黑尖的亮度上限
WARM_MAX = 50      # 黑尖的 (r-b) 上限；木头远高于它


def main():
    try:
        from PIL import Image
    except ImportError:
        print("PIL missing")
        return 1

    im = Image.open(ASSET).convert("RGB")
    px = im.load()
    w, h = im.size

    # 内容 bbox
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if max(px[x, y]) >= LUMA_BG:
                x0 = min(x0, x); x1 = max(x1, x)
                y0 = min(y0, y); y1 = max(y1, y)
    cw, chh = x1 - x0 + 1, y1 - y0 + 1
    print("asset %s %dx%d" % (ASSET.name, w, h))
    print("content bbox x %d..%d y %d..%d  (%dx%d, aspect %.2f)"
          % (x0, x1, y0, y1, cw, chh, cw / float(chh)))

    rows = max(1, int(round(COLS * chh / float(cw) * 0.5)))   # 字符高宽比约 2:1
    print("grid %dx%d over content\n" % (COLS, rows))

    # 黑尖的精确 bbox
    dx0, dy0, dx1, dy1 = w, h, -1, -1

    lines = []
    for ry in range(rows):
        line = []
        for rx in range(COLS):
            # 取格子中心像素（网格比图小得多，采样足够）
            sx = x0 + int((rx + 0.5) * cw / COLS)
            sy = y0 + int((ry + 0.5) * chh / rows)
            pxv = px[min(sx, w - 1), min(sy, h - 1)]
            r, g, b = pxv
            m = max(r, g, b)
            if m < LUMA_BG:
                line.append(".")
            elif m < DARK_MAX and (r - b) < WARM_MAX:
                line.append("#")
            else:
                line.append("w")
        lines.append("".join(line) + "  u=%.2f" % ((ry + 0.5) / rows))

    # 逐像素扫黑尖 bbox（用与 ASCII 相同的判据）
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            r, g, b = px[x, y]
            m = max(r, g, b)
            if m >= LUMA_BG and m < DARK_MAX and (r - b) < WARM_MAX:
                dx0 = min(dx0, x); dx1 = max(dx1, x)
                dy0 = min(dy0, y); dy1 = max(dy1, y)

    for ln in lines:
        print("  " + ln)

    print()
    if dx1 < 0:
        print("charred: (none found)")
        return 1
    print("charred bbox x %d..%d y %d..%d  (%dx%d)"
          % (dx0, dx1, dy0, dy1, dx1 - dx0 + 1, dy1 - dy0 + 1))
    print("  rel to content: x %.3f..%.3f   y %.3f..%.3f"
          % ((dx0 - x0) / float(cw), (dx1 - x0) / float(cw),
             (dy0 - y0) / float(chh), (dy1 - y0) / float(chh)))
    print("  charred top is %.1fpx below content top (%.3f of content h)"
          % (dy0 - y0, (dy0 - y0) / float(chh)))
    print("  content top in dial units: content spans %.3f..%.3f of dial height"
          % (((y0 - h / 2.0) / float(h)), ((y1 - h / 2.0) / float(h))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
