# -*- coding: utf-8 -*-
"""活动日历「图例右缘 vs 日历内容右缘」改前/改后对照图。

坐标全部由 PIL 从像素里扫出来，**不做 CSS→设备像素换算** —— 实测截图里卡片
位置比 CSS 预测整体偏移约 7 CSS px（`.wrap` 居中量随视口宽变），换算会把标线画歪。

扫描结论（dsf=1.5，窗口 1144 → 图像 1716 × 900）：
  卡片外缘 x 68..1647
  日历内容右缘（y=173 行）       → 1567
  图例墨迹右缘（y=322 行）       → 改前 1615 / 改后 1566
  ⇒ 改前偏右 48 设备 px = 32 CSS px；改后偏差 1 设备 px（抗锯齿）。
"""
from PIL import Image, ImageDraw, ImageFont

CROP = (20, 0, 1660, 372)
CAL_R = 1567                      # 日历内容右缘
CASES = [
    ('_lg_before_1144.png', '改前', 1615, (192, 57, 43)),
    ('_lg_after_1144.png',  '改后', 1566, (22, 130, 93)),
]
OUT = '_legend_compare.png'
BAR = 34

f = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 14)
fb = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 16)

ox, oy = CROP[0], CROP[1]
strips = []
for path, tag, lg_r, col in CASES:
    im = Image.open(path).convert('RGB').crop(CROP)
    d = ImageDraw.Draw(im)
    W, H = im.size
    x_cal, x_lg = CAL_R - ox, lg_r - ox
    gap = lg_r - CAL_R

    def dash(x, c, w=2, y0=56, y1=None):
        y1 = y1 or H - 4
        for y in range(y0, y1, 10):
            d.line([(x, y), (x, min(y + 5, y1))], fill=c, width=w)

    dash(x_cal, (105, 105, 105))                    # 日历内容右缘
    dash(x_lg, col, w=3, y0=34)                     # 图例墨迹右缘
    if abs(gap) > 4:                                # 有偏差才画间隔标注
        d.line([(x_cal, 46), (x_lg, 46)], fill=col, width=2)
        for x in (x_cal, x_lg):
            d.line([(x, 41), (x, 51)], fill=col, width=2)
        d.text(((x_cal + x_lg) / 2 - 20, 62), '%dpx' % gap, font=fb, fill=col)

    # 两个标签都靠线的左侧，但**错开 y** —— 水平位置几乎重合时也不会叠字
    t1 = '图例右缘 %d' % lg_r
    d.text((x_lg - 6 - d.textlength(t1, font=f), 2), t1, font=f, fill=col)
    t2 = '日历内容右缘 %d' % CAL_R
    d.text((x_cal - 6 - d.textlength(t2, font=f), 22), t2, font=f, fill=(105, 105, 105))
    strips.append((im, tag, lg_r, col))

W = strips[0][0].width
canvas = Image.new('RGB', (W, len(strips) * (BAR + strips[0][0].height)), (255, 255, 255))
y = 0
for im, tag, lg_r, col in strips:
    canvas.paste(im, (0, y + BAR))
    d = ImageDraw.Draw(canvas)
    gap = lg_r - CAL_R
    d.text((6, y + 8),
           '%s　图例右缘 %d vs 日历内容右缘 %d　→　偏差 %+d 设备px（%+.1f CSSpx）'
           % (tag, lg_r, CAL_R, gap, gap / 1.5), font=fb, fill=col)
    y += BAR + im.height
canvas.save(OUT)
print('written', OUT, canvas.size)
