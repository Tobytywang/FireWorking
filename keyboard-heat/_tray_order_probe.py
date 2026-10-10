# -*- coding: utf-8 -*-
"""托盘菜单**运行时顺序**探针 —— 盯「显示器」排在哪一位。

为什么不能用源码检查代替：菜单顺序不是源码里的书写顺序决定的。`_build_screen_menu`
先 `addMenu`（append 到末尾），再 `insertMenu(锚点, sub)` 把它挪到「停靠位置」的
前面/后面。源码文本里 `显示器` 和 `停靠位置` 谁先出现，跟用户看到的顺序没关系 ——
所以判据必须落在 **QMenu.actions() 的真顺序**上。

又因为「显示器」只在**多屏**才挂出，本探针在单屏环境下会把 `QApplication.screens`
补成两块（只影响枚举数量，走的还是生产代码 `_build_screen_menu`），否则这个子菜单
根本不出场、判据会变成空转。

跑法：  .pyenv\\Scripts\\python.exe _tray_order_probe.py
反向验证：.pyenv\\Scripts\\python.exe _tray_order_probe.py --legacy
          —— 把「显示器」按**旧实现**（插在停靠位置之后）重新排一遍，判据必须报红。
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt6.QtWidgets import QApplication, QWidget          # noqa: E402

import overlay                                              # noqa: E402

OK = 0
BAD = 0

# 期望的运行时顺序（上→下）。分隔线不参与，单独查。
EXPECTED = [
    "打开统计面板",
    "倒计时",
    "停止计时",
    "显示器",          # ← 本次要求：排在「停靠位置」上面
    "停靠位置",
    "透明度",
    "表盘样式",
    "隐藏表盘",
    "托盘按钮单击效果",
    "托盘按钮双击效果",
    "托盘按钮右键效果",
    "退出",
]
# 旧顺序（反向验证用）：显示器 在 停靠位置 之后
LEGACY = [
    "打开统计面板",
    "倒计时",
    "停止计时",
    "停靠位置",
    "显示器",
    "透明度",
    "表盘样式",
    "隐藏表盘",
    "托盘按钮单击效果",
    "托盘按钮双击效果",
    "托盘按钮右键效果",
    "退出",
]


def ok(name, cond, detail=""):
    global OK, BAD
    if cond:
        OK += 1
        print("  [PASS] %s" % name)
    else:
        BAD += 1
        print("  [FAIL] %s   %s" % (name, detail))


class _Sig:
    def connect(self, *a, **k):
        pass


class _FakeTray:
    """替掉 QSystemTrayIcon：跑探针不想在托盘里留一个图标。其余属性生产代码没用到。"""

    def __init__(self, *a, **k):
        self.activated = _Sig()

    def setToolTip(self, *a):
        pass

    def show(self):
        pass


class _StubDial(overlay.HeatDial):
    """只为调 `_build_tray` 而生的壳：跑 QWidget 的构造（C++ 对象要建），
    跳过 HeatDial.__init__ 的重活（定时器 / 图片预载 / 热键 / 窗口落位）。
    方法全部继承自真 HeatDial —— 探针走的就是生产代码，不是复刻。"""

    def __init__(self):
        QWidget.__init__(self)


def build_menu(force_multi=True):
    """用**真实**的 HeatDial._build_tray 把右键菜单搭出来。"""
    if force_multi and len(QApplication.screens()) < 2:
        first = QApplication.screens()[0] if QApplication.screens() else QApplication.primaryScreen()
        fake = [first, first]
        # 只改枚举数量：装的仍是真 QScreen，_build_screen_menu 里的 primaryScreen()
        # 比较、entries 生成、insertMenu 落位全部照生产代码走。
        QApplication.screens = staticmethod(lambda: list(fake))

    overlay.QSystemTrayIcon = _FakeTray

    d = _StubDial()
    d._service = types.SimpleNamespace(config={})
    d._overlay_cfg = {
        "position": "bottom-right",
        "bg_alpha": 0.72,
        "screen": 0,
        "tray_single_click": "open_stats",
        "tray_double_click": "open_stats",
    }
    d._countdown_min = 25
    d._campfire = True
    d._build_tray()
    return d, d._menu


def labels_of(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def dump(menu, title):
    print("\n%s" % title)
    for a in menu.actions():
        if a.isSeparator():
            print("    ──────────────── (分隔线)")
        elif a.menu() is not None:
            sub = " / ".join(x.text() for x in a.menu().actions())
            print("    %-14s >  %s" % (a.text(), sub))
        else:
            print("    %s" % a.text())


def main():
    app = QApplication(sys.argv)          # noqa: F841
    legacy = "--legacy" in sys.argv

    print("=" * 72)
    print("托盘菜单顺序探针%s" % ("（反向验证：按旧实现排一遍）" if legacy else ""))
    print("=" * 72)
    print("  枚举到的显示器数量（真实）=%d" % len(QApplication.screens()))

    d, menu = build_menu()
    print("  本探针使用的显示器数量（多屏判定用）=%d" % len(QApplication.screens()))
    lab = labels_of(menu)

    if legacy:
        # 反向验证：把「显示器」按旧实现挪到「停靠位置」**之后**，判据必须报红。
        # 只动真 QMenu 的真 action，不重写生产方法。
        acts = menu.actions()
        i_pos = lab.index("停靠位置")
        screen_act = [a for a in acts if a.menu() is not None and a.text() == "显示器"][0]
        menu.insertMenu(acts[acts.index([a for a in acts if a.text() == "停靠位置"][0]) + 1],
                        screen_act.menu())
        lab = labels_of(menu)

    dump(menu, "  实际运行时顺序：")

    ok("菜单顺序 == 要求顺序（显示器 紧挨在 停靠位置 上面）",
       lab == EXPECTED, "got=%r" % (lab,))
    if legacy:
        # 反向验证的**前提**：注入出来的确实是旧形态（不是随便乱排），否则下面的
        # 报红证明不了判据能抓「显示器 掉到停靠位置下面」这个缺陷。
        ok("（反向验证前提）注入后的顺序 == 旧实现形态", lab == LEGACY,
           "got=%r" % (lab,))
    ok("「显示器」紧挨在「停靠位置」上面",
       lab.index("显示器") == lab.index("停靠位置") - 1,
       "显示器@%d 停靠位置@%d" % (lab.index("显示器"), lab.index("停靠位置")))
    ok("「显示器」是位置设置组的第一项（分隔线之后第一个）",
       lab[lab.index("显示器") - 1] == "停止计时",
       "显示器 前面是 %r" % lab[lab.index("显示器") - 1])
    ok("位置设置组其余顺序未被打乱（透明度<表盘样式<隐藏表盘）",
       lab.index("停靠位置") < lab.index("透明度") < lab.index("表盘样式") < lab.index("隐藏表盘"))
    ok("隐藏表盘 仍是该组最后一项（后面紧跟托盘按钮效果）",
       lab.index("隐藏表盘") + 1 == lab.index("托盘按钮单击效果"))
    ok("分隔线仍是 4 条，且第一条仍在「打开统计面板」之后",
       sum(1 for a in menu.actions() if a.isSeparator()) == 4
       and menu.actions()[1].isSeparator())

    # 「显示器」子菜单内容（多屏）：顺序 + 主屏标记。
    # 注意假屏前提：本机单屏，补出来的两块指向**同一个** QScreen，所以两项都会带
    # 「（主屏）」。这不是生产缺陷 —— 真双屏下只有索引 0 那一块带标记。因此这里
    # 比的是剥掉标记后的序号，标记单独查一条。
    scr_act = [a for a in menu.actions() if a.menu() is not None and a.text() == "显示器"][0]
    items = [x.text() for x in scr_act.menu().actions()]
    ok("「显示器」子菜单项 = 显示器 1 / 显示器 2（序号与索引一致）",
       [t.replace("（主屏）", "") for t in items] == ["显示器 1", "显示器 2"],
       "got=%r" % (items,))
    ok("主屏标记挂在索引 0 那一项上",
       "（主屏）" in items[0], "got=%r" % (items,))
    ok("「显示器」子菜单当前勾选的是配置里的 screen=0",
       [x.isChecked() for x in scr_act.menu().actions()] == [True, False])

    menu.close()
    d.close()
    print("\n结果：%d 通过 / %d 失败" % (OK, BAD))
    if legacy:
        print("（反向验证：上面应当**有失败**才是对的 —— 全绿说明判据没在盯顺序）")
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
