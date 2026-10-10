# -*- coding: utf-8 -*-
"""总览改版 改前/改后 对照图（桌面 1280 档）。
改前 = 三簇等高卡网格；改后 = 铺地砖式语义排布（主砖双环图 + 按主题着色自填）。
用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))


def load(p):
    return Image.open(os.path.join(HERE, p)).convert('RGB')


before = load('before_1280_1x.png')
after = load('after_1280_1x.png')

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
y = cap(y, '改前｜「键盘 / 鼠标 / 时间」三簇等高卡网格 —— 卡宽远大于内容，右半张全是空白', (110, 101, 91))
canvas.paste(before, (pad, y))
y += before.height + gap
y = cap(y, '改后｜铺地砖式语义排布 —— 主砖=键盘/鼠标双环占比，其余砖按主题着色（蓝键盘 / 橙鼠标 / 绿时间）自填', (232, 89, 12))
canvas.paste(after, (pad, y))

out = os.path.join(HERE, '_tiles_compare.png')
canvas.save(out)
print('saved', out, canvas.size)
