# -*- coding: utf-8 -*-
"""把两块区域裁出来、最近邻放大，供肉眼判断"4 卡底边 / 面板顶边 / 中间间隙"到底在哪。

用 NEAREST 而非 BILINEAR：要保留 1px 边框线的**硬边**，抗锯齿插值会把细线糊成渐变，
反而看不出"线在哪一行"。
"""
from PIL import Image

USER = (r'C:\Users\toby.wang\.workbuddy\clipboard-images'
        r'\clipboard-2026-10-08T01-10-05-214Z-efcb8dfc.png')
MINE = r'D:\Workspace\HardWorking\keyboard-heat\data\_cdgap_now_1280.png'

JOBS = [
    # (源, 裁剪框, 放大倍数, 输出, 左半 x0)
    (USER, (0, 118, 505, 212), 3, r'D:\Workspace\HardWorking\keyboard-heat\data\_cdgap_user_zoom.png'),
    (MINE, (95, 40, 600, 134), 3, r'D:\Workspace\HardWorking\keyboard-heat\data\_cdgap_mine_zoom.png'),
]

for src, box, k, out in JOBS:
    im = Image.open(src).convert('RGB')
    c = im.crop(box)
    c = c.resize((c.width * k, c.height * k), Image.NEAREST)
    c.save(out)
    print('%s  crop=%s  scale=%dx  ->  %s (%dx%d)'
          % (src.split('\\')[-1], box, k, out.split('\\')[-1], c.width, c.height))
