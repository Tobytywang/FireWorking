# -*- coding: utf-8 -*-
"""面板标题行「注释右对齐」改前/改后 对照图（桌面 1280 档）。

改前 = hrpre_1280_1x.png —— 注释紧跟标题（左对齐），短标题行右侧空掉
       632px / 522px（两条面板标题行均值 577px）。
改后 = hr_1280_1x.png   —— 注释贴本行右缘（= 卡片内容右缘、与下方图表内容右缘同线，
       实测 flushR = 0 ），右侧空白归零。

另附窄屏（620 / 390）看注释换行后的自然退化。

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


def band(im, y0, h):
    """取一块并 2× 放大：看注释与标题的左右关系。"""
    return zoom(im, y0, y0 + h)


hb = load('hrpre_1280_1x.png')
ha = load('hr_1280_1x.png')
n6 = load('hr_620_1x.png')
n3 = load('hr_390_1x.png')

stack([
    ('改前｜注释紧跟标题（左对齐）：右侧空 632px / 522px（两行均值 577px）', hb, GRAY),
    ('改后｜注释贴本行右缘 = 卡片内容右缘（与下方图表右缘同线，flushR=0），右空 0px', ha, ORANGE),
    ('改前｜放大 2×：注释紧贴标题，行右侧整片留白', band(hb, 140, 90), GRAY),
    ('改后｜放大 2×：标题在左、注释在右，同一行两端站稳', band(ha, 140, 90), ORANGE),
    ('窄屏 620｜注释仍在标题同行、贴右缘（未换行）', n6, GRAY),
    ('窄屏 390｜注释换行后落到标题下方、左对齐（自然退化，不成断头）', n3, ORANGE),
], os.path.join(HERE, '_headrow_ab.png'))
