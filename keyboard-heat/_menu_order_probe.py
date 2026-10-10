"""离屏 dump 当前代码的真实菜单顺序，确认改对了没。"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import heatcore
import overlay
from PyQt6.QtWidgets import QApplication


def walk(menu, depth=0, out=None):
    if out is None:
        out = []
    for a in menu.actions():
        label = a.text() or ("[separator]" if a.isSeparator() else "[menu:%s]" % (a.menu().title() if a.menu() else "?"))
        out.append(("  " * depth) + label)
        if a.menu() is not None:
            walk(a.menu(), depth + 1, out)
    return out


def main():
    svc = heatcore.HeatService().start()
    app = QApplication(sys.argv)
    dial = overlay.HeatDial(svc)
    lines = walk(dial._menu)
    print("==== 当前代码构建出的菜单顺序 ====")
    for ln in lines:
        print(ln)
    # 关键顺序断言
    titles = [l.strip() for l in lines if not l.strip().startswith("[")]
    try:
        i_open = titles.index("打开统计面板")
        i_hide = titles.index("隐藏表盘")
        i_cd = titles.index("倒计时")
        i_style = titles.index("表盘样式")
    except ValueError:
        print("\n[WARN] 缺少某个标题")
        return
    print("\n==== 关键顺序校验 ====")
    print("打开统计面板(=%d) < 隐藏表盘(=%d): %s" % (i_open, i_hide, i_open < i_hide))
    print("隐藏表盘(=%d) < 倒计时(=%d): %s  (暂停计时在倒计时之上)" % (i_hide, i_cd, i_hide < i_cd))
    print("隐藏表盘(=%d) < 表盘样式(=%d): %s  (已移出表盘样式组)" % (i_hide, i_style, i_hide < i_style))


if __name__ == "__main__":
    main()
