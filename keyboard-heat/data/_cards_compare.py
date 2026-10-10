# -*- coding: utf-8 -*-
"""hero 三卡 / 倒计时四卡 套用「总览砖块」契约 的 改前/改后 对照图（桌面 1280 档）。

改前 = *_before_1280_1x.png —— hero 用 .hero-stat、倒计时用 .stat：无顶色条、无角标，
       标签与数值相邻（数值不在卡底），321px/254px 宽的卡右侧分别空 208px / 152px。
改后 = *_after_1280_1x.png  —— 两组都改用与总览砖块同一套 `.tile`：
       顶色条（hero 各族色 蓝/绿/橙、倒计时族色 紫）+ 右上角标 + 标签左上 / 数值左下，
       右列放一条同源推导的次要信息填掉宽度（日均/当量、来源种类/范围/峰值/占比）。

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


def stack(panels, out, width=None, pad=20, gap=18, lab=36, fs=21):
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


def zoom(im, y0, y1, s=2):
    c = im.crop((0, max(0, y0), im.width, min(im.height, y1)))
    return c.resize((c.width * s, c.height * s), Image.LANCZOS)


def bottom(im, h):
    return zoom(im, im.height - h, im.height)


hb, ha = load('hero_before_1280_1x.png'), load('hero_after_1280_1x.png')
stack([
    ('改前｜hero 三卡：无顶色条/角标，321px 宽的卡右侧空 208px（hFill 27%）', hb, GRAY),
    ('改后｜hero 三卡：族色顶色条（键盘蓝/时间绿/鼠标橙）+ 角标；右列补「日均/当量」（hFill 99%）', ha, ORANGE),
    ('改前｜hero 卡带放大 2×（标签与数值相邻、右侧整片白）', bottom(hb, 140), GRAY),
    ('改后｜hero 卡带放大 2×（标签左上 / 数值左下 / 右列次要信息）', bottom(ha, 140), ORANGE),
], os.path.join(HERE, '_cards_hero_ab.png'))

cb, ca = load('cd_before_1280_1x.png'), load('cd_after_1280_1x.png')
stack([
    ('改前｜倒计时四卡（.stat）：无顶色条/角标，254px 宽的卡右侧空 152px（hFill 31%）', cb, GRAY),
    ('改后｜倒计时四卡（.tile）：族色顶色条（倒计时·紫）+ 角标；右列补「来源种类/范围/峰值/占比」（hFill 99%）', ca, ORANGE),
    ('改前｜倒计时卡带放大 2×', zoom(cb, 30, 140), GRAY),
    ('改后｜倒计时卡带放大 2×', zoom(ca, 25, 135), ORANGE),
], os.path.join(HERE, '_cards_cd_ab.png'))
