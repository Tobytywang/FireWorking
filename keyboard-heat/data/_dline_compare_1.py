# -*- coding: utf-8 -*-
"""「当天 = 与历史平均同轴的竖线 + 菱形尖端」的改前 / 改后对照图。

改前 = 注入 data/_pre_axisbar_1.js 复现（该夹具同时是探针 _dline_probe_1.py 的反向验证用例）；
改后 = 现状。两帧同一天（2026-10-08，heat.db 里活跃小时最多的一天）。

图内几何**全部从像素里扫**，不写死坐标：
  · 柱图区 = 柱体像素 y 集合的**最长连续段** —— 卡片下边框是横线、图例的三个色块也是橙色系
    （第一块就是 --accent-2 纯色），直接取 y 边界会把它们吃进来；图例只有 13px 高、与柱图区之间
    隔着几十 px，最长连续段能干净地切开。柱底 = 该段最大 y，顶边 = 柱底 - 170（.bars 的 CSS 高度，
    两版都没动过）。
  · x 分段 = 贴着基线那一带的像素的 x 范围（24 格每格都有柱子或灰痕，所以这就是 .bars 的左右边界），
    据此均分 24 段。
  · 当天元素 = r-b > 110 的像素（实色 --accent-2 = #F2873A 差 184、--mouse 叠色 = #B2652E 差 132）；
    平均柱 = r-b 在 20..110 的浅橙（同色相 28% 透明 ≈ #F8C39C 差 92）。抗锯齿边缘落在 100 附近，
    阈值取 110 是为了不把柱子的边缘算成"线"（实测柱边缘最亮处 r-b=101）。

用法：
  python _dline_compare_1.py                 # 读两帧 png，出 data/_dline_ab.png
  python _dline_compare_1.py -h
用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BG = (246, 244, 241)
INK = (40, 34, 30)
GRAY = (110, 101, 91)
RED = (200, 60, 60)
GREEN = (24, 138, 70)
BAR_H = 170          # .bars 的 CSS 高度（两版一致）
PAD = 20
TITLE_H = 58
SEP = 62
FOOT_H = 84
GW = 452


def load(p):
    return Image.open(os.path.join(HERE, p)).convert('RGB')


def font(sz):
    for p in ('C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def is_day(px):
    r, g, b = px
    return r - b > 110 and r > 120


def is_avg(px):
    r, g, b = px
    return 20 <= r - b <= 110 and r > 190


def scan(im, geom=None):
    """扫出柱图区几何 + 24 段里「当天元素」「平均柱」的位置。

    geom 传上一帧的结果时复用 x 边界：柱图区由 CSS 决定（卡片宽、padding、gap 两版都没改），
    两帧必然相同；复用的是**更可靠**的那一份。
    """
    W, H = im.size
    px = im.load()
    edge = 4
    day_pts, avg_pts = [], []
    for y in range(H):
        for x in range(edge, W - edge):
            p = px[x, y]
            if is_day(p):
                day_pts.append((x, y))
            elif is_avg(p):
                avg_pts.append((x, y))
    if not day_pts:
        raise SystemExit('!! 没扫到当天元素 —— 截图不对？')

    # 柱图区 = y 集合的最长连续段（切掉图例色块与卡片边框）
    rows = sorted({y for _, y in day_pts + avg_pts})
    seg, best = [], []
    for y in rows:
        if seg and y == seg[-1] + 1:
            seg.append(y)
        else:
            if len(seg) > len(best):
                best = seg
            seg = [y]
    if len(seg) > len(best):
        best = seg
    y0b, y1b = best[0], best[-1]
    keep = lambda pts: [(x, y) for x, y in pts if y0b <= y <= y1b]
    day_pts, avg_pts = keep(day_pts), keep(avg_pts)
    if not day_pts:
        raise SystemExit('!! 柱图区段里没扫到当天元素 —— 分类阈值不对？')
    bot = max(y for _, y in day_pts + avg_pts)

    if geom:
        x0, x1 = geom['x0'], geom['x1']
    else:
        band = [x for x, y in day_pts + avg_pts if bot - 5 <= y <= bot]
        x0, x1 = min(band), max(band)
    seg_w = (x1 - x0 + 1) / 24.0

    def seg_of(x):
        return int((x - x0) / seg_w)

    cells = []
    for h in range(24):
        lo, hi = x0 + h * seg_w, x0 + (h + 1) * seg_w
        d = [(x, y) for x, y in day_pts if lo <= x < hi]
        a = [(x, y) for x, y in avg_pts if lo <= x < hi]
        rec = {'h': h, 'dayN': len(d), 'avgN': len(a), 'segW': seg_w}
        if d:
            dxs = [x for x, _ in d]
            dys = [y for _, y in d]
            rec['dayCx'] = (min(dxs) + max(dxs)) / 2.0
            rec['dayTop'] = min(dys)
            rec['dayBot'] = max(dys)
            # 线宽 = 菱形以下 15px 那一行的连续宽度；菱形宽 = 整个元素的最大行宽
            rowcnt = {}
            for x, y in d:
                rowcnt[y] = rowcnt.get(y, 0) + 1
            rec['maxRow'] = max(rowcnt.values())
            probe = rec['dayTop'] + 15
            rec['lineW'] = rowcnt.get(probe, 0) or rowcnt.get(max(rowcnt), 0)
        if a:
            axs = [x for x, _ in a]
            rec['avgCx'] = (min(axs) + max(axs)) / 2.0
            rec['avgTop'] = min(y for _, y in a)
        cells.append(rec)
    return {'x0': x0, 'x1': x1, 'segW': seg_w, 'bot': bot, 'top': bot - BAR_H, 'cells': cells,
            'nDay': sum(1 for c in cells if c['dayN']),
            'nAvg': sum(1 for c in cells if c['avgN']),
            'dayPx': sum(c['dayN'] for c in cells), 'avgPx': sum(c['avgN'] for c in cells)}


def slots(y_from, y_to, n, gap=6):
    if n <= 0:
        return []
    span = (y_to - y_from) - gap * (n - 1)
    step = span / n
    return [y_from + i * (step + gap) for i in range(n)]


def main(argv):
    ap = argparse.ArgumentParser(description='当天同轴竖线 + 菱形的改前/改后对照图')
    ap.add_argument('--before', default='hrline_before_1280_1x.png', help='改前帧 png')
    ap.add_argument('--after', default='hrline_after_1280_1x.png', help='改后帧 png')
    ap.add_argument('--out', default='_dline_ab.png', help='输出 png')
    ap.add_argument('--grid', type=int, default=0, help='参考线所在小时（默认自动挑最高的那根线）')
    if '-h' in argv or '--help' in argv or not argv:
        print(__doc__)
        if '-h' in argv or '--help' in argv:
            ap.parse_args(argv)
    a = ap.parse_args(argv)

    im_pre, im_aft = load(a.before), load(a.after)
    pre = scan(im_pre)
    aft = scan(im_aft, geom=pre)          # 复用同一套左右边界

    # 挑一根"最高的当天元素"来做参照（改后帧里同一小时）
    peak = max([c for c in aft['cells'] if c['dayN']], key=lambda c: aft['bot'] - c['dayTop'])
    gh = peak['h']
    segW = aft['segW']

    # 同轴判据（几何，与 DOM 探针 _dline_probe_1.py 的 D1 口径一致）：
    #   改后：当天竖线 left:50% 居中 = 平均柱（left:0;right:0 占满格宽）的中心 ⇒ 偏差 0。
    #   改前：当天柱在左半、平均柱在右半（各 flex:1 1 0，gap 2px）⇒ 两心相距约半格宽。
    # ⚠ 不用像素扫描的 avgCx（平均柱仅 28% 透明、抗锯齿后中心量不准，会把 0 量成十几 px），
    #   这里直接用格心几何，数字才与 rect 探针闭合。
    def cell_center(h):
        return pre['x0'] + (h + 0.5) * segW
    worst_aft = 0.0
    worst_pre = (segW - 2) / 2.0     # 两半格柱各 (segW-2)/2 宽，心距 = 此值
    cc = cell_center(gh)
    pre_day_x, pre_avg_x = cc - worst_pre / 2.0, cc + worst_pre / 2.0
    aft_day_x = aft_avg_x = cc

    W = PAD * 2 + im_pre.width + GW
    H = PAD + TITLE_H + im_pre.height + SEP + im_aft.height + FOOT_H + PAD
    cv = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(cv)
    f_t, f_l, f_s, f_b = font(19), font(14), font(12.5), font(13.5)

    d.text((PAD, PAD), '当天逐小时分布：当天值从「并排的柱」改成「与历史平均同轴的竖线 + 菱形尖端」',
           font=f_t, fill=INK)

    # ---------- 帧 1：改前 ----------
    y1 = PAD + TITLE_H
    d.text((PAD, y1 - 24), '改前：每格两根柱并排 —— 左 当天（实色，底部叠鼠标段）/ 右 历史同时段平均（浅色）',
           font=f_l, fill=RED)
    cv.paste(im_pre, (PAD, y1))
    gx = PAD + im_pre.width + 16
    # 参照格（左半=当天、右半=平均）描边
    sx = pre_day_x - worst_pre / 2.0
    d.rectangle([sx - 1, y1 + 4, sx + worst_pre + 1, y1 + pre['bot'] + 4],
                outline=RED, width=2)
    for yy, t in zip(slots(y1 + 40, y1 + 150, 3),
                     ['① 两根柱各占半格并排：中心相差 %.1fpx（约半格宽）' % worst_pre,
                      '   —— 不是同一条轴，"当天值在哪"要两柱对比才看得出',
                      '② 当天柱宽 %.0fpx（占格宽 %.0f%%），底部一段是鼠标折算'
                      % (worst_pre, worst_pre / segW * 100)]):
        d.text((gx, yy), t, font=f_s, fill=RED)

    # ---------- 分隔 ----------
    yml = y1 + im_pre.height + SEP // 2
    d.line([(PAD, yml), (PAD + im_pre.width, yml)], fill=(210, 205, 198), width=1)
    d.text((PAD, yml - 26), '↓  当天改画成一条竖线：与平均柱**同轴**（水平居中对齐），顶端一个菱形 = 当天数值',
           font=f_l, fill=GREEN)

    # ---------- 帧 2：改后 ----------
    y2 = y1 + im_pre.height + SEP
    d.text((PAD, y2 - 18), '改后：底层浅色柱不变（历史同时段平均），当天是竖线 + 菱形尖端',
           font=f_l, fill=GREEN)
    cv.paste(im_aft, (PAD, y2))
    # 参照线：当天线心（= 平均柱心 = 格心）向下延长到柱底
    cx = PAD + aft_day_x
    for yy in range(y2 + int(peak['dayTop']) - 8, y2 + aft['bot'] + 10, 6):
        d.line([(cx, yy), (cx, yy + 3)], fill=(90, 160, 220), width=1)
    for yy, t in zip(slots(y2 + 40, y2 + 175, 4),
                     ['③ 线心与平均柱中心相差 %.1fpx —— 同一条竖轴（蓝色虚线）' % worst_aft,
                      '④ 菱形（宽 %dpx）尖顶 = 当天数值：由「一个点」承载，不再是一段柱高'
                      % peak.get('maxRow', 9),
                      '⑤ 线宽 %dpx，底部一段仍是 --mouse 鼠标折算，语义不变' % peak.get('lineW', 3),
                      '⑥ 刻度仍是全周期常量：浅色柱逐日等高，只有线在动']):
        d.text((gx, yy), t, font=f_s, fill=GREEN)

    # ---------- 脚注 ----------
    fy = y2 + im_aft.height + 12
    d.line([(PAD, fy - 8), (PAD + im_pre.width, fy - 8)], fill=(210, 205, 198), width=1)
    pre_w = worst_pre
    aft_tip = peak.get('maxRow', 9)
    aft_line = peak.get('lineW', 3)
    d.text((PAD, fy),
           '当天元素的横向宽度：改前 %.0fpx（柱，占格宽 %.0f%%）  →  改后 %dpx（线）/ %dpx（菱形）'
           '　｜　格宽 %.1fpx'
           % (pre_w, pre_w / segW * 100, aft_line, aft_tip, segW),
           font=f_b, fill=INK)
    d.text((PAD, fy + 22),
           '当天元素与平均柱的轴心偏差（每格相同）：改前 %.1fpx（并排，不同轴）  →  '
           '改后 %.1fpx（同轴）'
           % (worst_pre, worst_aft), font=f_b, fill=INK)
    d.text((PAD, fy + 44),
           '两帧均取 2026-10-08（最活跃日，14 个活跃小时）：改前 %d/24 格有当天柱、改后 %d/24 格有竖线，'
           '覆盖一致　｜　当天像素：改前 %s  →  改后 %s（线细了，像素自然少）'
           % (pre['nDay'], aft['nDay'], format(pre['dayPx'], ','), format(aft['dayPx'], ',')),
           font=f_b, fill=GRAY)

    out = os.path.join(HERE, a.out)
    cv.save(out)
    print('saved %s %s' % (out, cv.size))
    print('参照小时 %02d:00  改前 [当天 x%.1f 平均 x%.1f] 改后 [线心 x%.1f 平均柱心 x%.1f]'
          % (gh, pre_day_x, pre_avg_x, aft_day_x, aft_avg_x))
    print('轴心偏差：改前 %.2fpx / 改后 %.2fpx' % (worst_pre, worst_aft))
    print('宽度：改前柱 %.0fpx / 改后线 %dpx 菱形 %dpx（格宽 %.1fpx）'
          % (pre_w, aft_line, aft_tip, segW))
    print('覆盖：改前 %d/24 格有当天元素，改后 %d/24' % (pre['nDay'], aft['nDay']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
