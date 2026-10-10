# -*- coding: utf-8 -*-
"""键鼠活动记录卡片：改前（tab 互斥）/ 改后（日历 + 当天平铺）对照图。

改前 = 注入 `_pre_tabsback.js` 复现：顶部一条 tab 栏（日历 / 周×小时 / 当天），
       同一位置只显示一个视图；想看待天要再点一次 tab；点日历日期还会再切一次视图。
改后 = 现状：卡片里两个块**都直接展开**，中间一条细线分隔；tab 栏与「周×小时」已删除。

图内坐标全部**从像素里扫**，不写死：
  · 改前的 tab 栏 = 高亮 tab 的橙色药丸（`--accent`）墨迹外接框；
  · 改后的分隔线 = 卡片内三条 `--line` 横线（面板上边框 / 分隔线 / 面板下边框）中间那条，
    需要恰好扫到 3 条，否则直接报错（宁可吵，也不要静默画错位置）。
用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BG = (246, 244, 241)
GRAY = (110, 101, 91)
INK = (40, 34, 30)
RED = (200, 60, 60)
GREEN = (47, 158, 68)
ACCENT = (232, 89, 12)
# `--line: rgba(40,33,26,.12)` 叠在白卡上 → 实测 (229,228,227)
LINE_RGB = (229, 228, 227)


def load(p):
    return Image.open(os.path.join(HERE, p)).convert('RGB')


def font(sz):
    for p in ('C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def find_accent_bbox(im, tol=26):
    """高亮 tab 的橙色药丸外接框。
    ⚠ 不能只"扫所有橙色像素再取外接框"：同色 `--accent` 还出现在 h2 左侧竖条与
      日历里最深一档格子（色阶末端就是 accent）上 —— 实测那样会量到整张图 (0,13,982,277)。
       所以取**最大橙色连通块**（药丸 ~64×32 实心，远大于 3px 竖条与 13px 格子）。"""
    px = im.load()
    W, H = im.size
    mask = [[False] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            if abs(r - ACCENT[0]) <= tol and abs(g - ACCENT[1]) <= tol and abs(b - ACCENT[2]) <= tol:
                mask[y][x] = True
    best = None
    for y0 in range(H):
        for x0 in range(W):
            if not mask[y0][x0]:
                continue
            stack = [(x0, y0)]
            mask[y0][x0] = False
            n = 0
            bx0 = bx1 = x0
            by0 = by1 = y0
            while stack:
                x, y = stack.pop()
                n += 1
                bx0 = min(bx0, x); bx1 = max(bx1, x)
                by0 = min(by0, y); by1 = max(by1, y)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H and mask[ny][nx]:
                        mask[ny][nx] = False
                        stack.append((nx, ny))
            if best is None or n > best[0]:
                best = (n, bx0, by0, bx1, by1)
    if not best:
        raise SystemExit('!! 没扫到高亮 tab 的橙色 —— 夹具没生效？')
    print('   橙色连通块最大者：%d px 外接框 %s' % (best[0], best[1:]))
    return best[1:]


def find_hlines(im):
    """卡片内的 `--line` 横线：返回 [(y, xstart, runlen)]。
    预期恰好 3 条：面板上边框 / 两块之间的分隔线 / 面板下边框。"""
    px = im.load()
    W, H = im.size
    out = []
    for y in range(H):
        run, start, best = 1, 0, (0, 0)
        for x in range(1, W):
            if px[x, y] == px[x - 1, y]:
                run += 1
                if run > best[0]:
                    best = (run, start)
            else:
                run, start = 1, x
        c = px[best[1] + 1, y] if best[0] else None
        if c and best[0] >= 800 and all(abs(c[i] - LINE_RGB[i]) <= 2 for i in range(3)):
            out.append((y, best[1], best[0]))
    if len(out) != 3:
        raise SystemExit('!! 扫描到 %d 条 --line 横线，预期 3 条（上边框/分隔线/下边框）：%s'
                         % (len(out), out))
    return out


def find_tabbar_box(im, pill):
    """整条 tab 栏的外框：从药丸中心向右/左/上/下走，撞到栏边框为止。
    栏边框色 = `--line`(rgba(40,33,26,.12)) 叠在 `--card-2`(#faf8f5) 上 ≈ (225,222,219)；
    ⚠ 必须与"叠在白卡上"的 (229,228,227) 区分开（tol=4 时两者差 (4,6,8)，分得清），
       否则会一路走到面板边框，把整张卡片圈进去。"""
    px = im.load()
    W, H = im.size
    BORDER, tol = (225, 222, 219), 4

    def near(c):
        return all(abs(c[i] - BORDER[i]) <= tol for i in range(3))

    cx = (pill[0] + pill[2]) // 2
    cy = (pill[1] + pill[3]) // 2
    x0 = cx
    while x0 > 0 and not near(px[x0, cy]):
        x0 -= 1
    x1 = cx
    while x1 < W - 1 and not near(px[x1, cy]):
        x1 += 1
    y0 = cy
    while y0 > 0 and not near(px[cx, y0]):
        y0 -= 1
    y1 = cy
    while y1 < H - 1 and not near(px[cx, y1]):
        y1 += 1
    return x0, y0, x1, y1


pre = load('pb_1280_1x.png')      # 改前（tab 模式）
aft = load('pa_1280_1x.png')      # 改后（平铺）

tb = find_accent_bbox(pre)
bar = find_tabbar_box(pre, tb)
hl = find_hlines(aft)
div_y = hl[1][0]
div_x0, div_w = hl[1][1], hl[1][2]
panel_bot = hl[2][0]
day_box = (div_x0, div_y + 1, div_x0 + div_w - 1, panel_bot - 1)
print('改前 tab 药丸 bbox=%s | tab 栏外框=%s | 改后 --line 三条 y=%s | 分隔线 y=%d x=%d..%d | 当天块 %s'
      % (tb, bar, [h[0] for h in hl], div_y, div_x0, div_x0 + div_w, day_box))

PAD, LAB, ROWGAP, GUT = 26, 30, 26, 300
W = PAD * 2 + max(pre.width, aft.width) + GUT
H = PAD + LAB + pre.height + ROWGAP + LAB + aft.height + PAD
cv = Image.new('RGB', (W, H), BG)
d = ImageDraw.Draw(cv)
f_cap, f_lab, f_sm = font(17), font(13), font(12)

d.text((PAD, 8), '键鼠活动记录：只留「日历 + 当天」，平铺展开（不再用 tab 合并切换）',
       font=font(19), fill=INK)

x0 = PAD
gx = PAD + max(pre.width, aft.width) + 16

# ── 改前 ──
y = PAD + LAB
d.text((x0, y - LAB + 6),
       '改前｜tab 互斥：一屏只看到一个视图，「当天」要先点 tab；点日期还会再切一次视图',
       font=f_cap, fill=GRAY)
cv.paste(pre, (x0, y))
d.rectangle([x0 + bar[0] - 3, y + bar[1] - 3, x0 + bar[2] + 3, y + bar[3] + 3], outline=RED, width=2)
d.text((gx, y + bar[1] - 4), '① tab 栏：日历 / 周×小时 / 当天', font=f_lab, fill=RED)
d.text((gx, y + bar[1] + 14), '   切换控件 + 要维护 active 状态', font=f_sm, fill=RED)
d.text((gx, y + bar[3] + 18), '② 当天块被藏起来（hidden）', font=f_lab, fill=RED)
d.text((gx, y + bar[3] + 36), '   隐藏元素没有 rect → 量宽度前', font=f_sm, fill=RED)
d.text((gx, y + bar[3] + 52), '   得先"临时揭示"再量', font=f_sm, fill=RED)

# ── 改后 ──
y = PAD + LAB + pre.height + ROWGAP + LAB
d.text((x0, y - LAB + 6),
       '改后｜日历 + 当天同时平铺：两块都直接展开，中间一条细线分隔；点日期只更新下方当天',
       font=f_cap, fill=INK)
cv.paste(aft, (x0, y))
d.line([(x0 + div_x0, y + div_y), (x0 + div_x0 + div_w, y + div_y)], fill=GREEN, width=2)
d.rectangle([x0 + day_box[0], y + day_box[1], x0 + day_box[2], y + day_box[3]],
            outline=GREEN, width=2)
d.text((gx, y + div_y - 16), '③ 细线分隔 + 18/16px 留白', font=f_lab, fill=GREEN)
d.text((gx, y + day_box[1] + 6), '④ 当天块直接展开', font=f_lab, fill=GREEN)
d.text((gx, y + day_box[1] + 24), '   两块恒可见 → 量宽度不再需要', font=f_sm, fill=GREEN)
d.text((gx, y + day_box[1] + 40), '   "切回来重算"那套补丁', font=f_sm, fill=GREEN)

out = os.path.join(HERE, '_flat_tabs_ab.png')
cv.save(out)
print('saved', out, cv.size)
