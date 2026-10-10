# -*- coding: utf-8 -*-
"""总览「输入构成」与键盘/鼠标列的相对位置 改前/改后 对照图（桌面 1280 档）。
改前 = comp 靠左，只贴着键盘列，鼠标列被键盘列隔开（离它最远）；
改后 = comp 夹在键盘列与鼠标列之间，左邻键盘(蓝)、右邻鼠标(橙)，
       且砖内双环图「左⌨右🖱」与砖外色带方位一致。
用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))


def load(p):
    return Image.open(os.path.join(HERE, p)).convert('RGB')


before = load('preflank_1280_1x.png')   # 改前：comp 靠左
after = load('flank_1280_1x.png')       # 改后：comp 夹心

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
y = cap(y, '改前｜「输入构成」靠左 —— 只贴着键盘列，鼠标列被键盘列隔开，离它最远',
         (110, 101, 91))
canvas.paste(before, (pad, y))
y += before.height + gap
y = cap(y, '改后｜「输入构成」夹在键盘列与鼠标列之间 —— 左邻键盘(蓝)、右邻鼠标(橙)，与砖内双环图方位一致',
         (232, 89, 12))
canvas.paste(after, (pad, y))

out = os.path.join(HERE, '_tiles_flank_ab.png')
canvas.save(out)
print('saved', out, canvas.size)
