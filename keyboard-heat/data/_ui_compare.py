# -*- coding: utf-8 -*-
"""把改前/改后两张截图裁到同一张卡片，上下拼接并标注左右留白实测值。

关键 x 坐标来自 `_ui_geom_probe.py`（vw=1128）：容器内容区 [58, 1070]；
改前内容 [59, 1005]（左 1 / 右 65），改后 [91, 1037]（左 33 / 右 33）。
"""
from PIL import Image, ImageDraw, ImageFont

CROP = (20, 296, 1120, 540)          # 「每日使用次数」卡片
BOX = (58, 1070)                     # 卡片内容区左右边缘（padding 内）
CASES = [
    ('_ui_before_1144.png', '改前', (59, 1005), (1, 65),  (192, 57, 43)),
    ('_ui_fixed_1144.png',  '改后', (91, 1037), (33, 33), (22, 130, 93)),
]
OUT = '_ui_compare.png'

f = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 16)
fb = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 18)

ox, oy = CROP[0], CROP[1]
strips = []
for path, tag, content, stat, col in CASES:
    im = Image.open(path).convert('RGB').crop(CROP)
    d = ImageDraw.Draw(im)
    W, H = im.size
    # 卡片内容区边界（灰）
    for x in BOX:
        d.line([(x - ox, 30), (x - ox, H)], fill=(170, 170, 170), width=1)
    # 内容左右边缘（彩色）
    for x in content:
        d.line([(x - ox, 30), (x - ox, H)], fill=col, width=2)
    # 留白段：在卡片顶部用横线把「留白宽度」视觉化
    y = 16
    d.line([(BOX[0] - ox, y), (content[0] - ox, y)], fill=col, width=3)
    d.line([(content[1] - ox, y), (BOX[1] - ox, y)], fill=col, width=3)
    d.text((content[0] - ox + 6, 34), 'L=%d' % stat[0], font=fb, fill=col)
    tw = d.textlength('R=%d' % stat[1], font=fb)
    d.text((content[1] - ox - tw - 6, 34), 'R=%d' % stat[1], font=fb, fill=col)
    strips.append((im, tag, stat, col))

W = strips[0][0].width
BAR = 30
H = sum(s[0].height for s in strips) + BAR * len(strips)      # 每张条都有一段标题带
canvas = Image.new('RGB', (W, H), (255, 255, 255))
y = 0
for im, tag, stat, col in strips:
    canvas.paste(im, (0, y + BAR))
    d = ImageDraw.Draw(canvas)
    d.text((6, y + 4), '%s   左留白 %d px / 右留白 %d px   不对称 %d px'
           % (tag, stat[0], stat[1], abs(stat[1] - stat[0])), font=f, fill=col)
    y += BAR + im.height
canvas.save(OUT)
print('written', OUT, canvas.size)
