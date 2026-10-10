# -*- coding: utf-8 -*-
"""卡片头条（标题色 + 与右上角标顶边对齐）改前/改后 对照图。

改前 = 注入 `_pre_label.css` 复现：
        标题 --fg3（白底对比度 2.83:1，低于 AA 4.5:1，且与右列注释同色同重）；
        角标硬编码 top:11px，而标题墨迹顶边由 padding-top 推出 → 两者错行（hero 4px / 其余 2px）。
改后 = 现状：
        标题 --fg2（白底 5.69:1 / 暗色 7.54:1）；
        角标 top:var(--padT)，与标题**由同一个数推出** → 全部卡片墨迹顶边同为 13px（dTop = 0）。

用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BG = (246, 244, 241)
GRAY = (110, 101, 91)
ORANGE = (232, 89, 12)


def load(p):
    return Image.open(os.path.join(HERE, p)).convert('RGB')


def font(sz):
    for p in ('C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def stack(panels, out, width=None, pad=20, gap=18, lab=38, fs=21):
    W = width or max(im.width for _, im, _ in panels)
    H = pad + sum(lab + im.height + gap for _, im, _ in panels) - gap + pad
    cv = Image.new('RGB', (W + pad * 2, H), BG)
    d = ImageDraw.Draw(cv)
    f = font(fs)
    y = pad
    for cap, im, col in panels:
        d.text((pad, y), cap, font=f, fill=col)
        y += lab
        cv.paste(im, (pad, y))
        y += im.height + gap
    cv.save(out)
    print('saved', out, cv.size)


def crop(im, box, s=2):
    x0, y0, x1, y1 = box
    box = (max(0, x0), max(0, y0), min(im.width, x1), min(im.height, y1))
    c = im.crop(box)
    return c.resize((c.width * s, c.height * s), Image.LANCZOS)


# 顶色条只可能是三族主题色 → 从像素里扫出「卡片头条」的位置，别写死坐标
# （视口/截图尺寸会差几 px，写死的裁剪框早晚偏）。
FAMILY = [(47, 111, 176), (232, 89, 12), (47, 158, 68)]   # 键盘蓝 / 鼠标橙 / 时间绿


def bar_row(im, tol=40):
    """返回 (y, [(x0,x1), …]) —— 顶色条所在行与每张卡的横向区间。"""
    def near(p):
        return any(all(abs(p[i] - c[i]) <= tol for i in range(3)) for c in FAMILY)
    for y in range(im.height):
        xs = [x for x in range(im.width) if near(im.getpixel((x, y)))]
        if len(xs) > im.width * 0.5:
            runs, s, prev = [], xs[0], xs[0]
            for x in xs[1:]:
                if x - prev > 4:
                    runs.append((s, prev))
                    s = x
                prev = x
            runs.append((s, prev))
            if len(runs) >= 3:
                return y, runs
    return None, []


def header(im, idx):
    """第 idx 张卡的「头条」裁剪框：从它自己的顶色条推出来（顶色条就在卡顶）。"""
    y, runs = bar_row(im)
    if y is None or idx >= len(runs):
        return (0, 0, min(im.width, 360), 40)
    x0, x1 = runs[idx]
    return (x0 - 2, y - 2, x1 + 2, y + 35)


# —— 图 1：hero 三卡（用户圈的就是第 3 张「鼠标占比」）+ 头条 3× 放大 ——
hb, ha = load('lbl_hero_before_1280_1x.png'), load('lbl_hero_after_1280_1x.png')
Z = 3
BOX_C1 = header(ha, 0)            # 第 1 张卡头条（从顶色条扫出来）
BOX_C3 = header(ha, 2)            # 第 3 张卡「鼠标占比」（被圈的那张）
print('hero 头条框:', BOX_C1, BOX_C3)
stack([
    ('改前｜标题 --fg3（白底 2.83:1，太浅）；标题顶边比角标低 4px', hb, GRAY),
    ('改后｜标题 --fg2（白底 5.69:1）；标题与角标顶边同线（dTop 0px）', ha, ORANGE),
    ('改前｜第 1 张卡头条（放大 3×）：标题比右侧「键盘」低 4px、且更浅', crop(hb, BOX_C1, Z), GRAY),
    ('改后｜第 1 张卡头条（放大 3×）：标题与「键盘」同一条顶边', crop(ha, BOX_C1, Z), ORANGE),
    ('改前｜第 3 张卡「鼠标占比」（放大 3×）：标题比右侧「鼠标」低 4px、且更浅', crop(hb, BOX_C3, Z), GRAY),
    ('改后｜第 3 张卡「鼠标占比」（放大 3×）：标题与「鼠标」同一条顶边', crop(ha, BOX_C3, Z), ORANGE),
], os.path.join(HERE, '_tilelabel_ab.png'))

# —— 图 2：另两组同类卡片（同一套契约，一起改） ——
sb, sa = load('lbl_stats_before_1280_1x.png'), load('lbl_stats_after_1280_1x.png')
cb, ca = load('lbl_cd_before_1280_1x.png'), load('lbl_cd_after_1280_1x.png')
BOX_S1 = header(sa, 0)            # 总览首砖头条（同样从顶色条扫出来）
print('总览头条框:', BOX_S1)
stack([
    ('改前｜总览铺砖：标题 --fg3 + 标题比角标低 2px', sb, GRAY),
    ('改后｜总览铺砖（同一套契约）', sa, ORANGE),
    ('改前｜总览首砖头条（放大 3×）', crop(sb, BOX_S1, Z), GRAY),
    ('改后｜总览首砖头条（放大 3×）', crop(sa, BOX_S1, Z), ORANGE),
    ('改前｜倒计时四卡：标题 --fg3 + 标题比角标低 2px', cb, GRAY),
    ('改后｜倒计时四卡（同一套契约）', ca, ORANGE),
], os.path.join(HERE, '_tilelabel_groups.png'))
