# -*- coding: utf-8 -*-
"""键鼠活动记录卡片：改前（两块同属一张卡、中间一条细线）/ 改后（两块各自成卡）对照图。

改前 = 注入 `_pre_merged.js` 复现：一张 .panel 里平铺两块，中间只有一条 `.view-pane + .view-pane`
       的内部分隔线；没有卡片标题行。
改后 = 现状：两张独立 .panel，各有边框与圆角、卡间 14px，每张卡自带 `.row` 标题行
       （标题左 / 注释右）—— 与「倒计时功能的统计」那节的卡片形式一致。

图内坐标全部**从像素里扫**，不写死：
  · 卡片边界 = `--line` 横线（实测叠在白卡上 ≈ (229,228,227)）。改前应恰好扫到 3 条
    （卡上边框 / 内部分隔线 / 卡下边框），改后应恰好扫到 4 条（两卡各上下边框）；
    条数对不上直接报错 —— 宁可吵，也不要静默画错位置。
用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BG = (246, 244, 241)
GRAY = (110, 101, 91)
INK = (40, 34, 30)
RED = (200, 60, 60)
GREEN = (47, 158, 68)
# `--line: rgba(40,33,26,.12)` 叠在白卡上 → 实测 (229,228,227)
LINE_RGB = (229, 228, 227)


def load(p):
    return Image.open(os.path.join(HERE, p)).convert('RGB')


def font(sz):
    for p in ('C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def find_hlines(im, expect, minrun=800):
    """`--line` 横线：返回 [(y, xstart, runlen)]，条数必须等于 expect。"""
    px = im.load()
    W, H = im.size
    out = []
    for y in range(H):
        run, start, best = 1, 0, (0, 0)
        for x in range(1, W):
            if px[x, y] == px[x - 1, y]:
                run += 1
                if run > best[0]:
                    best = (run, start)
            else:
                run, start = 1, x
        c = px[best[1] + 1, y] if best[0] >= minrun else None
        if c and all(abs(c[i] - LINE_RGB[i]) <= 2 for i in range(3)):
            out.append((y, best[1], best[0]))
    if len(out) != expect:
        raise SystemExit('!! 扫描到 %d 条 --line 横线，预期 %d 条：%s' % (len(out), expect, out))
    return out


def find_headrow(im, top, bot):
    """扫卡片顶部那行标题的**墨迹带**：返回 (y0, y1)。
    取"自上而下**第一个**连续墨迹带"—— 标题行必然紧贴卡片顶部（padding 之后），
    再往下就是日历格子（橙色格子的 r+g+b 只有 333，比标题还深，会被误当成标题
    —— 第一版整卡扫，实测卡1 拿到 (77,256)，把日历也算进去了）。
    判据：某行"暗像素"（r+g+b < 560，卡底色 743 / 边框线 684 都不算）≥8 个。"""
    px = im.load()
    W, H = im.size
    bands = []
    cur = None
    for y in range(max(0, top + 2), min(H, bot - 1)):
        dark = 0
        for x in range(0, W, 2):
            r, g, b = px[x, y]
            if r + g + b < 560:
                dark += 1
        if dark >= 8:
            if cur is None:
                cur = y
        elif cur is not None:
            bands.append((cur, y - 1))
            cur = None
    if cur is not None:
        bands.append((cur, min(H, bot - 1) - 1))
    return bands[0] if bands else None


pre = load('sp_pre_1280_1x.png')   # 改前（两块同属一张卡）
aft = load('sp_af_1280_1x.png')    # 改后（两块各自成卡）

hl_pre = find_hlines(pre, 3)       # 卡上 / 内部分隔线 / 卡下
hl_aft = find_hlines(aft, 4)       # 卡1上 / 卡1下 / 卡2上 / 卡2下

pre_div, pre_x0, pre_w = hl_pre[1]
aft_gap = (hl_aft[1][0], hl_aft[2][0])          # 两卡之间的空隙（卡1下边 → 卡2上边）
print('改前 --line 三条 y=%s | 内部分隔线 y=%d x=%d..%d'
      % ([h[0] for h in hl_pre], pre_div, pre_x0, pre_x0 + pre_w))
print('改后 --line 四条 y=%s | 卡间隙 y=%d→%d（%dpx）'
      % ([h[0] for h in hl_aft], aft_gap[0], aft_gap[1], aft_gap[1] - aft_gap[0] - 1))
print('同宽下高度：改前 %d → 改后 %d（+%dpx）' % (pre.height, aft.height, aft.height - pre.height))

PAD, LAB, ROWGAP, GUT = 26, 30, 26, 320
W = PAD * 2 + max(pre.width, aft.width) + GUT
H = PAD + LAB + pre.height + ROWGAP + LAB + aft.height + PAD
cv = Image.new('RGB', (W, H), BG)
d = ImageDraw.Draw(cv)
f_cap, f_lab, f_sm = font(17), font(13), font(12)

d.text((PAD, 8), '键鼠活动记录：两块由「同属一张卡」拆成「两张独立卡」（参照倒计时那节的卡片形式）',
       font=font(19), fill=INK)

x0 = PAD
gx = PAD + max(pre.width, aft.width) + 16

# ── 改前 ──
y = PAD + LAB
d.text((x0, y - LAB + 6),
       '改前｜两块同属一张卡：只有一层外框 + 一条内部分隔线，两块都没有自己的名字',
       font=f_cap, fill=GRAY)
cv.paste(pre, (x0, y))
d.rectangle([x0 + pre_x0 - 1, y + hl_pre[0][0] - 1,
             x0 + pre_x0 + pre_w, y + hl_pre[2][0] + 1], outline=RED, width=2)
d.line([(x0 + pre_x0, y + pre_div), (x0 + pre_x0 + pre_w, y + pre_div)], fill=RED, width=2)
def notes(items, color, top, lh=20):
    """右侧标注：按**不重叠**的槽位排（每条先跳到它的目标 y，若已被上一条占用则顺延）。
    直接 `d.text(目标y)` 会在目标挨得近时互相盖住 —— 第一版 ②③④ 就叠成一团。"""
    cur = top
    for target, rows in items:
        cur = max(cur, target)
        for txt, fnt in rows:
            d.text((gx, cur), txt, font=fnt, fill=color)
            cur += lh
        cur += 10


notes([
    (y + hl_pre[0][0] - 6, [('① 一张卡（.panel）', f_lab),
                            ('   内容左缘由卡片 padding 决定', f_sm)]),
    (y + pre_div - 6, [('② 两块之间只有一条内线', f_lab),
                       ('   读者要靠内容自己猜"这是两块"', f_sm)]),
    (y + hl_pre[2][0] - 18, [('③ 两块都没有自己的名字', f_lab),
                             ('   卡片标题行的位置是空的', f_sm)]),
], RED, y + 2)

# ── 改后 ──
y = PAD + LAB + pre.height + ROWGAP + LAB
d.text((x0, y - LAB + 6),
       '改后｜两块各自成卡：各有边框与圆角、卡间 14px，每卡自带标题行（标题左 / 注释右）',
       font=f_cap, fill=INK)
cv.paste(aft, (x0, y))

card1 = (hl_aft[0], hl_aft[1])
card2 = (hl_aft[2], hl_aft[3])
for (t, b) in (card1, card2):
    d.rectangle([x0 + hl_aft[0][1] - 1, y + t[0] - 1,
                 x0 + hl_aft[0][1] + hl_aft[0][2], y + b[0] + 1], outline=GREEN, width=2)
# 卡间隙：两条绿线之间的空档用一条竖直双向标尺标出来
xc = x0 + hl_aft[0][1] - 10
d.line([(xc, y + aft_gap[0]), (xc, y + aft_gap[1])], fill=GREEN, width=2)
d.line([(xc - 4, y + aft_gap[0]), (xc + 4, y + aft_gap[0])], fill=GREEN, width=2)
d.line([(xc - 4, y + aft_gap[1]), (xc + 4, y + aft_gap[1])], fill=GREEN, width=2)

h1 = find_headrow(aft, card1[0][0], card1[1][0])
h2 = find_headrow(aft, card2[0][0], card2[1][0])
print('改后卡1 标题墨迹带 y=%s | 卡2 y=%s' % (h1, h2))

notes([
    (y + card1[0][0] - 6, [('① 卡片 1：全年活动热力', f_lab),
                           ('   自带边框 + 圆角，与倒计时卡片同族', f_sm)]),
    (y + (h1[0] - 6 if h1 else card1[0][0] + 26),
     [('② 卡片标题行 .row（卡上边 +%dpx）' % (h1[0] - card1[0][0] if h1 else 0), f_lab),
      ('   标题左、注释右（margin-left:auto）', f_sm)]),
    (y + aft_gap[0] - 4, [('③ 卡间 %dpx（.panel + .panel）' % (aft_gap[1] - aft_gap[0] - 1), f_lab)]),
    (y + card2[0][0] - 6, [('④ 卡片 2：当天逐小时分布', f_lab),
                           ('   同样是"标题行 + 内容"的同一套卡语', f_sm)]),
    (y + card2[1][0] - 34, [('⑤ 两块各自独立，可单独引用 / 搬运', f_lab),
                            ('   ⚠ 代价：同宽下高 +%dpx（两行标题 + 卡间距）'
                             % (aft.height - pre.height), f_sm)]),
], GREEN, y + 2)

for band in (h1, h2):
    if band:
        d.line([(x0 + 2, y + band[0]), (x0 + hl_aft[0][1] - 3, y + band[0])], fill=GREEN, width=1)
        d.line([(x0 + 2, y + band[1]), (x0 + hl_aft[0][1] - 3, y + band[1])], fill=GREEN, width=1)

out = os.path.join(HERE, '_split_cards_ab.png')
cv.save(out)
print('saved', out, cv.size)
