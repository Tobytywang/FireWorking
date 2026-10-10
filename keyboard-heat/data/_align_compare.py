# -*- coding: utf-8 -*-
"""总览「文字位置统一 + 主砖顶色条」改前/改后 对照图（桌面 1280 档）。

改前 = row_1280_1x.png —— 主砖文字垂直居中、顶色条 --tc:transparent（缺失）；
                        时间行用 space-between：标签贴左、数值贴右，中间留一条空洞，数值右对齐。
改后 = v4_1280_1x.png  —— 主砖标题左上 / 脚注左下（与其它砖同一套位置），
                        顶色条「键盘蓝 → 鼠标橙」撞色渐变；
                        时间行左列沿用同一套位置（标签左上 / 数值左下），右列放次要信息填掉空白。

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


before, after = load('row_1280_1x.png'), load('v4_1280_1x.png')

# 1) 整块对照
stack([
    ('改前｜主砖文字垂直居中、顶色条缺失；时间行 space-between（标签贴左/数值贴右，中间留出空洞）',
     before, GRAY),
    ('改后｜主砖标题左上 / 脚注左下 + 顶色条「键盘蓝→鼠标橙」撞色；时间行标签左上/数值左下，右列补次要信息',
     after, ORANGE),
], os.path.join(HERE, '_tiles_align_ab.png'))

# 2) 细节放大（主砖 2×、时间行 2×）
BOX_COMP = (530, 36, 1053, 232)
BOX_TIME = (0, 236, 1053, 330)
stack([
    ('改前｜主砖：文字垂直居中、顶色条为空（放大 2×）', crop(before, BOX_COMP), GRAY),
    ('改后｜主砖：标题左上 / 脚注左下；顶色条「键盘蓝→鼠标橙」撞色（放大 2×）', crop(after, BOX_COMP), ORANGE),
    ('改前｜时间行：标签贴左、数值贴右，中缝留白且数值右对齐（放大 2×）', crop(before, BOX_TIME), GRAY),
    ('改后｜时间行：标签左上 / 数值左下（与上面 6 块同位置），右列补次要信息（放大 2×）', crop(after, BOX_TIME), ORANGE),
], os.path.join(HERE, '_tiles_align_zoom.png'))
