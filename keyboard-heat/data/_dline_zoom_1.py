# -*- coding: utf-8 -*-
"""把「当天竖线 + 菱形」那块放大出来目视：线宽 / 鼠标段位置 / 菱形是不是真正的菱形。

用法：
  python _dline_zoom_1.py                        # 默认裁 hrline_after_1280_1x.png 的右下活跃区
  python _dline_zoom_1.py 图.png 330 190 470 350 4
                                  x0  y0  x1  y1 倍率
用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。"""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    if '--help' in argv or '-h' in argv:
        print(__doc__)
        return 0
    src = os.path.join(HERE, argv[0] if argv else 'hrline_after_1280_1x.png')
    nums = [int(v) for v in argv[1:6]] if len(argv) > 1 else [330, 190, 470, 350, 4]
    x0, y0, x1, y1, k = nums
    out = os.path.join(HERE, '_dline_zoom.png')

    im = Image.open(src).convert('RGB')
    crop = im.crop((x0, y0, x1, y1))
    big = crop.resize((crop.width * k, crop.height * k), Image.NEAREST)
    # 每 10 源像素画一条细网格，方便数"线到底几像素宽"
    d = ImageDraw.Draw(big)
    for gx in range(0, crop.width + 1, 10):
        d.line([(gx * k, 0), (gx * k, big.height)], fill=(180, 200, 220), width=1)
    for gy in range(0, crop.height + 1, 10):
        d.line([(0, gy * k), (big.width, gy * k)], fill=(180, 200, 220), width=1)

    big.save(out)
    print('saved %s  crop=(%d,%d,%d,%d) x%d -> %s' % (out, x0, y0, x1, y1, k, big.size))

    # 顺带把这块的列剖面打出来：每列的非背景像素数（背景 = 卡片白 #fff）
    px = im.load()
    cols = []
    for x in range(x0, x1):
        n = 0
        for y in range(y0, y1):
            r, g, b = px[x, y]
            if not (r > 248 and g > 248 and b > 248):
                n += 1
        cols.append((x, n))
    busy = [c for c in cols if c[1] > 3]
    print('非背景像素 > 3 的列：')
    for x, n in busy:
        print('   x=%4d  n=%3d' % (x, n))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
