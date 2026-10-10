"""改前/改后对照图：唯一差别是"打开统计面板"后面那条分隔线。

文本行、子菜单箭头、分隔线位置**全部读自真实 QMenu**（action.text() /
actionGeometry() / action.menu()），只有绘制交给 PIL —— 因为离屏平台一个
字体都没有，Qt 自己渲染出来的中文全是豆腐块。所以这是"真实结构 + 可读字形"
的示意图，不是凭空画的 mock。

改前那一版同样来自真实的菜单对象：把统计面板后那条分隔线 removeAction 掉
再取一次几何，保证两张图只差这一条线。

输出：_menu_group_compare.png
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import heatcore
import overlay
from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtWidgets import QApplication

OUT = "_menu_group_compare.png"
K = 1.6                      # 放大系数（离屏条目高只有 20px，放大后才好看）
FONT = "C:/Windows/Fonts/msyh.ttc"


def rows_of(menu):
    """[(文字, 是否分隔线, y, 高, 有无子菜单)] —— 全部取真实几何。"""
    menu.ensurePolished()
    menu.adjustSize()
    out = []
    for a in menu.actions():
        g = menu.actionGeometry(a)
        out.append((a.text() or "", a.isSeparator(), g.y(), g.height(),
                    a.menu() is not None))
    return out, menu.sizeHint().width(), menu.sizeHint().height()


def groups_of(menu):
    groups, cur = [], []
    for a in menu.actions():
        if a.isSeparator():
            if cur:
                groups.append(cur)
            cur = []
        else:
            cur.append(a.text() or "[sub]")
    if cur:
        groups.append(cur)
    return groups


def show(groups, tag):
    print("--- %s ---" % tag)
    for k, g in enumerate(groups, 1):
        print("  组%d: %s" % (k, " | ".join(g)))


def draw_menu(rows, w, h, font):
    img = Image.new("RGB", (int(w * K), int(h * K)), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width - 1, img.height - 1], outline=(205, 205, 205))
    for text, is_sep, y, hh, has_menu in rows:
        ymid = int((y + hh / 2.0) * K)
        if is_sep:
            d.line([int(5 * K), ymid, img.width - int(5 * K), ymid],
                   fill=(231, 231, 231), width=2)
        else:
            d.text((int(11 * K), ymid), text, font=font, fill=(25, 25, 25), anchor="lm")
            if has_menu:
                d.text((img.width - int(14 * K), ymid), "›", font=font,
                       fill=(70, 70, 70), anchor="mm")
    return img


def main():
    svc = heatcore.HeatService().start()
    app = QApplication(sys.argv)
    dial = overlay.HeatDial(svc)
    menu = dial._menu

    rows_after, w, h_after = rows_of(menu)
    g_after = groups_of(menu)

    acts = menu.actions()
    i_rep = next(i for i, a in enumerate(acts) if a.text() == "打开统计面板")
    sep = acts[i_rep + 1]
    assert sep.isSeparator(), "统计面板后面不是分隔线，锚点失效"
    menu.removeAction(sep)
    rows_before, _, h_before = rows_of(menu)
    g_before = groups_of(menu)

    show(g_before, "改前（统计面板与计时组粘连）")
    show(g_after, "改后（统计面板独占一组）")

    f_big = ImageFont.truetype(FONT, 21)
    f_mid = ImageFont.truetype(FONT, 16)
    f_small = ImageFont.truetype(FONT, 15)

    w_total = max(w, 76) + 16
    p_before = draw_menu(rows_before, w_total, h_before, f_mid)
    p_after = draw_menu(rows_after, w_total, h_after, f_mid)

    pad, head, gap, foot = 26, 62, 40, 56
    W = pad * 2 + p_before.width + gap + p_after.width
    H = head + max(p_before.height, p_after.height) + foot
    canvas = Image.new("RGB", (W, H), (240, 240, 242))
    d = ImageDraw.Draw(canvas)

    y0 = head
    for img, x, title, sub in (
        (p_before, pad, "改  前", "统计面板与计时组粘成一整块"),
        (p_after, pad + p_before.width + gap, "改  后", "统计面板独占（多一条分隔线）"),
    ):
        canvas.paste(img, (x, y0))
        d.text((x, 16), title, font=f_big, fill=(20, 20, 20))
        d.text((x + 92, 23), sub, font=f_small, fill=(150, 60, 60))
        ymark = y0 + int(20 * K)      # 统计面板那一行的下沿
        d.rectangle([x - 5, ymark - 5, x + img.width + 5, ymark + 5],
                    outline=(214, 40, 40), width=3)

    d.text((pad, H - 38),
           "红框处 = 本次新增的分隔线所在行；改前那一行是「打开统计面板」与「隐藏表盘」直接相邻",
           font=f_small, fill=(90, 90, 90))
    d.text((pad, H - 20),
           "（文本 / 行高 / 分隔线位置均读自真实 QMenu 的 actionGeometry，仅字形由 PIL 绘制）",
           font=f_small, fill=(150, 150, 150))
    canvas.save(OUT)
    print("\nsaved %s  %dx%d" % (OUT, W, H))


if __name__ == "__main__":
    main()
