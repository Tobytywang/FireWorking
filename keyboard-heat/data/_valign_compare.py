# -*- coding: utf-8 -*-
"""大号数字在卡内的纵向位置：改前 / 改后 对照图。

改前 = 注入 `_pre_valign.css` 复现：三组卡片卡高来路不同（hero 80 / 总览 88 / 倒计时 69）、
       下内边距不同（19 / 15）、数值行盒随字号走（27/23/21px × line-height:1.05），
       且单位 <small> 继承行高把「带单位」的卡再撑高 → 数字顶边 31 / 48 / 31，极差 17px。
改后 = 现状：卡高统一 88（min-height，窄屏 92）、下内边距统一 15、数值行盒钉死 34px、
       单位行高收到 1 → 17 张卡的数字顶边全部 38px（极差 0）。

图内坐标 = 卡片相对坐标（截图用 `--pad 0`），所以参考线直接画在 y = VTOP 处。
用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BG = (246, 244, 241)
GRAY = (110, 101, 91)
ORANGE = (232, 89, 12)
GREEN = (47, 158, 68)

# 探针 `_label_align_probe.py` 实测的「数值行盒顶边 − 卡顶」（px）
VTOP_AFTER = 38
VTOP_BEFORE = (31, 48)      # (hero 卡, 总览滚轮卡)


def load(p):
    return Image.open(os.path.join(HERE, p)).convert('RGB')


def font(sz):
    for p in ('C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


hero_pre = load('vc_hero_pre_1280_1x.png')    # 321x80  改前 hero 第 3 卡「鼠标占比」
roll_pre = load('vc_roll_pre_1280_1x.png')    # 165x88  改前 总览「鼠标滚轮」
hero_aft = load('vc_hero_1280_1x.png')        # 321x88
roll_aft = load('vc_roll_1280_1x.png')        # 165x88

PAD, LAB, COLGAP, ROWGAP, ROWH = 26, 34, 24, 30, 92
rowW = max(hero_aft.width, hero_pre.width) + COLGAP + roll_aft.width
W = PAD * 2 + rowW + 250
H = PAD + (LAB + ROWH + ROWGAP) * 2 - ROWGAP + PAD
cv = Image.new('RGB', (W, H), BG)
d = ImageDraw.Draw(cv)
f_cap = font(17)
f_lab = font(14)
f_sm = font(13)

d.text((PAD, 8), '大号数字在卡内的纵向位置（两张卡按「卡顶对齐」并排）', font=font(19), fill=(40, 34, 30))

rows = [
    ('改前｜hero 卡 80px（数字顶边 31）与总览滚轮卡 88px（数字顶边 48）→ 差 17px',
     hero_pre, roll_pre, GRAY),
    ('改后｜两张卡都 88px、数字顶边都是 38px → 差 0px（同一条线）',
     hero_aft, roll_aft, ORANGE),
]

y = PAD + 34
for cap, hl, rl, col in rows:
    d.text((PAD, y), cap, font=f_cap, fill=col)
    y += LAB
    cv.paste(hl, (PAD, y))
    cv.paste(rl, (PAD + hl.width + COLGAP, y))
    if col == GRAY:
        # 改前：两张卡各自的实际数字顶边（红实线，一高一低）
        for xx, vt, wd in ((PAD, VTOP_BEFORE[0], hl.width),
                           (PAD + hl.width + COLGAP, VTOP_BEFORE[1], rl.width)):
            d.line([(xx, y + vt), (xx + wd, y + vt)], fill=(200, 60, 60), width=2)
        d.text((PAD + rowW + 10, y + VTOP_BEFORE[0] - 9), '各自顶边 31', font=f_lab, fill=(200, 60, 60))
        d.text((PAD + rowW + 10, y + VTOP_BEFORE[1] - 9), '各自顶边 48（差 17px）', font=f_lab, fill=(200, 60, 60))
    else:
        # 改后：贯穿两卡的统一基准线（绿点线）
        ly = y + VTOP_AFTER
        for x in range(PAD, PAD + rowW, 9):
            d.line([(x, ly), (x + 5, ly)], fill=GREEN, width=1)
        d.text((PAD + rowW + 10, ly - 9), '统一顶边 38px（差 0）', font=f_lab, fill=GREEN)
    y += ROWH + ROWGAP

out = os.path.join(HERE, '_tiles_valign_ab.png')
cv.save(out)
print('saved', out, cv.size)
