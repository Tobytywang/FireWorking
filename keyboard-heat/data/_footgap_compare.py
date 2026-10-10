# -*- coding: utf-8 -*-
"""活动日历「图例（注脚）带的垂直空白」改前/改后对照图。

改前 = 注入旧规则（margin-top:14px; line-height:1.6，即继承值）；
改后 = 生成器当前状态。

三条标线全部来自**探针实测的绝对页面坐标**（CSS px × dsf = 设备 px，纵向无偏移；
横向才有 ~7px 偏移，本图不涉及横向）：
  内容墨迹底  = 最后一排格子的底（网格内容的视觉底边）
  图例色块顶  = 注脚色块的顶（不是行盒顶 —— 行盒里那半行距是看不见的）
  gap        = 两者之差，就是用户圈出来的那块空白
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ui_geom_probe as P

HERE = os.path.dirname(os.path.abspath(__file__))
OLD_CSS = '.legend{margin-top:14px;line-height:1.6}'
WIDTH, DSF = 1144, 1.5


def capture(tag, css, width=WIDTH, dsf=DSF):
    """返回 (截图路径, foots 记录)。测量与截图共用同一份 TMP。"""
    P.build(css, clip=True, only='#year-cal')
    rec = P.measure(width, dsf)
    foot = next((f for f in (rec or {}).get('foots', []) if f['host'] == 'year-cal'), None)
    shot = os.path.join(HERE, '_fg_%s.png' % tag)
    P.chrome(['--screenshot=' + shot], width, 420, dsf)
    return shot, foot


def main():
    cases = []
    for tag, css, cn, col in [('before', OLD_CSS, '改前', (192, 57, 43)),
                              ('after', '', '改后', (22, 130, 93))]:
        shot, f = capture(tag, css)
        if not f:
            print('!! 没量到注脚带'); return
        cases.append((shot, f, cn, col))

    f0 = cases[0][1]
    # 裁带：从内容墨迹底上方 46 CSS px 到色块底下方 34 CSS px（含卡片下边）
    y0 = int((f0['gridInkBot'] - 46) * DSF)
    y1 = int((f0['inkB'] + 34) * DSF)

    strips = []
    for shot, f, cn, col in cases:
        im = Image.open(shot).convert('RGB')
        im = im.crop((0, y0, im.width, min(y1, im.height)))
        d = ImageDraw.Draw(im)
        W, H = im.size

        def dash(y, c, w=2):
            for x in range(0, W, 12):
                d.line([(x, y), (x + 6, y)], fill=c, width=w)

        yg = int(f['gridInkBot'] * DSF) - y0          # 内容墨迹底
        yl = int(f['inkT'] * DSF) - y0                # 色块墨迹顶
        dash(yg, (105, 105, 105))
        dash(yl, col, 3)
        # 间距标注（竖双箭头）。间距小的时候数字会压在虚线上 → 垫一块白底
        xa = 30
        d.line([(xa, yg), (xa, yl)], fill=col, width=2)
        for yy in (yg, yl):
            d.line([(xa - 5, yy), (xa + 5, yy)], fill=col, width=2)
        txt = '%.1fpx' % f['footGap']
        tw = d.textlength(txt, font=F)
        d.rectangle([xa + 9, (yg + yl) / 2 - 9, xa + 15 + tw, (yg + yl) / 2 + 6], fill=(255, 255, 255))
        d.text((xa + 12, (yg + yl) / 2 - 7), txt, font=F, fill=col)
        t1 = '内容墨迹底 y=%d' % f['gridInkBot']
        d.text((W - 12 - d.textlength(t1, font=F), yg - 18), t1, font=F, fill=(105, 105, 105))
        t2 = '图例色块顶 y=%d' % f['inkT']
        d.text((W - 12 - d.textlength(t2, font=F), yl + 4), t2, font=F, fill=col)
        strips.append((im, cn, col, f))
        print('%s  footGap=%.1f  行盒高 %.1f  墨迹高 %.1f  rowSlack %.1f'
              % (cn, f['footGap'], f['rowH'], f['inkH'], f['rowSlack']))

    BAR = 36
    W = strips[0][0].width
    canvas = Image.new('RGB', (W, len(strips) * (BAR + strips[0][0].height) + 10), (255, 255, 255))
    y = 0
    d = ImageDraw.Draw(canvas)
    for im, cn, col, f in strips:
        d.text((8, y + 9), '%s　内容→图例 %.1fpx　注脚行盒 %.1fpx（其中看不见的 %0.1fpx）'
               % (cn, f['footGap'], f['rowH'], f['rowSlack']), font=FB, fill=col)
        canvas.paste(im, (0, y + BAR))
        y += BAR + im.height + 6
    out = os.path.join(HERE, '_footgap_compare.png')
    canvas.save(out)
    print('written', out, canvas.size)


F = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 13)
FB = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 16)

if __name__ == '__main__':
    main()
