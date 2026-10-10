# -*- coding: utf-8 -*-
"""「这块图形是哪张图的什么倍率/偏移？」—— 候选图模板匹配

用途：用户截图上有一块**来路不明**的图形（残留位图 / 渲染错位），要在候选图里认出它。

用法：
  ../.pyenv/Scripts/python.exe _stray_ident.py <截图> <x0,y0,x1,y1> <候选png...>

方法要点（可复用）：
  · 特征取「**只在该图里出现**的颜色掩码」（本例绿弧），绝不用"深色"——正文文字也是深色；
  · 倍率初值 = （目标最大行宽 / 候选最大行宽），再在 0.85~1.15 倍内细搜；
  · 平移先按**质心对齐**，再小网格局部搜索；打分用 **IoU**；
  · ⚠ IoU 的分母含目标全部像素 —— 目标被裁掉一部分时 IoU 上限天然被压低，
    所以**只拿它做相对排序**，别把绝对值当"匹配度"。
"""
import os
import sys
from collections import Counter
from PIL import Image


def green_pts(im):
    px = im.load()
    out = []
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = px[x, y]
            if g > 105 and g - r > 40 and g - b > 40:
                out.append((x, y))
    return out


def match(tpts, cpts, scales, offs):
    tset = set(tpts)
    tcx = sum(p[0] for p in tpts) / len(tpts)
    tcy = sum(p[1] for p in tpts) / len(tpts)
    ccx = sum(p[0] for p in cpts) / len(cpts)
    ccy = sum(p[1] for p in cpts) / len(cpts)
    best = None
    for s in scales:
        for dx in offs:
            for dy in offs:
                ox = tcx - s * ccx + dx
                oy = tcy - s * ccy + dy
                pts = set((int(ox + s * a + .5), int(oy + s * b + .5)) for a, b in cpts)
                inter = len(pts & tset)
                if not inter:
                    continue
                iou = inter / float(len(pts) + len(tset) - inter)
                if best is None or iou > best[0]:
                    best = (iou, s, ox, oy, inter, len(pts))
    return best


def main():
    shot = Image.open(sys.argv[1]).convert('RGB')
    x0, y0, x1, y1 = [int(v) for v in sys.argv[2].split(',')]
    cands = sys.argv[3:]
    tpts = green_pts(shot.crop((x0, y0, x1, y1)))
    if len(tpts) < 20:
        raise SystemExit('!! 区域内绿像素不足（%d），换特征或换区域' % len(tpts))
    c = Counter(x for x, _ in tpts)
    tmax = max(c.values())
    print('目标区域 %s：绿像素 %d，最大行宽 %d' % ((x0, y0, x1, y1), len(tpts), tmax))
    print()
    rank = []
    for p in cands:
        try:
            im = Image.open(p).convert('RGB')
        except Exception:
            continue
        cpts = green_pts(im)
        if len(cpts) < 20:
            continue
        c = Counter(x for x, _ in cpts)
        s0 = tmax / float(max(c.values()))
        offs = [-8, -4, 0, 4, 8]
        scales = [s0 * k for k in (0.85, 0.95, 1.0, 1.05, 1.15)]
        b = match(tpts, cpts, scales, offs)
        if b:
            rank.append((b[0], os.path.basename(p), b[1], b[2], b[3], len(cpts), os.path.getsize(p)))
    rank.sort(reverse=True)
    print('%-26s %6s %8s %8s %8s %8s' % ('候选', 'IoU', '倍率', '左上x', '左上y', '源绿px'))
    for iou, name, s, ox, oy, n, sz in rank[:10]:
        print('%-26s %6.3f %7.2fx %8.1f %8.1f %8d   (%d B)' % (name, iou, s, ox, oy, n, sz))
    if not rank:
        print('（没有候选图能在该区域里匹配上绿弧特征）')


if __name__ == '__main__':
    main()
