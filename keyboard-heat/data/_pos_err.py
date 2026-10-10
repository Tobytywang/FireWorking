# -*- coding: utf-8 -*-
"""「位置到底差多少」—— 把残留图形的错位量成 CSS 像素

用法：../.pyenv/Scripts/python.exe _pos_err.py
产出：_pos_err.png

方法（可复用）：用户说"位置不对"时，别只说"越界了"，要给四个**框**和两组差值：
  ① 容器框（它本该在里面的那个：卡片格）
  ② 承载框（本该放它的槽位：文件图标那一格）
  ③ 实际可见框（抠像素量出来）
  ④ 被**硬切**的边落在哪 —— ⚠ 关键推论：如果硬切边**不在容器边上**，
     说明裁它的框**根本不是这个容器**（元素是相对另一个盒子定位的，典型"残留/错位"特征）。
设备像素 ÷ 2 = CSS 像素（该截图 DPR=2）。
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = r'C:\Users\toby.wang\.workbuddy\clipboard-images\clipboard-2026-09-29T14-38-55-981Z-9ebd452c.png'
CROP = (555, 40, 1080, 360)          # 展示区（设备像素）
CARD = (573, 207, 1058, 334)         # 卡片格
SLOT = (604, 247, 660, 296)          # 缩略位＝卡内文件图标所在处
STRY = (640, 114, 827, 305)          # 残留图形可见区
TEXT = (620, 138, 1080, 178)         # 被盖住的正文行

BG, PANEL, INK, GRAY, LINE = (245, 246, 248), (255, 255, 255), (31, 35, 40), (118, 126, 134), (222, 226, 230)
RED, GREEN, BLUE, ORANGE = (214, 60, 60), (32, 140, 84), (40, 110, 200), (200, 120, 20)
SC = 1.5
W, PAD, TITLE_H, FOOT_H = 1330, 26, 84, 104


def font(sz):
    for p in ('C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def main():
    cw, ch = CROP[2] - CROP[0], CROP[3] - CROP[1]
    iw, ih = int(cw * SC), int(ch * SC)
    H = PAD + TITLE_H + ih + FOOT_H + PAD
    cv = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(cv)
    f_t, f_s, f_b, f_n = font(21), font(14), font(15), font(13)

    shot = Image.open(SHOT).convert('RGB')
    view = shot.crop(CROP).resize((iw, ih), Image.LANCZOS)
    x0, y0 = PAD, PAD + TITLE_H
    cv.paste(view, (x0, y0))

    d.text((PAD, PAD), '位置到底差多少？—— 三只框 + 两条"切边不在容器边上"', font=f_t, fill=INK)
    d.text((PAD, PAD + 34),
           '绿虚线 = 卡片格｜蓝框 = 缩略位（文件图标处）｜橙框 = 残留图形可见区（避开你画的红框，免得撞色）'
           '｜灰虚线 = 被盖住的正文行（截图原坐标，CSS 像素 = 设备像素 ÷ 2）', font=f_s, fill=GRAY)

    def to(x, y):
        return (x0 + (x - CROP[0]) * SC, y0 + (y - CROP[1]) * SC)

    def box(r, col, dash=0, wd=2):
        a, b = to(r[0], r[1]), to(r[2], r[3])
        if not dash:
            d.rectangle([a[0], a[1], b[0], b[1]], outline=col, width=wd)
            return
        for x in range(int(a[0]), int(b[0]), dash * 2):
            d.line([(x, a[1]), (min(x + dash - 1, b[0]), a[1])], fill=col, width=wd)
            d.line([(x, b[1]), (min(x + dash - 1, b[0]), b[1])], fill=col, width=wd)
        for y in range(int(a[1]), int(b[1]), dash * 2):
            d.line([(a[0], y), (a[0], min(y + dash - 1, b[1]))], fill=col, width=wd)
            d.line([(b[0], y), (b[0], min(y + dash - 1, b[1]))], fill=col, width=wd)

    box(TEXT, GRAY, dash=6, wd=1)
    box(CARD, GREEN, dash=7, wd=2)
    box(SLOT, BLUE, wd=2)
    box(STRY, ORANGE, wd=2)

    def chip(tx, ty, text, col, bgc=(255, 255, 255)):
        wpx = d.textlength(text, font=f_n)
        d.rectangle([tx - 4, ty - 3, tx + wpx + 5, ty + 18], fill=bgc, outline=col, width=1)
        d.text((tx, ty), text, font=f_n, fill=col)

    # 标注
    chip(*to(573, 190), '卡片格 243×64 CSS', GREEN)
    chip(*to(596, 258), '缩略位 28×24.5', BLUE)
    chip(*to(646, 100), '残留图形可见区 93.5×95.5', ORANGE)
    chip(*to(646, 118), '↑ 上沿高出卡片上边 46.5px，盖住正文', ORANGE)
    chip(*to(700, 282), '↓ 右/下沿在卡片内部被硬切（不在卡片边上）', ORANGE)
    chip(*to(576, 142), '正文行', GRAY)

    # ── 右栏数字 ──
    tx = PAD + iw + 34
    d.text((tx, y0 + 4), 'CSS 像素（= 设备 ÷ 2）', font=f_b, fill=INK)
    rows = [
        ('容器：卡片格', 'x 286.5 – 529.0 ｜ y 103.5 – 167.0', GREEN, '243 × 64'),
        ('槽位：缩略位（图标处）', 'x 302.0 – 330.0 ｜ y 123.5 – 148.0', BLUE, '28 × 24.5'),
        ('实际：可见区', 'x 320.0 – 413.5 ｜ y 57.0 – 152.5', ORANGE, '93.5 × 95.5'),
        ('', '', INK, ''),
        ('横向错位', '左沿 320 vs 槽位 302 → 偏右 18.0', INK, ''),
        ('', '右沿 413.5 vs 卡片右边 529 → 卡内 115.5 处被切', ORANGE, ''),
        ('纵向错位', '上沿 57.0 vs 卡片上边 103.5 → 高出 46.5', INK, ''),
        ('', '下沿 152.5 vs 卡片下边 167 → 卡内 14.5 处被切', ORANGE, ''),
        ('尺寸错位', '可见区 93.5×95.5 已是槽位 28×24.5 的 ~13 倍', INK, ''),
        ('', '覆盖正文行 y 70 – 87.5（完整落在它的纵向范围里）', INK, ''),
    ]
    yy = y0 + 30
    for lab, val, col, note in rows:
        if lab:
            d.text((tx, yy), lab, font=f_n, fill=col)
        if val:
            d.text((tx, yy + 17), val, font=f_n, fill=col)
            yy += 38
        else:
            yy += 14
        if note:
            d.text((tx + 300, yy - 22), note, font=f_n, fill=GRAY)

    # ── 脚注 ──
    fy = y0 + ih + 16
    d.line([(PAD, fy - 12), (W - PAD, fy - 12)], fill=LINE, width=1)
    d.text((PAD, fy),
           '关键推论：裁它的两条硬边（右 413.5 / 下 152.5）都不在这张卡片的边上（卡片右 529 / 下 167）——'
           '所以裁切它的框根本不是这张卡片，', font=f_b, fill=INK)
    d.text((PAD, fy + 22),
           '说明这个元素是相对另一个盒子定位的：典型的"残留 / 错位渲染"，不是文件内容问题。'
           '可见区面积只占源图约 1/4，正是你看到的"只有 1/4"。', font=f_b, fill=INK)
    d.text((PAD, fy + 46),
           '（更正：上一轮我说它是 _dialqt_c_pointing.png —— 本轮用四角颜色否掉了：那张图四角是不透明深灰 (64,64,68)，'
           '画上去周围不会是浅底。真身待定，但不影响上面的结论。）', font=f_n, fill=GRAY)

    out = os.path.join(HERE, '_pos_err.png')
    cv.save(out)
    print('saved %s  %s' % (out, cv.size))


if __name__ == '__main__':
    main()
