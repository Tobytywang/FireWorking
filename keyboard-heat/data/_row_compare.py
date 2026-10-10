# -*- coding: utf-8 -*-
"""总览「输入构成」分组方向 改前/改后 对照图（桌面 1280 档）。
改前 = 按「列」分组（键盘列 | 占比 | 鼠标列），占比夹在两列之间；
改后 = 按「行」分组（键盘行 / 鼠标行 / 时间行），占比横跨键盘行与鼠标行、置于行末。
用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))


def load(p):
    return Image.open(os.path.join(HERE, p)).convert('RGB')


before = load('flank_1280_1x.png')   # 改前：列式
after = load('row_1280_1x.png')      # 改后：行式

W = max(before.width, after.width)
pad, gap, lab = 20, 16, 34
canvas_w = W + pad * 2
H = pad + lab + before.height + gap + lab + after.height + pad
canvas = Image.new('RGB', (canvas_w, H), (246, 244, 241))
d = ImageDraw.Draw(canvas)
try:
    f = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 21)
except Exception:
    f = ImageFont.load_default()


def cap(y, text, color):
    d.text((pad, y), text, font=f, fill=color)
    return y + lab


y = pad
y = cap(y, '改前｜按「列」分组 —— 键盘列 | 占比 | 鼠标列（占比夹在两列之间的旧做法）',
         (110, 101, 91))
canvas.paste(before, (pad, y))
y += before.height + gap
y = cap(y, '改后｜按「行」分组 —— 键盘行 / 鼠标行 / 时间行；占比横跨键盘行与鼠标行、置于行末',
         (232, 89, 12))
canvas.paste(after, (pad, y))

out = os.path.join(HERE, '_tiles_row_ab.png')
canvas.save(out)
print('saved', out, canvas.size)
