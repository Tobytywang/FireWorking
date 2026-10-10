# -*- coding: utf-8 -*-
"""托盘「单选」菜单回归测试 —— 用户报的「0% 和 100% 前面同时有对号」。

根因是 Qt 一条反直觉的行为：**`setCheckable(True)` 本身不带任何互斥**。
同一个菜单里放几个 checkable action，Qt 不会自动把它们凑成一组，点新的一项时
旧的对号会留着不放。互斥只能靠 `QActionGroup`（exclusive）。实测见第 1 节。

反向验证过（别怀疑这几条断言是空转）：把 `build_choice_menu` 里的
`group.addAction(act)` 注掉，本文件立刻 9 条变红，勾选串是 `0011`、`1010`
这类 —— 和用户看到的「0% 和 100% 同时有对号」完全一致。改回来即全绿。

本文件盯两件事：

  1. **行为**：直接调 `overlay.build_choice_menu`（生产代码，不是复刻），走
     鼠标点击和键盘回车两条真实路径，勾选数必须**恰好 1**，且是刚点那一项。
     来回切换几次也要保持 1。
  2. **源码**：`overlay.py` 里 `setCheckable(True)` 只许出现在
     `build_choice_menu` 内部 —— 谁再手写一组单选、忘了配 QActionGroup，
     这里就红。

跑法：.pyenv\\Scripts\\python.exe _test_tray.py
"""
from __future__ import annotations

import os
import re
import sys
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt6.QtCore import QPoint, Qt                                    # noqa: E402
from PyQt6.QtTest import QTest                                         # noqa: E402
from PyQt6.QtWidgets import QApplication, QMenu, QWidget               # noqa: E402

import overlay                                                         # noqa: E402

OK = 0
BAD = 0


def eq(name, got, want):
    global OK, BAD
    if got == want:
        OK += 1
        print("  [PASS] %-46s %s" % (name, got))
    else:
        BAD += 1
        print("  [FAIL] %-46s got=%r want=%r" % (name, got, want))


def ok(name, cond, detail=""):
    """条件断言。detail 只在失败时打出来，免得日志被数字淹没。"""
    global OK, BAD
    if cond:
        OK += 1
        print("  [PASS] %-46s %s" % (name, detail))
    else:
        BAD += 1
        print("  [FAIL] %-46s %s" % (name, detail))


# ---------------- 工具 ----------------

def make(entries, current, on_pick):
    """按生产代码建一组单选菜单。返回持有引用的元组（别让 parent/group 被 GC）。"""
    parent = QWidget()
    menu = QMenu()
    sub, acts, group = overlay.build_choice_menu(
        parent, menu, "测试", entries, current, on_pick)
    return parent, menu, sub, acts, group


def checks(acts):
    """勾选状态串，如 '0010'。"""
    return "".join("1" if a.isChecked() else "0" for a in acts)


def pump(app, n=6):
    for _ in range(n):
        app.processEvents()


def click(app, sub, act):
    """真实鼠标点击某一项。"""
    sub.popup(QPoint(140, 140))
    pump(app)
    rect = sub.actionGeometry(act)
    QTest.mouseClick(sub, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, rect.center())
    pump(app)
    sub.close()
    pump(app, 4)


def press(app, sub, act):
    """真实键盘回车激活（光标移到该项）。"""
    sub.popup(QPoint(140, 140))
    pump(app)
    sub.setActiveAction(act)
    QTest.keyClick(sub, Qt.Key.Key_Return)
    pump(app)
    sub.close()
    pump(app, 4)


# ---------------- 1. 点击互斥（这是 bug 本体） ----------------

def section_click(app):
    print("\n1. 点击互斥：ALPHA_ENTRIES（透明度 100% / 55% / 28% / 0%）")
    picked = []

    for how, act_fn in (("鼠标点击", click), ("键盘回车", press)):
        for target, want in ((3, "0001"), (0, "1000"), (1, "0100")):
            holder = make(overlay.ALPHA_ENTRIES, 72,
                          lambda v: picked.append(v))
            _p, _m, sub, acts, _g = holder
            act_fn(app, sub, acts[target])
            eq("%s 点 %s" % (how, overlay.ALPHA_ENTRIES[target][0]),
               checks(acts), want)

    # 回调收到的是**内部不透明度**整数（菜单显示的是透明度，值仍是 0~100 的不透明度）。
    eq("回调收到的是内部不透明度整数", picked, [100, 0, 45, 100, 0, 45])


def section_pos(app):
    print("\n2. 位置组：值是字符串，同样必须互斥")
    holder = make(overlay.POSITIONS, "bottom-right", lambda v: None)
    _p, _m, sub, acts, _g = holder
    click(app, sub, acts[0])                      # 左上角（现在排第一）
    eq("点「左上角」后 左上/右上/左下/右下", checks(acts), "1000")
    eq("勾选那一项的文字就是刚点的", acts[0].text(), "左上角")


def section_switch(app):
    print("\n3. 连续来回切换：勾选数一直保持 1")
    holder = make(overlay.ALPHA_ENTRIES, 0, lambda v: None)
    _p, _m, sub, acts, _g = holder
    seq = []
    for i in (3, 0, 2, 3, 1):
        click(app, sub, acts[i])
        seq.append(checks(acts))
    eq("0→100→0→72→100→45 的勾选轨迹", seq,
       ["0001", "1000", "0010", "0001", "0100"])
    ok("每次切换后有且只有一个对号", all(s.count("1") == 1 for s in seq), str(seq))


# ---------------- 4. 回写（配置值是唯一数据源） ----------------

def section_sync():
    print("\n4. sync_choice_checks：按配置值回写勾选")
    holder = make(overlay.ALPHA_ENTRIES, 72, lambda v: None)
    _p, _m, _s, acts, _g = holder

    overlay.sync_choice_checks(acts, overlay.ALPHA_ENTRIES, 45)
    eq("回写到不透明度 45（显示 55%）", checks(acts), "0100")

    overlay.sync_choice_checks(acts, overlay.ALPHA_ENTRIES, 0)
    eq("回写到不透明度 0（显示 100%）", checks(acts), "1000")

    # 配置里出现档位之外的值（手工改过 config.json）：宁可一个都不勾，也不能勾错。
    overlay.sync_choice_checks(acts, overlay.ALPHA_ENTRIES, 33)
    eq("档位外的值 33 → 一个都不勾（不许勾错档）", checks(acts), "0000")

    holder2 = make(overlay.POSITIONS, "bottom-right", lambda v: None)
    acts2 = holder2[3]
    overlay.sync_choice_checks(acts2, overlay.POSITIONS, "top-left")
    eq("位置组同理（值域是字符串，左上=首档→1000）", checks(acts2), "1000")


# ---------------- 4b. 「不透明度」改名「透明度」+ 反相显示 ----------------

def section_alpha_semantics():
    """用户第 8 轮：菜单从「底盘不透明度」改名「底盘透明度」，且要「和 100% 配合上」——
    即 100% 字面义就是**完全透明**。做法是显示值反相，内部 bg_alpha（不透明度）不动。"""
    print("\n4b. 透明度语义：显示值反相、内部不透明度不变")

    eq("标签是透明度（100/55/28/0，从大到小排）",
       [lbl for lbl, _ in overlay.ALPHA_ENTRIES], ["100%", "55%", "28%", "0%"])
    eq("内部值仍是不透明度（0/45/72/100）",
       [v for _, v in overlay.ALPHA_ENTRIES], [0, 45, 72, 100])

    labels = dict((v, lbl) for lbl, v in overlay.ALPHA_ENTRIES)
    # 两头点名：实心(不透明100)↔透明度0；全透明(不透明0)↔透明度100
    eq("不透明度 100（实心）显示为透明度 0%", labels[100], "0%")
    eq("不透明度 0（全透明）显示为透明度 100%", labels[0], "100%")
    eq("透明度 = 100 − 不透明度（逐档都对）",
       [(v, lbl) for lbl, v in overlay.ALPHA_ENTRIES],
       [(0, "100%"), (45, "55%"), (72, "28%"), (100, "0%")])

    # 吸附：配置里是档位外的值也要有对号（不然托盘上一个勾都没有）
    eq("_snap_alpha(33) 吸附到最近档 45", overlay._snap_alpha(33), 45)
    eq("_snap_alpha(90) 吸附到最近档 100", overlay._snap_alpha(90), 100)
    eq("_snap_alpha(72) 本身是档位值 → 不动", overlay._snap_alpha(72), 72)


# ---------------- 5. 源码守卫 ----------------

def fn_body(src, name, indent="    "):
    """抠出一个函数的函数体（到下一条同缩进的 def / 文件尾为止）。"""
    pat = r"\n%sdef %s\(.*?(?=\n%sdef |\nclass |\Z)" % (indent, name, indent)
    m = re.search(pat, src, re.S)
    return m.group(0) if m else ""


def section_source():
    print("\n5. 源码守卫：单选菜单只许从 build_choice_menu 出来")
    src = (HERE / "overlay.py").read_text(encoding="utf-8")

    # 只数**代码**：`act.setCheckable(True)`。docstring 里也提过这句（解释为什么
    # 要 QActionGroup），不带 `act.` 前缀，正好被这个口径排除掉。
    n_raw = src.count("act.setCheckable(True)")
    eq("overlay.py 全文 act.setCheckable(True) 只剩 1 处", n_raw, 1)

    b = fn_body(src, "build_choice_menu", indent="")
    ok("唯一那处在 build_choice_menu 里面",
       b.count("act.setCheckable(True)") == 1)
    ok("build_choice_menu 建了 QActionGroup", "QActionGroup(" in b)
    ok("build_choice_menu 设了 setExclusive(True)", "setExclusive(True)" in b)
    ok("每个 action 都加进了组（互斥就靠这一句）",
       "group.addAction(act)" in b)

    tray = fn_body(src, "_build_tray")
    eq("_build_tray 用 build_choice_menu 建了六组", tray.count("build_choice_menu("), 6)
    ok("_build_tray 里不再有裸的 setCheckable", "setCheckable(" not in tray)

    # 改名守卫：菜单标题是「透明度」，旧的「底盘不透明度 / 底盘透明度」不许再出现。
    ok("_build_tray 菜单标题是「透明度」", "透明度" in tray)
    ok("旧的「底盘透明度」已不在 _build_tray", "底盘透明度" not in tray)
    ok("_build_tray 有「倒计时」子菜单", "倒计时" in tray)
    ok("_build_tray 有「托盘按钮单击效果」子菜单", '"托盘按钮单击效果"' in tray)
    ok("旧的「单击效果」独立标题已移除", '"单击效果"' not in tray)
    ok("_build_tray 有「托盘按钮双击效果」子菜单", '"托盘按钮双击效果"' in tray)
    ok("旧的「双击效果」独立标题已移除", '"双击效果"' not in tray)
    ok("_build_tray 有「托盘按钮右键效果」提示子菜单", '"托盘按钮右键效果"' in tray)
    ok("右键效果唯一项「菜单」默认勾选且禁用（不可更改）",
       "setChecked(True)" in tray and "setEnabled(False)" in tray)
    ok("_build_tray 表盘样式也是子菜单（二选一：篝火 / 数字）", "CAMPFIRE_ENTRIES" in tray)
    ok("_build_tray 表盘样式子菜单走 _set_campfire", "_set_campfire" in tray)
    ok("CAMPFIRE_ENTRIES 两项：篝火 / 表盘",
       [v for _, v in overlay.CAMPFIRE_ENTRIES] == [True, False])
    ok("CAMPFIRE_ENTRIES 标签是「篝火」「数字」",
       [t for t, _ in overlay.CAMPFIRE_ENTRIES] == ["篝火", "数字"])
    ok("_set_campfire 改完会回写勾选", "_sync_tray_checks()" in fn_body(src, "_set_campfire"))
    ok("旧的 _toggle_campfire / _act_campfire 已移除",
       "_toggle_campfire" not in src and "_act_campfire" not in src)
    ok("_build_tray 有「停止计时」顶层动作", "停止计时" in tray)
    ok("_build_tray 倒计时子菜单用 COUNTDOWN_DURATIONS（不含复位档）",
       "COUNTDOWN_DURATIONS" in tray)
    ok("_build_tray 调了 _set_single_click", "_set_single_click" in tray)
    ok("_build_tray 调了 _set_double_click", "_set_double_click" in tray)
    sync = fn_body(src, "_sync_tray_checks")
    ok("_sync_tray_checks 用 _snap_alpha 吸附档位", "_snap_alpha(" in sync)

    for m in ("_set_position", "_set_alpha", "_set_countdown"):
        ok("%s 改完会回写勾选" % m, "_sync_tray_checks()" in fn_body(src, m))
    sc = fn_body(src, "_set_countdown")
    ok("_set_countdown 设置倒计时截止与触发标志",
       "_countdown_deadline" in sc and "_fired" in sc)
    refresh = fn_body(src, "_refresh")
    ok("_refresh 到点把 _fired 置 True", "_fired = True" in refresh)
    sync = fn_body(src, "_sync_tray_checks")
    ok("_sync_tray_checks 七组都走 sync_choice_checks（多屏后多了「显示器」一组）",
       sync.count("sync_choice_checks(") == 7)

    # 菜单分组顺序（上→下）：打开统计面板（单独成组）→ 分隔 →
    # 倒计时 / 停止计时（同组，倒计时在上）→ 分隔 →
    # 停靠位置 / 透明度 / 表盘样式 / 隐藏表盘（隐藏表盘在三者最下面）→ 分隔 →
    # 托盘按钮单击效果 / 托盘按钮双击效果 / 托盘按钮右键效果 → 分隔 → 退出。
    # 用 ASCII 引号包裹的精确标题子串，避免命中注释里的中文（注释不带 ASCII 引号）。
    def pos(t):
        return tray.find('"%s"' % t)
    order = [pos(t) for t in (
        "打开统计面板", "倒计时", "停止计时", "停靠位置",
        "透明度", "表盘样式", "隐藏表盘", "托盘按钮单击效果",
        "托盘按钮双击效果", "托盘按钮右键效果", "退出")]
    ok("_build_tray 各标题都在", all(i >= 0 for i in order))
    ok("菜单顺序符合分组：统计<倒计时<停止计时<停靠<透明度<表盘<隐藏<单击<双击<右键<退出",
       order == sorted(order) and len(set(order)) == 11)
    ok("倒计时 在 停止计时 之上（同组、倒计时项在上）",
       pos("倒计时") < pos("停止计时"))
    ok("隐藏表盘 与 停靠/透明度/表盘样式 同组、且置于三者最下面（表盘样式之下）",
       pos("表盘样式") < pos("隐藏表盘") < pos("托盘按钮单击效果"))
    # 「单独成组」的硬判据不是位置靠前，而是它后面真的有一条分隔线。
    # 只断言位置时，漏掉 addSeparator() 也照样全绿 —— 这正是放走这个 bug 的原因。
    i_rep = tray.find("menu.addAction(act_report)")
    i_sep = tray.find("menu.addSeparator()", i_rep + 1) if i_rep >= 0 else -1
    i_stop = tray.find("act_stop_cd = QAction")
    ok("打开统计面板 后有分隔线（真正单独成组，不与计时组粘连）",
       -1 < i_rep < i_sep < i_stop)
    ok("托盘按钮右键效果 在双击效果之后、退出之前",
       pos("托盘按钮右键效果") > pos("托盘按钮双击效果")
       and pos("托盘按钮右键效果") < pos("退出"))

    # 「显示器」必须插在「停靠位置」**上面**（用户要求）。
    # 注意：这一条只钉住锚点，钉不住最终顺序 —— 顺序由 insertMenu 运行时决定，
    # 源码里「显示器」这四个字压根不在 _build_tray 体内（在 _build_screen_menu 里）。
    # 真正的顺序判据在 _tray_order_probe.py（离屏搭真菜单、读 QMenu.actions()）。
    sbm = fn_body(src, "_build_screen_menu")
    ok("_build_screen_menu 以「停靠位置」为锚点插在它**之前**",
       "insertMenu(pos_sub.menuAction(), sub)" in sbm)
    ok("_build_screen_menu 不再插在「停靠位置」之后（旧的 index(...) + 1）",
       "actions.index(pos_sub.menuAction()) + 1" not in sbm)

    # 倒计时子菜单不再含复位档（已提到外面改名「停止计时」）；时长档反向排成
    # 25/10/5，向上展开让 5 分钟最接近父菜单（用户排序要求）。
    eq("COUNTDOWN_DURATIONS 反向排成 25/10/5（不含复位档）",
       [v for _, v in overlay.COUNTDOWN_DURATIONS], [25, 10, 5])
    eq("COUNTDOWN_DURATIONS 标签反向 25分钟/10分钟/5分钟",
       [lbl for lbl, _ in overlay.COUNTDOWN_DURATIONS],
       ["25分钟", "10分钟", "5分钟"])

    # 隐藏表盘：勾选 = 隐藏窗口（不暂停数据采集），取消 = 显示窗口（替代旧「暂停记录」）。
    hide = fn_body(src, "_toggle_hide_dial")
    ok("有 _toggle_hide_dial（替代旧 _toggle_pause）", "_toggle_hide_dial" in src)
    ok("_toggle_hide_dial 用 setHidden 控制显隐", "setHidden(" in hide)
    ok("_toggle_hide_dial 不再暂停数据采集（无 toggle_pause 调用）",
       "toggle_pause" not in hide)
    ok("旧的 _toggle_pause / _act_pause 已移除",
       "_toggle_pause" not in src and "_act_pause" not in src)

    # 倒计时进行 / 已触发 → 圆环（进度条）改表示倒计时进度，不再表示热度。
    ok("有 _countdown_progress 方法", "def _countdown_progress" in src)
    cp = fn_body(src, "_countdown_progress")
    ok("_countdown_progress 未进入倒计时返回 None", "return None" in cp)
    ok("_countdown_progress 已触发（到点）返回 flash 哨兵", 'return "flash"' in cp)
    ok("_countdown_progress 进行中返回剩余占比（remaining/total）",
       "remaining / total" in cp)
    pe = fn_body(src, "paintEvent")
    ok("paintEvent 在倒计时时把圆环接管为倒计时进度", "_countdown_progress" in pe)
    ok("paintEvent 倒计时弧用 COUNTDOWN_ARC_COLOR", "COUNTDOWN_ARC_COLOR" in pe)

    # 左键单击 / 双击都是快捷操作入口（各自在右键菜单配置动作，都不弹菜单）；
    # 单击走去抖定时器、双击取消它立即执行；右键弹菜单（和左键同套几何）。
    act = fn_body(src, "_on_tray_activated")
    ok("_on_tray_activated 处理左键 Trigger", "ActivationReason.Trigger" in act)
    ok("_on_tray_activated 左键单击走去抖调度（_schedule_single_click）",
       "_schedule_single_click" in act)
    ok("_on_tray_activated 处理右键 Context", "ActivationReason.Context" in act)
    ok("_on_tray_activated 右键弹菜单用 _popup_menu", "_popup_menu" in act)
    ok("左键单击分支仍不弹菜单（Trigger 段无 _popup_menu）",
       "_popup_menu" not in act.split("Context")[0])
    ok("_on_tray_activated 处理双击 DoubleClick 信号",
       "ActivationReason.DoubleClick" in act)
    ok("_on_tray_activated 双击执行 _do_double_click_action",
       "_do_double_click_action" in act)
    ok("_on_tray_activated 双击先取消单击去抖定时器", "_click_timer.stop" in act)
    ok("新增 _do_single_click_action 方法", "def _do_single_click_action" in src)
    ok("新增 _do_double_click_action 方法", "def _do_double_click_action" in src)
    ok("新增 _schedule_single_click 方法", "def _schedule_single_click" in src)
    ok("新增 _popup_menu 方法", "def _popup_menu" in src)
    ok("新增 _set_single_click 方法", "def _set_single_click" in src)
    ok("新增 _set_double_click 方法", "def _set_double_click" in src)
    pm = fn_body(src, "_popup_menu")
    ok("_popup_menu 改用托盘图标几何锚定（QPoint 由 geometry 算出）",
       "geometry()" in pm and "QPoint(" in pm)
    ok("_popup_menu 拿不到图标几何时仍退回光标位置兜底", "QCursor.pos()" in pm)
    ok("_popup_menu 按屏幕边缘决定向上/向下翻", "sg.bottom()" in pm and "sg.top()" in pm)


def section_countdown(app):
    print("\n6. 倒计时组（5 / 10 / 25 分钟 / 关闭）")
    eq("标签顺序 5分钟/10分钟/25分钟/关闭",
       [lbl for lbl, _ in overlay.COUNTDOWN_ENTRIES],
       ["5分钟", "10分钟", "25分钟", "关闭"])
    eq("值 5/10/25/0", [v for _, v in overlay.COUNTDOWN_ENTRIES], [5, 10, 25, 0])

    holder = make(overlay.COUNTDOWN_ENTRIES, 0, lambda v: None)
    _p, _m, sub, acts, _g = holder
    click(app, sub, acts[1])                      # 10分钟（索引 1）
    eq("点 10分钟 → 0100", checks(acts), "0100")
    eq("勾选那一项的文字就是刚点的", acts[1].text(), "10分钟")

    overlay.sync_choice_checks(acts, overlay.COUNTDOWN_ENTRIES, 5)
    eq("回写 5（索引 0）→ 1000", checks(acts), "1000")
    overlay.sync_choice_checks(acts, overlay.COUNTDOWN_ENTRIES, 25)
    eq("回写 25（索引 2）→ 0010", checks(acts), "0010")
    overlay.sync_choice_checks(acts, overlay.COUNTDOWN_ENTRIES, 0)
    eq("回写 关闭（索引 3）→ 0001", checks(acts), "0001")


def section_countdown_progress():
    """_countdown_progress 行为：倒计时是**剩余占比**（满圈 1.0 → 空 0.0），
    到点（_fired）返回 "flash" 哨兵。不构造完整 HeatDial（要 QApplication +
    HeatService），只把方法绑到一个最小命名空间上跑。"""
    print("\n7. _countdown_progress 行为：剩余占比 1.0→0.0 + 到点 flash")
    ns = types.SimpleNamespace(
        _countdown_min=0, _countdown_deadline=None, _fired=False)
    fn = overlay.HeatDial._countdown_progress.__get__(ns, overlay.HeatDial)

    eq("未进入倒计时（min=0） → None", fn(), None)

    ns._countdown_min = 10                              # 选 10 分钟档
    ns._countdown_deadline = time.time() + 10 * 60.0    # 满格剩余
    eq("刚选时长 → 1.0（满圈）", fn(), 1.0)
    ns._countdown_deadline = time.time() + 5 * 60.0     # 半程剩余
    eq("半程 → 0.5", fn(), 0.5)
    ns._countdown_deadline = time.time() + 0.0          # 到点（尚未 fired）
    eq("到点未 fired → 0.0（空）", fn(), 0.0)

    ns._fired = True
    eq("已触发（fired） → flash 哨兵", fn(), "flash")

    ns._countdown_min = 0                               # 选「关闭」复位
    ns._fired = False
    eq("关闭复位 → None", fn(), None)


def section_singleclk():
    """单击效果：SINGLECLK_ENTRIES 配置 + _do_single_click_action 的分发逻辑。"""
    print("\n8. 单击效果（左键单击托盘图标时执行，从 4 个效果里选）")
    eq("SINGLECLK_ENTRIES 四个选项（统计第一、时间项反向、去前缀）",
       [lbl for lbl, _ in overlay.SINGLECLK_ENTRIES],
       ["打开统计面板", "倒计时 25 分钟",
        "倒计时 10 分钟", "倒计时 5 分钟"])
    eq("SINGLECLK_ENTRIES 值 open_stats/cd25/cd10/cd5（时间项反向）",
       [v for _, v in overlay.SINGLECLK_ENTRIES],
       ["open_stats", "cd25", "cd10", "cd5"])

    # _do_single_click_action 的分发：绑到最小命名空间，stub 掉两个副作用。
    calls = []
    ns = types.SimpleNamespace(
        _overlay_cfg={"tray_single_click": "open_stats"},
        _set_countdown=lambda m, src="menu": calls.append(("cd", m, src)),
        _open_report=lambda: calls.append(("report",)))
    fn = overlay.HeatDial._do_single_click_action.__get__(ns, overlay.HeatDial)

    ns._overlay_cfg = {"tray_single_click": "open_stats"}
    calls.clear(); fn()
    eq("open_stats → 打开统计面板", calls, [("report",)])

    ns._overlay_cfg = {"tray_single_click": "cd5"}
    calls.clear(); fn()
    eq("cd5 → 倒计时 5 分钟（来源 single_click）", calls, [("cd", 5, "single_click")])

    ns._overlay_cfg = {"tray_single_click": "cd10"}
    calls.clear(); fn()
    eq("cd10 → 倒计时 10 分钟（来源 single_click）", calls, [("cd", 10, "single_click")])

    ns._overlay_cfg = {"tray_single_click": "cd25"}
    calls.clear(); fn()
    eq("cd25 → 倒计时 25 分钟（来源 single_click）", calls, [("cd", 25, "single_click")])

    # 未知值回退到打开统计面板（防御性）
    ns._overlay_cfg = {"tray_single_click": "???"}
    calls.clear(); fn()
    eq("未知值回退 → 打开统计面板", calls, [("report",)])


def section_doubleclk():
    """双击效果：和单击共用 SINGLECLK_ENTRIES 选项，分发到 double_click 来源。"""
    print("\n9. 双击效果（左键双击托盘图标时执行，从 4 个效果里选）")
    eq("双击效果复用同一份选项（时间项反向）",
       [v for _, v in overlay.SINGLECLK_ENTRIES],
       ["open_stats", "cd25", "cd10", "cd5"])

    calls = []
    ns = types.SimpleNamespace(
        _overlay_cfg={"tray_double_click": "open_stats"},
        _set_countdown=lambda m, src="menu": calls.append(("cd", m, src)),
        _open_report=lambda: calls.append(("report",)))
    fn = overlay.HeatDial._do_double_click_action.__get__(ns, overlay.HeatDial)

    ns._overlay_cfg = {"tray_double_click": "open_stats"}
    calls.clear(); fn()
    eq("open_stats → 打开统计面板", calls, [("report",)])

    ns._overlay_cfg = {"tray_double_click": "cd5"}
    calls.clear(); fn()
    eq("cd5 → 倒计时 5 分钟（来源 double_click）", calls, [("cd", 5, "double_click")])

    ns._overlay_cfg = {"tray_double_click": "cd10"}
    calls.clear(); fn()
    eq("cd10 → 倒计时 10 分钟（来源 double_click）", calls, [("cd", 10, "double_click")])

    ns._overlay_cfg = {"tray_double_click": "cd25"}
    calls.clear(); fn()
    eq("cd25 → 倒计时 25 分钟（来源 double_click）", calls, [("cd", 25, "double_click")])

    ns._overlay_cfg = {"tray_double_click": "???"}
    calls.clear(); fn()
    eq("未知值回退 → 打开统计面板", calls, [("report",)])


def section_submenu(app):
    print("\n9. 子菜单落点：右侧弹出 + 向上展开")
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QAction

    # —— 纯函数分支（离屏下 QMenu 不布局，端到端验不出垂直落点，所以直接测算法）——
    sg = QRect(0, 0, 800, 800)
    pg = QRect(500, 400, 160, 300)                 # 父菜单底边 699

    p = overlay.submenu_pos(pg, 600, 620, 200, 80, sg)
    eq("① 向上展开：y = 父项底边 - 子菜单高", p.y(), 540)
    eq("① 底边正好落在父项底边", p.y() + 80, 620)

    pg2 = QRect(500, 0, 160, 60)                   # 父项贴屏幕顶
    p2 = overlay.submenu_pos(pg2, 40, 60, 200, 300, sg)
    eq("② 上方放不下 → 退回向下（y0 = 父项顶边）", p2.y(), 40)

    pg3 = QRect(300, 400, 60, 100)                 # 右边留得下 200 宽
    p3 = overlay.submenu_pos(pg3, 420, 440, 200, 80, sg)
    eq("③ 右边有空间时钉父菜单右缘", p3.x(), 359)
    eq("③ 同时仍向上展开", p3.y(), 360)

    pg4 = QRect(700, 400, 60, 100)                 # 贴右缘，200 宽放不下
    p4 = overlay.submenu_pos(pg4, 420, 440, 200, 80, sg)
    eq("④ 右边放不下 → 退回父菜单左缘", p4.x(), 500)

    pg5 = QRect(50, 400, 700, 100)                 # 父菜单很宽，左右都放不下
    p5 = overlay.submenu_pos(pg5, 420, 440, 200, 80, sg)
    eq("⑤ 左右都放不下 → 夹到屏幕左缘", p5.x(), 0)

    # —— 端到端：真实 QMenu 展开子菜单（走 Qt 内部 setActiveAction 那条路）——
    scr = QApplication.primaryScreen().geometry()

    def build(plain):
        """造一个父菜单 + 4 项子菜单；plain=True 用普通 QMenu 当对照组。"""
        h = QWidget()
        m = QMenu()
        if plain:
            s = QMenu("单击效果", m)
            m.addMenu(s)
            for i in range(len(overlay.SINGLECLK_ENTRIES)):
                a = QAction("项%d" % i, m)
                a.setCheckable(True)
                s.addAction(a)
        else:
            s, _a, _g = overlay.build_choice_menu(
                h, m, "单击效果", overlay.SINGLECLK_ENTRIES, "open_stats",
                lambda v: None)
        for _ in range(10):
            m.addAction(QAction("填充", m))
        return h, m, s

    def open_sub(m, s):
        m.popup(QPoint(scr.right() - 280, scr.bottom() - 60))
        pump(app)
        m.setActiveAction(s.menuAction())
        pump(app)
        return s.geometry()

    holder, menu, sub = build(plain=False)
    ok("build_choice_menu 给子菜单挂了 _parent_menu",
       getattr(sub, "_parent_menu", None) is menu)
    g = open_sub(menu, sub)
    mrect = menu.geometry()
    ok("端到端：子菜单底边不越过父菜单底边（向上展开）",
       g.bottom() <= mrect.bottom() + 1,
       "sub.bottom=%d parent.bottom=%d" % (g.bottom(), mrect.bottom()))
    ok("端到端：子菜单整体落在屏幕内",
       g.top() >= scr.top() and g.bottom() <= scr.bottom())

    # 差分对照：普通 QMenu 走 Qt 默认（从父项往下铺），SubMenuRight 应明显更靠上。
    # 这条是「守卫被跳过」那个真实 bug 的探针：一旦 showEvent 又拿不到父菜单提前
    # return，落点就退回 Qt 默认，差分立刻消失。
    h2, m2, plain = build(plain=True)
    y_plain = open_sub(m2, plain).y()
    y_ours = g.y()
    ok("差分：SubMenuRight 比普通 QMenu（默认向下）更靠上",
       y_ours < y_plain, "ours=%d plain=%d" % (y_ours, y_plain))

    for w in (sub, plain):
        w.close()
    for m in (menu, m2):
        m.close()
    pump(app, 4)

    # —— 源码守卫 ——
    src = (HERE / "overlay.py").read_text(encoding="utf-8")
    se = fn_body(src, "showEvent")
    ok("showEvent 用显式 _parent_menu（QMenu 子菜单没有父级引用）",
       "_parent_menu" in se)
    ok("showEvent 调 submenu_pos 定位", "submenu_pos(" in se)
    ok("SubMenuRight 已注释说明向上展开", "向上展开" in src)


def main():
    app = QApplication(sys.argv)
    print("=" * 72)
    print("托盘单选菜单测试")
    print("=" * 72)
    section_click(app)
    section_pos(app)
    section_switch(app)
    section_sync()
    section_alpha_semantics()
    section_source()
    section_countdown(app)
    section_countdown_progress()
    section_singleclk()
    section_doubleclk()
    section_submenu(app)
    print("\n结果：%d 通过 / %d 失败" % (OK, BAD))
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
