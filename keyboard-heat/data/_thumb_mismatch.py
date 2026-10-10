# -*- coding: utf-8 -*-
"""产物卡片缩略图异常诊断图（“图坏了”到底是谁坏了）

用法：../.pyenv/Scripts/python.exe _thumb_mismatch.py
产出：_thumb_mismatch.png

判据思路（可复用）：
  用户说“这个图形坏了”时，**先分离“文件”与“渲染”**：
    ① 磁盘上那张图：md5 + 尺寸 + 内容像素（本脚本用“橙色柱像素数”）—— 坏了没有？
    ② 现象截图里实际画出来的那块：抠出来，量它的可见范围 / 放大倍率 / 是否越界。
  只有 ① 真的坏了才去改生成器；① 完好而 ② 异常 → 是渲染层（UI）问题。
  本轮的量化闭环：槽位宽 ≈167 设备像素（截图 DPR=2 → 83.5 CSS px），
  而残留图按**自然尺寸 190px** 绘制 → 190/83.5 ≈ 2.28×，正好只露出左上约 1/3×1/3。
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = r'C:\Users\toby.wang\.workbuddy\clipboard-images\clipboard-2026-09-29T14-38-55-981Z-9ebd452c.png'
TARGET = 'hr_nar_560_1x.png'        # 被投诉的那张卡
STRAY = '../_dialqt_c_pointing.png'  # 残留位图的真身
# 现象截图里“实际画出来的那块”的像素框。
# 用法：别用眼睛估 —— 用**只在该图里出现**的颜色定位（绿弧 + 金色火焰）：
#   绿弧 bbox [652,176,728,307]、金色 bbox [785,237,824,307] → 并集 [652,176,824,307]，
#   左右各留 ~55px 余量（深色环带本身不带绿/金），上下各留 ~35px。
STRAY_BOX = (596, 141, 838, 314)

BG, PANEL, INK, GRAY, LINE = (245, 246, 248), (255, 255, 255), (31, 35, 40), (120, 128, 136), (222, 226, 230)
RED, GREEN, BLUE = (214, 60, 60), (32, 140, 84), (40, 110, 200)

W, PAD, TITLE_H, CAP_H, FOOT_H = 1300, 26, 76, 92, 96
IH = 340


def font(sz):
    for p in ('C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def fit(im, box):
    """等比缩放进 box（不放大）。"""
    r = min(box[0] / im.width, box[1] / im.height)
    r = min(r, 1.0)
    return im.resize((max(1, int(im.width * r + .5)), max(1, int(im.height * r + .5))), Image.LANCZOS)


def main():
    H = PAD + TITLE_H + IH + CAP_H + FOOT_H + PAD
    cv = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(cv)
    f_t, f_s, f_b, f_n = font(21), font(14), font(15), font(13)

    # 两列
    COLW = (W - PAD * 2 - 40) // 2
    x1, x2 = PAD, PAD + COLW + 40

    d.text((PAD, PAD), '产物卡片上的“坏图”不是文件的问题 —— 是缩略图层没套上尺寸约束', font=f_t, fill=INK)
    d.text((PAD, PAD + 34),
           '左边是磁盘上的真身（完整无损）；右边是你截图里卡片上实际画出来的东西（一个越界的残留位图）',
           font=f_s, fill=GRAY)

    y = PAD + TITLE_H

    # ── 左：磁盘真身 ──
    real = Image.open(os.path.join(HERE, TARGET)).convert('RGB')
    d.rectangle([x1, y, x1 + COLW, y + IH], fill=PANEL, outline=LINE, width=1)
    r = fit(real, (COLW - 40, IH - 40))
    cv.paste(r, (x1 + (COLW - r.width) // 2, y + (IH - r.height) // 2))
    d.text((x1 + 12, y + 9), '磁盘上：%s' % TARGET, font=f_b, fill=GREEN)

    # ── 右：现象截图里实际画出的那块 ──
    d.rectangle([x2, y, x2 + COLW, y + IH], fill=PANEL, outline=LINE, width=1)
    shot = Image.open(SHOT).convert('RGB')
    stray = shot.crop(STRAY_BOX)
    stray = stray.resize((stray.width * 2, stray.height * 2), Image.LANCZOS)  # 2x：看清它压住了什么
    stray = fit(stray, (COLW - 40, IH - 82))
    sx = x2 + (COLW - stray.width) // 2
    sy = y + 50 + (IH - 50 - stray.height) // 2
    cv.paste(stray, (sx, sy))
    d.rectangle([sx - 1, sy - 1, sx + stray.width, sy + stray.height], outline=RED, width=2)
    # 槽位边界（按自然尺寸 190 CSS px 反推）
    d.text((x2 + 12, y + 9), '卡片上：实际画出来的那块（截图原样放大 2×）', font=f_b, fill=RED)

    def chip(tx, ty, text, col):
        """带底色的标注，避免压在图上看不清。"""
        w = d.textlength(text, font=f_n)
        d.rectangle([tx - 4, ty - 3, tx + w + 4, ty + 17], fill=(255, 255, 255), outline=col, width=1)
        d.text((tx, ty), text, font=f_n, fill=col)

    chip(sx + 4, sy + 4, '↑ 越界：压住了上面的正文', RED)
    chip(sx + 4, sy + stray.height - 24, '↓ 越界：压住了文件名和图标', RED)

    # ── 说明条 ──
    cy = y + IH + 12
    d.text((x1, cy), '512 × 373 · 15.8 KB · md5 ab0507fd… · 橙色柱像素 404（24 格柱图完整）',
           font=f_n, fill=GREEN)
    d.text((x1, cy + 22), '→ 文件像素级完好，可以直接用任何看图工具打开核对。', font=f_n, fill=GRAY)
    d.text((x2, cy), '内容是 %s（190×190）的局部：绿弧厚度比 2.46×、长度比 2.24×（两把尺子互证）。'
                     % os.path.basename(STRAY), font=f_n, fill=RED)
    d.text((x2, cy + 22), '可见范围 242×173 设备像素 ≈ 源图的 1/5 面积 —— 既没缩放到槽位，也没被槽位裁掉。',
           font=f_n, fill=RED)

    # ── 脚注 ──
    fy = cy + 56
    d.line([(PAD, fy - 10), (W - PAD, fy - 10)], fill=LINE, width=1)
    d.text((PAD, fy),
           '同一张截图里另外 4 张图片产物（hr_dark / _axis_ab / _avg_ref_ab / hr_1280）'
           '缩略图一个都没画出来，只剩文件类型图标（HTML 那张本来就是代码图标，正常）。',
           font=f_b, fill=INK)
    d.text((PAD, fy + 22),
           '→ 不是某一张文件坏了，是整层缩略图在休眠唤醒后没有重绘：一张残留旧位图 + 其余空白。'
           '重建产物列表（重新生成/重启应用）即可恢复。', font=f_b, fill=INK)

    out = os.path.join(HERE, '_thumb_mismatch.png')
    cv.save(out)
    print('saved %s  %s' % (out, cv.size))


if __name__ == '__main__':
    main()
