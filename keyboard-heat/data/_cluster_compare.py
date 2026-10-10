# -*- coding: utf-8 -*-
"""总览「铺砖」聚类 改前/改后 对照图（桌面 1280 档）。
改前 = 砖块散排（同类不相邻，颜色不成带）；
改后 = 按类别聚成三竖列色带（键盘列 / 鼠标列 / 时间列）。
用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))


def load(p):
    return Image.open(os.path.join(HERE, p)).convert('RGB')


before = load('scatter_1280_1x.png')   # 改前：散排
after = load('tiles_1280_1x.png')      # 改后：聚类

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
y = cap(y, '改前｜砖块「散排」—— 键盘/鼠标/时间混杂，鼠标三块被键盘块插队、散在两行，颜色不成带',
         (110, 101, 91))
canvas.paste(before, (pad, y))
y += before.height + gap
y = cap(y, '改后｜同类「聚类」成三竖列色带 —— 键盘列(蓝) / 鼠标列(橙) / 时间列(绿)，键盘列紧贴鼠标列呼应主砖配对',
         (232, 89, 12))
canvas.paste(after, (pad, y))

out = os.path.join(HERE, '_tiles_cluster_ab.png')
canvas.save(out)
print('saved', out, canvas.size)
