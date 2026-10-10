# -*- coding: utf-8 -*-
"""像素级扫描：找出「4 卡底边」与「按类型分布卡片顶边」之间的真实间隙（屏幕 px）。

用于对齐两边的观感差异：
  A) _cdgap_now_1280.png —— 我这边原型（--clip --only #countdown，dsf=1，未缩放）
  B) 用户截图 —— 来源未知，需先测出其缩放比

手法：对每一行 y，统计 x 区间内的像素颜色分布。
  · 空白行：主色占比 ≈ 1.00（整行都是页面背景）
  · 边框/线行：出现一条横贯的异色线（主色占比骤降）
把"线行"的 y 列出来，就能直接读出结构。
"""
import collections
import sys

from PIL import Image

USER = (r'C:\Users\toby.wang\.workbuddy\clipboard-images'
        r'\clipboard-2026-10-08T01-10-05-214Z-efcb8dfc.png')
MINE = r'D:\Workspace\HardWorking\keyboard-heat\data\_cdgap_now_1280.png'


def scan(path, x0, x1, y0, y1, step=2, tag=''):
    im = Image.open(path).convert('RGB')
    W, H = im.size
    x1 = min(x1, W)
    y1 = min(y1, H)
    print('== [%s] %s  %dx%d | 列 %d..%d  行 %d..%d' % (tag, path, W, H, x0, x1, y0, y1))
    prev_main = None
    for y in range(y0, y1):
        px = [im.getpixel((x, y)) for x in range(x0, x1, step)]
        c = collections.Counter(px)
        top, n = c.most_common(1)[0]
        frac = n / len(px)
        mark = ''
        if frac < 0.995:
            mark = '  <== 非纯背景行（主色占比 %.2f）' % frac
        print('  y=%4d  主色 %-18s 占比 %.3f  唯一色 %3d%s'
              % (y, str(top), frac, len(c), mark))
        prev_main = top
    print()


if __name__ == '__main__':
    scan(USER, 20, 985, 128, 205, tag='用户截图')
    scan(MINE, 110, 1170, 55, 130, tag='原型1280')
