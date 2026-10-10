# -*- coding: utf-8 -*-
"""把「改前 / 改后」的 hover 渲染（探针 _hover_cdp.mjs 的 3 倍放大截图）并排拼成对照图。

数据来源：`_hb_*.png`（--css 注入旧规则复现改前）/ `_ha_*.png`（当前产物）。
"""
from PIL import Image, ImageDraw, ImageFont

ROWS = [
    ('_hb_1.png', '_ha_1.png', '活动日历 · 跨月占位格', '不属于该月的日期'),
    ('_hb_6.png', '_ha_6.png', '倒计时日历 · 无数据日', '有日期但当天 0 次'),
    ('_hb_4.png', '_ha_4.png', '周视图 · 无数据小时格', '当天该小时无记录'),
    ('_hb_3.png', '_ha_3.png', '活动日历 · 有数据的日期', '对照组：应保留橙框'),
]
OUT = '_hover_compare.png'
F = 'C:/Windows/Fonts/msyh.ttc'
f_lab = ImageFont.truetype(F, 15)
f_sub = ImageFont.truetype(F, 13)
f_tag = ImageFont.truetype(F, 15)
f_ttl = ImageFont.truetype(F, 19)

CW = CH = 210
LABW, PAD, GAP, TOPBAR = 270, 18, 14, 92
W = PAD + LABW + CW + GAP + CW + PAD
H = TOPBAR + len(ROWS) * (CH + 10) + PAD
cv = Image.new('RGB', (W, H), (255, 255, 255))
d = ImageDraw.Draw(cv)
d.text((PAD, 12), '鼠标悬停格子时的渲染（放大 3 倍）', font=f_ttl, fill=(33, 27, 21))
d.text((PAD, 42), '判据：只有「有数据」的格子才该出现橙色描边+放大；空占位/无数据格不该有任何反馈',
       font=f_sub, fill=(120, 110, 100))

x_b = PAD + LABW
x_a = x_b + CW + GAP
d.text((x_b + 4, TOPBAR - 22), '改前', font=f_tag, fill=(192, 57, 43))
d.text((x_a + 4, TOPBAR - 22), '改后', font=f_tag, fill=(22, 130, 93))

y = TOPBAR
for p1, p2, lab, sub in ROWS:
    d.text((PAD, y + CH / 2 - 22), lab, font=f_lab, fill=(33, 27, 21))
    d.text((PAD, y + CH / 2 + 2), sub, font=f_sub, fill=(120, 110, 100))
    for x, p in ((x_b, p1), (x_a, p2)):
        im = Image.open(p).convert('RGB')
        s = min(CW / im.width, CH / im.height)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
        cv.paste(im, (x + (CW - im.width) // 2, y + (CH - im.height) // 2))
        d.rectangle([x, y, x + CW, y + CH], outline=(228, 224, 218))
    y += CH + 10
cv.save(OUT)
print('written', OUT, cv.size)
