"""把当前代码的托盘菜单离屏渲染成 PNG，并打印"分组结构"。

用途：用户截图里"打开统计面板"和计时组粘成一整块 —— 查证是代码漏了分隔线
还是实例陈旧。结论：离屏 QMenu 加了 ensurePolished()+adjustSize()+popup()
之后**是会正常布局的**（actionGeometry 给出真实行位置），所以可以直接拿它
当"代码真实渲染结果"的基准，去和用户截图逐项对位。
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import heatcore
import overlay
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

OUT = "_menu_render.png"


def main():
    svc = heatcore.HeatService().start()
    app = QApplication(sys.argv)
    dial = overlay.HeatDial(svc)
    menu = dial._menu

    menu.ensurePolished()
    menu.adjustSize()
    print("sizeHint = %dx%d" % (menu.sizeHint().width(), menu.sizeHint().height()))
    print("--- actionGeometry（离屏能否布局）---")
    laid = []
    for a in menu.actions():
        g = menu.actionGeometry(a)
        laid.append((a.text() or "[sep]", g.y(), g.height()))
    for t, y, hh in laid:
        print("  %-22s y=%4d h=%3d" % (t, y, hh))

    # 真正弹出来（离屏也会走布局）+ 抓图
    menu.popup(QPoint(0, 0))
    app.processEvents()
    pm = menu.grab()
    pm.save(OUT)
    print("saved", OUT, pm.width(), "x", pm.height())

    # ---- 分组结构：分隔线把菜单切成几块（几何判定，不看颜色）----
    groups, cur, n_sep = [], [], 0
    for a in menu.actions():
        if a.isSeparator():
            n_sep += 1
            if cur:
                groups.append(cur)
            cur = []
        else:
            cur.append(a.text() or "[sub]")
    if cur:
        groups.append(cur)
    print("\n=== 分组结构（代码里 addSeparator 共 %d 处）===" % n_sep)
    for k, g in enumerate(groups, 1):
        print("  组%d: %s" % (k, " | ".join(g)))
    print("\n判定：")
    print("  打开统计面板 独占一组        : %s"
          % (groups[0] == ["打开统计面板"] if groups else False))
    timing = next((g for g in groups if "倒计时" in g), [])
    print("  计时组 = 倒计时 在 停止计时 之上: %s"
          % (timing == ["倒计时", "停止计时"]))
    cfg_grp = next((g for g in groups if "表盘样式" in g), [])
    print("  隐藏表盘 在 停靠/透明度/表盘样式 组最下面: %s"
          % (cfg_grp[-1] == "隐藏表盘" and "停靠位置" in cfg_grp
             and "透明度" in cfg_grp and "表盘样式" in cfg_grp))


if __name__ == "__main__":
    main()
