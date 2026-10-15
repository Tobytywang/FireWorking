"""篝火悬浮窗 + 系统托盘控制。

"存在感为零"靠这一组窗口标志实现，缺一个效果就破：
    FramelessWindowHint        无边框
    WindowStaysOnTopHint       永远置顶
    Tool                       不进任务栏、不占 Alt+Tab
    WindowTransparentForInput  鼠标点击/滚轮全部穿透到下层窗口  ← 核心
    WindowDoesNotAcceptFocus   点到它也不会抢走当前窗口的焦点
    WA_TranslucentBackground   四角真透明，不是一个黑色方块

热度有两种视觉表达，`overlay.campfire` 决定用哪种：
    campfire=true（默认）  盘中央是一簇篝火 —— 火苗大小和颜色都由热度驱动，
                          配合外圈的圆环做精确读数。火焰的造型与配色见 flame.py。
    campfire=false        数字仪表盘 —— 中心是「活跃/分」大数字加键/鼠分解。

两个都保留是有意的：火堆直觉但没有数字，数字精确但冷冰冰，用户可以按心情切。
托盘菜单里加了一项「篝火 / 数字」切换，写回 config.json。
"""

from __future__ import annotations

import ctypes
import math
import os
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import (QAction, QActionGroup, QColor, QCursor, QFont, QIcon,
                         QPainter, QPainterPath, QPen, QPixmap)
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from heatcore import (
    HeatService,
    cfg_get,
    cfg_set,
    claim_single_instance,
    heat_rgb,
    log_countdown,
    notify_already_running,
    save_config,
)
import flame

START_DEG = 220.0          # 弧起点角度，左下 7 点半方向
SWEEP_DEG = 260.0          # 顺时针扫过的角度，缺口留在正下方

# 开屏动画：底盘全不透明，圆环扫一圈，同时火苗从零"点燃"到当前热度。
# 存在的意义是回答"我到底起来没有" —— 之前是静默出现，深色桌面上根本发现不了。
BOOT_SWEEP_SECONDS = 1.4
IDLE_ARC_DEG = 2.5         # 完全空闲时保留的一小段弧，让表盘位置随时可见

# 文字光晕的 8 个偏移方向（Chebyshev 距离 1）→ 给字形描一圈 1px 的边。
_HALO_OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1),
                (-1, -1), (1, -1), (-1, 1), (1, 1))

# 早先 rim/track 都用了较高的 alpha，理由是"深色圆盘叠在深色终端上时，边框是唯一
# 能把轮廓交代清楚的东西，太淡就整块糊进背景"。这条理由现在只对 track 成立 ——
# **rim（底盘描边）已按用户要求整体去掉**：那是一条 2px 的细环，正压在圆盘最外沿，
# 实测 Δlum 能到 ±100 以上（dark 亮线 / light 暗线），是一圈比火还抢眼的白/黑线。
# 去掉后轮廓改由盘面自身与桌面的色差交代。
#
# **track 必须是 alpha=255 的定色**（上一轮修）。它原来是半透明白/黑，最终亮度
# 会跟着桌面漂：浅色桌面 + α=72% 时轨道能亮到 134，而热度色阶的低段（冷蓝→
# 青绿→草绿）亮度**恒定在 141~150**（等亮度变色相是刻意的），两个一撞，低热度
# 的弧就跟轨道糊成一片 —— 用户报的"低热度时进度条里的绿色和背景混在一起"就是
# 这个。改成定色后"弧 − 轨道"的亮度差在所有不透明度、所有桌面下都恒定：
#     dark  弧 141~150  vs 轨道 81  → +60 ~ +67
#     light 弧 141~150  vs 轨道 199 → −58 ~ −49
# 取值与 Tk 版 overlay_tk.py 的 THEMES **逐位相同**（#4A5261 / #C2C7D1）——
# Tk 版的轨道一直就是不透明定色，所以它没这个毛病；两边对齐后观感也不再分叉。
# 取舍：深色底下轨道比原来（等效 91）略暗一点；浅色底 + α≈72% 时轨道会贴近
# 底盘（那时底盘自己也漂到中灰 84）。弧是主角、轨道是配角，这样换是划算的。
# 逐组合验证与对照图：`_arc_contrast_probe.py` → `_arc_contrast.png`。
#
# **`track_edge`：圆环外沿的一条定色描边**（用户报"透明度 72 的时候，进度条的底色
# 和圆盘背景底色区分度太低"，并建议把去掉的那圈白色边沿挪到进度条边框上）。
# 轨道定色只解决了"弧 vs 轨道"，没解决"**轨道 vs 底盘**"—— 底盘是半透明的，
# 随桌面漂：dark 主题 α=72% 撞浅色桌面时底盘到 lum 84.8，和轨道（81.4）几乎重合
# （实测 Δlum −3.9 / ΔRGB 10.7，图上就是一块均匀的灰盘）；light 主题 α=72% 撞
# 深/中灰桌面同理（Δlum +8.3 / −1.6）。给环的外沿描一条线，进度条就有了硬边界。
# 取值原则和 rim 一样（暗盘配亮线、亮盘配暗线），这次是**定色**（颜色不随桌面自适应
# —— 自适应色才是漂的那个）。逐组合实测与对照图：`_ring_edge_probe.py`。
#
# **线的透明度与底盘反相**（用户第 7 轮）：`flame.track_edge_alpha(bg_alpha)`
# = `1 − bg_alpha`。底盘不透明度 100%（盘面实心、它自己就和轨道差 54）时线完全消失，
# 底盘 0%（盘面全透、环带直接压在桌面上）时线画满。
# 代价说清楚：α 居中那几档线是半透明的，会和底盘一起漂 —— 这是**故意的**，
# 因为"盘面自己够不够分得开"与"线够不够分得开"此消彼长，取两者较大的那个，
# 边界就始终可辨（`_edge_alpha_probe.py` 逐档量了这个 max）。
# 逐档实测见 `_edge_alpha_probe.py` → `_edge_alpha_probe.png`。
THEMES = {
    "dark": {
        "plate": (24, 27, 35),
        "track": (74, 82, 97),          # #4A5261，不透明（见上）
        "track_edge": (196, 203, 216),  # #C4CBD8，环外沿描边（见上）
        "text": (246, 247, 251),
        "muted": (169, 176, 192),
        # 文字描边光晕：和「text」反相（深底配亮字 → 暗色光晕）。底盘半透明甚至
        # 全透明时，文字不再有可靠底色，这道光晕是文字在**任何**桌面/任何透明度下
        # 都能被看清的兜底 —— 见 _text_read_probe.py（45% 与 0% 两档逐桌面量过）。
        "text_halo": (8, 10, 16),
        # 数字模式的**中央暗底**（盘芯）。和篝火模式的灶膛同色（= CAMP_PIT），
        # 这样两种模式切来切去，盘中央那块深色圆盘位置/颜色都不变，只有内容
        # （火 ⇄ 数字）在换 —— 否则 100% 透明度下，篝火有一块深色灶膛、数字
        # 却悬在桌面上，两种模式看着割裂。
        "center_bg": (14, 12, 17),
    },
    "light": {
        "plate": (252, 252, 254),
        "track": (194, 199, 209),       # #C2C7D1，不透明（见上）
        "track_edge": (95, 102, 116),   # #5F6674，环外沿描边（见上）
        "text": (26, 28, 34),
        "muted": (95, 102, 116),
        "text_halo": (255, 255, 255),   # 浅底配暗字 → 亮色光晕
        # 数字模式的中央底：light 主题的文字是**深色**，中央底必须也是浅色，
        # 否则暗字糊进深底。所以它不能和篝火的深色灶膛同色（灶膛永远是深的，
        # 火是夜里的东西）——这里只保证"有底"，颜色随主题走。
        "center_bg": (236, 238, 243),
    },
}

STATE_LABEL = {
    "typing": "输出中",
    "pointing": "操作中",     # 只动鼠标、没打字
    "pause": "停顿",
    "idle": "空闲",
    "paused": "已暂停",
}

# ---- 篝火模式的常量 ----
# （热度→火苗的映射规则在 flame.fire_heat，两版界面共用）

# 火必须有一块暗底才看得见：光晕是加法混合的，叠在浅色底盘上会被冲成一片白。
# 所以篝火模式在盘内单独铺一层"灶膛"，颜色跟 theme 无关 —— 火就是夜里的东西。
CAMP_PIT = (14, 12, 17)
# 灶膛在**任何**桌面底色上都必须够暗 —— 它不是装饰，是火赖以被看见的那块底。
#
# 早先取 96（38% 不透明），只在深色桌面上验过：那时 rgb(14,12,17) 叠在深色壁纸上
# 就是个坑，没问题。但浅色桌面上它**反过来**：白桌面有 62% 透上来，把灶膛冲成
# rgb(164,164,165) 的**中灰**；而空闲火焰 rgb(189,86,0) 的亮度只有 (189+86+0)/3 = 92，
# 比这块灰底还暗 —— 整簇火读起来就是"发闷、不亮、灰蒙蒙"。光晕又是加法混合的，
# 叠在亮底上只会更白，等于白画。
#
# 实测（_backdrop_probe.py：离屏渲染 → 合成到抓下来的真实白底桌面 → 采样）：
#     alpha  96 → 底 rgb(164,164,165)，火-底亮度差 −77（火比底还暗）
#     alpha 150 → 底 rgb(113,112,115)，−27
#     alpha 200 → 底 rgb(66, 64, 68)， +13（刚翻正）
#     alpha 232 → 底 rgb(36, 34, 38)， +43   ← 取这档
#     alpha 255 → 底 rgb(14, 12, 17)， +64
# 232 在白底上已是深炭色，同时保留 9% 的背景渗透 —— 深色桌面上不会比周围更黑，
# 不会变成一个突兀的纯黑洞。Tk 版没有逐元素 alpha，灶膛本来就是实心 (14,12,17)
# （见 overlay_tk.CAMP_PIT_RGB），两版的灶膛观感在这个值上基本对齐。
CAMP_PIT_MIN_ALPHA = 232

# 中心大数字的单位。鼠标活动已被折算成等效击键并进同一个热度，所以再叫 "KPM"
# 就不准确了 —— 改叫「活跃/分」，分母仍是 60 秒。
HEAT_UNIT = "活跃/分"


def split_text(kpm_keys, kpm_mouse):
    """底部的键/鼠分解。为 0 的那一路不显示，空闲时才退回完整的 "键 0 · 鼠 0"。

    不显示而非常显 0，是因为鼠标静止时屏幕上「鼠 0」是个噪声 —— 而这一行的
    价值恰恰在于回答"现在这个热度是敲出来的还是划出来的"。
    """
    if kpm_keys <= 0 and kpm_mouse <= 0:
        return "键 0 · 鼠 0"
    parts = []
    if kpm_keys > 0:
        parts.append("键 %d" % kpm_keys)
    if kpm_mouse > 0:
        parts.append("鼠 %d" % kpm_mouse)
    return " · ".join(parts)

POSITIONS = (
    ("左上角", "top-left"),
    ("右上角", "top-right"),
    ("左下角", "bottom-left"),
    ("右下角", "bottom-right"),
)

# 托盘里这组的**显示名是「透明度」**，但值和回调仍是内部的「不透明度」(bg_alpha)：
# 透明度% = 100 − 不透明度%。这样「100%」字面义就是完全透明（和 100% 配合直观），
# 内部存的和传给 _set_alpha 的依旧是 0~1 的不透明度，渲染逻辑一个字都不用动。
# 档位按「透明度」从大到小排（用户第 14+ 轮）：全透明(100%) → 45%不透明(55%)
# → 72%不透明(28%) → 实心(0%)。四个值和原来的 0/28/55/100 完全一致，只是反着列。
ALPHA_ENTRIES = [("100%", 0), ("55%", 45), ("28%", 72), ("0%", 100)]

# 倒计时可选档（含「关闭」复位档）。Qt 用 COUNTDOWN_DURATIONS（去掉关闭）做子菜单；
# Tk 热键循环仍用本表（0 档当关）。两个常量分开、互不影响。
# —— 选了某个时长就倒计时，到点后触发提示（篝火呼吸 / 数字「时间到」）；选「关闭」
# 清除倒计时与已触发的提示。不写盘：一次性定时器，重启归零。
COUNTDOWN_ENTRIES = [("5分钟", 5), ("10分钟", 10), ("25分钟", 25), ("关闭", 0)]

# 倒计时可选时长（不含「关闭」）：「关闭」被提到子菜单外面、改名「停止计时」做成一个
# 顶层动作（见 _build_tray / _stop_countdown）。这里只放真正会开始倒计时的时长，供
# Qt 版「倒计时」子菜单与勾选回写用。Tk 版仍直接用 COUNTDOWN_ENTRIES（热键循环需要
# 那个 0 档当「关」），所以两个常量分开、互不影响。
# 子菜单向上展开（最后一项离父菜单行最近），把最常用的 5 分钟放最后，让短时长
# 更贴近父菜单（用户排序要求）。不含「关闭」（已提到外面改名「停止计时」）。
COUNTDOWN_DURATIONS = [("25分钟", 25), ("10分钟", 10), ("5分钟", 5)]

# 单击 / 双击托盘图标时各自执行什么（都不弹菜单），做成一个单选组，两组共用
# 同一份选项。写盘，默认都打开统计面板。这两个就是托盘图标的两种快捷操作入口。
SINGLECLK_ENTRIES = [
    ("打开统计面板", "open_stats"),
    ("倒计时 25 分钟", "cd25"),
    ("倒计时 10 分钟", "cd10"),
    ("倒计时 5 分钟", "cd5"),
]

# 表盘样式子菜单：二选一（篝火 ⇄ 表盘）。值用布尔（True=篝火，False=表盘）。
# 采集和热度是同一套，切换的只是渲染；写回 config 的 "campfire" 键。
CAMPFIRE_ENTRIES = [("篝火", True), ("数字", False)]

# 「鼠标悬停时隐藏表盘」的档位。**默认「关」** —— 不改变既有行为，用户主动开启。
#   off：始终显示（默认）
#   on ：鼠标一进入表盘就隐藏，移开后自动恢复
#做成**单选**而不是 checkable 开关，是为了和旁边「表盘样式」「透明度」等保持同一种
# 交互（build_choice_menu 统一管互斥与勾选回写），也便于以后加中间档（如「淡化」）。
HOVER_ENTRIES = [("关", "off"), ("悬停时隐藏", "on")]

# 单击去抖阈值：单击后等这么久才执行，给双击留出识别窗口；期间来双击就取消单击、
# 改执行双击动作。Windows 默认双击阈值约 500ms，取一半稍小；对快捷键（开面板 /
# 开始倒计时）这点延迟几乎无感，却能避免双击被拆成两次单击触发。
SINGLE_CLICK_DELAY_MS = 220

# 倒计时结束后的「呼吸」效果参数（篝火模式在小火/大火间往复）。
COUNTDOWN_BREATHE_PERIOD = 2.6    # 一个呼吸周期的秒数
COUNTDOWN_FIRE_LOW = 0.16         # 小火（低热度）
COUNTDOWN_FIRE_HIGH = 0.95        # 大火（高热度）

# 倒计时进行 / 已触发期间，圆环（进度条）改表示倒计时进度，用这个固定色，
# 和「热度暖色」「暂停琥珀色」都区分开，一眼能看出是计时而不是热度。
COUNTDOWN_ARC_COLOR = (0x3B, 0x82, 0xF6)

# 倒计时结束（_fired）后，整圈圆环**闪烁**提示时间到：亮/暗各占半个周期。
COUNTDOWN_BLINK_HZ = 2.0


def _snap_alpha(opacity_pct):
    """把内部不透明度%吸附到最近的档位值，保证菜单永远有一个对号。"""
    vals = [v for _, v in ALPHA_ENTRIES]
    if opacity_pct in vals:
        return opacity_pct
    return min(vals, key=lambda v: abs(v - opacity_pct))


def build_choice_menu(parent, menu, title, entries, current, on_pick):
    """给 menu 挂一个**单选**子菜单，返回 (子菜单, action 列表, QActionGroup)。

    为什么非要 QActionGroup：Qt 里 `setCheckable(True)` **不带任何互斥**。同一个
    菜单里放几个 checkable action，Qt 不会自动把它们凑成一组，点新的一项时旧的
    对号会留着不放 —— 用户在托盘里看到的「0% 和 100% 前面都有对号」就是这个。
    实测见 `_test_tray.py`（不加组时勾选数 2，加了才是 1；鼠标点击和键盘回车
    两条路径同样）。互斥只能靠 QActionGroup，所以统一封装，别在调用点各写一遍。

    entries：[(显示文字, 值)]；current：当前生效的值（决定初始对号）。
    on_pick：选中时回调，收 entries 里的「值」。
    """
    group = QActionGroup(parent)
    group.setExclusive(True)
    sub = SubMenuRight(title)
    # 显式记住父菜单：QMenu 子菜单**没有**指回父菜单的父级引用 —— addMenu 不会把
    # 子菜单的 QWidget/QObject 父级设成父菜单（实测 parentWidget() 与 parent() 都是
    # None），所以子菜单的 showEvent 里拿不到父菜单就没法定位（曾经的 SubMenuRight
    # 就是这样一直空转的）。这里挂一个显式属性，父菜单被 HeatDial 持有，顺带保活。
    sub._parent_menu = menu
    menu.addMenu(sub)
    # 关键：把子菜单挂到父菜单的持久属性上。addMenu 后若没有 Python 强引用，
    # 这个 QMenu 会被 GC 回收、C++ 对象随之从父菜单移除 —— 表现为「菜单里只剩
    # 最后一个子菜单，前面那些（停靠位置 / 透明度 / 托盘按钮单击效果等）凭空消失」。
    # 父菜单(self._menu)本身被 HeatDial 持有，所以挂在这里最稳。
    subs = getattr(menu, "_choice_submenus", None)
    if subs is None:
        subs = []
        menu._choice_submenus = subs
    subs.append(sub)
    acts = []
    for label, value in entries:
        act = QAction(label, parent)
        act.setCheckable(True)
        act.setChecked(value == current)
        act.triggered.connect(lambda _=False, v=value: on_pick(v))
        group.addAction(act)               # ← 互斥靠这一句，别省
        sub.addAction(act)
        acts.append(act)
    return sub, acts, group


def submenu_pos(pg, y0, anchor_bottom, w, h, sg):
    """算子菜单落点（全局坐标）：水平钉父菜单右缘，垂直**优先向上展开**。

    托盘菜单贴着屏幕下边、整体往上开，它的下半部分（托盘按钮单击效果 / 双击效果）离任务栏
    很近；子菜单若继续从父项往下铺，就掉到任务栏那一侧、看着「往下坠」。所以这里改成
    **向上展开**：让子菜单**底边贴住父项底边**（anchor_bottom），占用父项上方的空间；
    只有上方实在放不下（父项已经贴屏幕顶）才退回向下展开（y0 = 父项顶边）。

    pg 父菜单几何；y0 父项顶边全局 y（向下展开时用）；anchor_bottom 父项底边全局 y；
    w/h 子菜单宽高；sg 屏幕几何。返回 QPoint。

    抽成纯函数是为了能直接测：离屏 / 某些平台下 QMenu 不做布局，``actionGeometry``
    对所有 action 返回同一个整菜单矩形，端到端探针验不出垂直落点。
    """
    x = pg.right()
    if x + w > sg.right():
        x = pg.left() - w                        # 右边没空间才退回左边
    x = max(sg.left(), x)                        # 兜底：两边都放不下时贴屏幕左缘
    y = anchor_bottom - h                        # 向上展开：底边贴父项底边
    if y < sg.top():                             # 上方放不下 → 退回向下展开
        y = y0
    y = max(sg.top(), min(y, sg.bottom() - h))   # 兜底：夹回屏幕内
    return QPoint(x, y)


def submenu_item_bottom(parent, act):
    """子菜单所对应**父项底边**的全局 y；拿不到就退回父菜单底边。

    离屏 / 某些平台下 QMenu 不做布局，``actionGeometry`` 对所有 action 返回同一个整
    菜单矩形 —— 那时按父菜单底边当锚点（视觉上等价于贴着菜单底部向上展开）。
    """
    if act is not None:
        ir = parent.actionGeometry(act)
        if not ir.isNull() and 0 < ir.height() < parent.height():
            return parent.mapToGlobal(ir.bottomLeft()).y()
    return parent.mapToGlobal(QPoint(0, parent.height())).y()


class SubMenuRight(QMenu):
    """子菜单强制在父菜单**右侧**弹出，且**向上展开**（底边贴父项底边）。

    托盘菜单锚在屏幕右下角、整体向上展开，Qt 默认把子菜单从父项顶部继续**向下**铺，
    于是整块掉到任务栏那一侧、看着「往下坠」。这里在 showEvent 里同时管两个轴：
    水平钉父菜单右缘、垂直向上展开（落点算法见 ``submenu_pos``）。

    只有父菜单真的可见（真实从托盘菜单展开子菜单时）才生效，直接 popup 调试时不打扰。
    """

    def showEvent(self, ev):
        super().showEvent(ev)
        # 父菜单来自 build_choice_menu 挂的显式属性（见那里的注释：QMenu 子菜单的
        # parentWidget()/parent() 都是 None，拿不到父菜单就没法定位）。
        parent = getattr(self, "_parent_menu", None)
        if not isinstance(parent, QMenu) or not parent.isVisible():
            return
        screen = QApplication.screenAt(parent.geometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return
        pg = parent.geometry()
        # 用 sizeHint 而不是 width()/height()：showEvent 触发时（离屏尤其明显）控件
        # 还没按 popup 的尺寸布局完，height() 会拿到未布局的默认值，落点就算歪了。
        w = self.sizeHint().width()
        h = self.sizeHint().height()
        bottom = submenu_item_bottom(parent, self.menuAction())
        self.move(submenu_pos(pg, self.y(), bottom, w, h, screen.geometry()))


def sync_choice_checks(acts, entries, current):
    """按 current 回写一组单选的勾选 —— 配置值当唯一数据源。

    QActionGroup 只保证「点击时互斥」，管不了「显示的永远是配置里那个」：
    手工编辑 config.json、将来加热键、外部复位之类都会让菜单留着过期对号。
    """
    for act, (_label, value) in zip(acts, entries):
        act.setChecked(value == current)


def heat_color(frac):
    """热度 0~1 → 色阶颜色。色阶表在 heatcore 里，和 Tkinter 版共用。"""
    return QColor(*heat_rgb(frac))


def dial_icon(size=64):
    """托盘图标：和悬浮窗同一套造型，缩放版。不依赖任何外部图片文件。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    r = (size - size * 0.22) / 2.0
    rect = QRectF(size / 2.0 - r, size / 2.0 - r, r * 2, r * 2)
    pen = QPen(QColor(*heat_rgb(1.0)), size * 0.15)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawArc(rect, int(START_DEG * 16), int(-SWEEP_DEG * 0.62 * 16))
    pen.setColor(QColor(0x4A, 0x9E, 0xE8))
    p.setPen(pen)
    p.drawArc(rect, int(START_DEG * 16), int(-SWEEP_DEG * 0.24 * 16))
    p.end()
    return QIcon(pm)


class HeatDial(QWidget):
    def __init__(self, service: HeatService):
        super().__init__()
        self._service = service
        cfg = service.config.get("overlay", {})
        self._overlay_cfg = cfg
        self._theme = THEMES.get(cfg_get(cfg, "theme", "dark"), THEMES["dark"])
        self._bg_alpha = int(max(0.0, min(1.0, float(cfg_get(cfg, "bg_alpha", 0.72)))) * 255)
        self._campfire = bool(cfg_get(cfg, "campfire", True))
        # 「悬停时隐藏表盘」：默认 off（不改变既有行为，用户在托盘里主动开启）。
        self._hover_hide = str(cfg_get(cfg, "hide_on_hover", "off")) == "on"
        self._hover_hidden = False# 因悬停而隐藏（与「手动隐藏」分开记）
        self._manually_hidden = False   # 因托盘「隐藏表盘」而隐藏
        self._tracking_mouse = False    # 保留字段（历史命名），当前实现不再需要原生订阅
        # 木柴样式（flat / bark / charred / gnarled），见 flame.LOG_STYLES
        self._log_style = str(cfg_get(cfg, "log_style", flame.LOG_STYLE_DEFAULT))
        # 位图柴堆（相对项目根目录的 PNG 路径；空 = 代码绘制三对柴塔 + 端向柴）。
        # 后景画在火焰后面，前景画在火焰前面（压住火焰下半段和平直底边）—— 层次
        # 由槽位决定，不再是"整个柴堆在火前还是火后"的单一开关。
        self._log_image = str(cfg_get(cfg, "log_image", flame.LOG_IMAGE_DEFAULT))
        self._log_image_obj = None      # flame.LogImage，加载一次缓存
        self._log_image_front = str(
            cfg_get(cfg, "log_image_front", flame.LOG_IMAGE_DEFAULT))
        self._log_image_front_obj = None
        # 底火层：固定高度的一层暗火，低热时也压住柴堆的炭化柴尖（见 flame.FLAME_FLOOR_*）
        self._flame_floor = bool(cfg_get(cfg, "flame_floor", True))
        self._snap = {"heat": 0.0, "kpm": 0, "peak": 0.0, "state": "idle"}
        self._tip = ""                 # 托盘 tooltip 的上一份文本，避免每帧都重设
        self._boot_start = time.time()
        self._boot_done = False
        self._phase = 0.0          # 火苗摇曳的时间相位，每帧累加
        self._last_t = None
        self._sparks = flame.SparkField()
        # 倒计时：选时长后才开始（不写盘，一次性）。_fired 后触发提示效果，
        # 一直持续到用户在菜单里选「关闭」或换一个时长。
        self._countdown_min = 0
        self._countdown_deadline = None
        self._fired = False
        self._fire_start = 0.0
        # 摇曳是低频动画，250ms 一步会明显"跳"。篝火模式把刷新率拉到 80ms
        # （12.5fps）—— 一个 190px 窗口的 QPainter 重绘，办公机完全承受得起。
        self._refresh_ms = self._refresh_interval()

        size = int(cfg_get(cfg, "size", 176))
        self.setFixedSize(size, size)
        self.setWindowTitle("键盘热度")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._place()

        # 单击去抖定时器：单击后延迟 SINGLE_CLICK_DELAY_MS 才执行，给双击留识别
        # 窗口（双击到达时 stop 它、改跑双击动作）。timeout 直接绑到单击动作方法。
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._do_single_click_action)

        self._build_tray()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(60)          # 开屏动画要走得顺，先上快帧；动画结束回落
        # 置顶看门狗：见 _enforce_topmost 注释。每 1s 把窗口重新声明为 HWND_TOPMOST，
        # 抵消 Qt6 + Windows 在焦点切换时把置顶位被动降格的问题。
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._enforce_topmost)
        self._topmost_timer.start(1000)
        # 悬停轮询：只有开启「悬停时隐藏表盘」时才跑（默认关 → 定时器不启动，零开销）。
        # 间隔 100ms：足够跟手，又不至于像刷新循环那样频繁查询光标位置。
        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._poll_hover)
        self._sync_hover_timer()
        self._preload_log_images()     # 后台线程预加载柴堆 PNG，首帧不再同步解码（~232ms）

    def _preload_log_images(self):
        """窗口显示前同步解码柴堆 PNG，确保首帧直接画位图、不再有
        『开屏先代码绘制柴堆→PNG 就绪后切换成位图』的视觉跳变。

        两张图（后景 2560×1440、前景 2560×1400）解码约 232ms，放在 __init__
        里、窗口 show() 之前完成——此时还没有 UI 事件循环，用户只是双击后
        多等约 0.2s；相比『窗口出现后再卡一下 + 柴堆形状切换闪现』，体感更
        丝滑。paintEvent 首帧即走位图分支（_log_image_obj 已就绪），drawImage
        是 blit，不会像同步解码那样阻塞；解码失败（文件损坏）则保持 None，
        首帧走代码绘制柴堆兜底（始终一致，无切换）。
        """
        back = self._log_image
        front = self._log_image_front
        if back:
            bj = flame.log_image_load(back)
            if bj is not None:
                self._log_image_obj = bj
        if front:
            fj = flame.log_image_load(front, slot="front")
            if fj is not None:
                self._log_image_front_obj = fj

    # ---------------- 定位 ----------------

    def _place(self):
        screens = QApplication.screens()
        idx = int(cfg_get(self._overlay_cfg, "screen", 0))
        screen = screens[idx] if 0 <= idx < len(screens) else QApplication.primaryScreen()
        geo = screen.availableGeometry()
        margin = int(cfg_get(self._overlay_cfg, "margin", 28))
        pos = cfg_get(self._overlay_cfg, "position", "bottom-right")
        w, h = self.width(), self.height()

        x = geo.x() + (geo.width() - w - margin if "right" in pos else margin)
        y = geo.y() + (geo.height() - h - margin if "bottom" in pos else margin)
        self.move(int(x), int(y))

    def _set_position(self, value):
        cfg_set(self._overlay_cfg, "position", value)
        save_config(self._service.config)
        self._sync_tray_checks()
        self._place()

    def _set_screen(self, idx):
        """托盘菜单选中某显示器：写 config、回写对号、重新落位。"""
        cfg_set(self._overlay_cfg, "screen", int(idx))
        save_config(self._service.config)
        self._sync_tray_checks()
        self._place()

    def _build_screen_menu(self, menu):
        """（重）构建「显示器」单选子菜单；多屏才挂，单屏自动移除。

        显示器枚举、菜单增删、落点重排都收在这里，_build_tray 初次搭建和屏幕热插拔
        （_on_screens_changed）两套路径共用，避免两处各写一遍漂移。
        """
        screens = QApplication.screens()
        # 移除旧子菜单（重构建时）
        old = getattr(self, "_screen_sub", None)
        if old is not None:
            menu.removeAction(old.menuAction())
            subs = getattr(menu, "_choice_submenus", [])
            if old in subs:
                subs.remove(old)
            self._screen_sub = None
            self._screen_acts = None
        if len(screens) <= 1:
            return
        cur = int(cfg_get(self._overlay_cfg, "screen", 0))
        if not (0 <= cur < len(screens)):
            cur = 0
            cfg_set(self._overlay_cfg, "screen", 0)
            save_config(self._service.config)
        entries = [
            ("显示器 %d%s" % (i + 1, "（主屏）" if s == QApplication.primaryScreen() else ""), i)
            for i, s in enumerate(screens)
        ]
        self._screen_entries = entries
        sub, acts, group = build_choice_menu(
            self, menu, "显示器", entries, cur, self._set_screen)
        self._screen_sub, self._screen_acts, self._screen_group = sub, acts, group
        # 钉在「停靠位置」子菜单之**前**（用户要求：显示器排在停靠位置上面）。
        # build_choice_menu 是 append，这里再插回去；热插拔重建时也保持同一位置，
        # 不漂到菜单末尾。锚点传 action 指针而不是索引：insertMenu 会把已存在的
        # menuAction 挪过去，索引在挪动后即失效。
        pos_sub = getattr(self, "_pos_sub", None)
        if pos_sub is not None:
            try:
                menu.insertMenu(pos_sub.menuAction(), sub)
            except (RuntimeError, TypeError):
                pass

    def _on_screens_changed(self, *_args):
        """显示器热插拔回调：重建子菜单（数量 / 主屏标记可能变）并重新落位。"""
        self._build_screen_menu(self._menu)
        self._place()

    def _set_alpha(self, value):
        cfg_set(self._overlay_cfg, "bg_alpha", value)
        self._bg_alpha = int(max(0.0, min(1.0, value)) * 255)
        save_config(self._service.config)
        self._sync_tray_checks()
        self.update()

    def _sync_tray_checks(self):
        """把两组单选的勾选按**当前配置值**回写一遍。

        QActionGroup 只管「点击时互斥」，它保证不了「显示的永远是配置里那个」。
        状态只要从别的路径改过（手工编辑 config.json、将来加热键、双击托盘复位
        之类），菜单就会留着过期对号。这里让配置值当唯一数据源：菜单显示什么，
        永远等于配置里是什么。两组 action 不存在时（托盘还没搭好）直接跳过。
        """
        pos_acts = getattr(self, "_pos_acts", None)
        alpha_acts = getattr(self, "_alpha_acts", None)
        if not pos_acts or not alpha_acts:
            return
        pos = cfg_get(self._overlay_cfg, "position", "bottom-right")
        alpha = int(round(float(cfg_get(self._overlay_cfg, "bg_alpha", 0.72)) * 100))
        sync_choice_checks(pos_acts, POSITIONS, pos)
        sync_choice_checks(alpha_acts, ALPHA_ENTRIES, _snap_alpha(alpha))
        cd_acts = getattr(self, "_countdown_acts", None)
        if cd_acts:
            sync_choice_checks(cd_acts, COUNTDOWN_DURATIONS, self._countdown_min)
        sc_acts = getattr(self, "_singleclk_acts", None)
        if sc_acts:
            sync_choice_checks(
                sc_acts, SINGLECLK_ENTRIES,
                cfg_get(self._overlay_cfg, "tray_single_click", "open_stats"))
        dc_acts = getattr(self, "_doubleclk_acts", None)
        if dc_acts:
            sync_choice_checks(
                dc_acts, SINGLECLK_ENTRIES,
                cfg_get(self._overlay_cfg, "tray_double_click", "open_stats"))
        cf_acts = getattr(self, "_campfire_acts", None)
        if cf_acts:
            sync_choice_checks(cf_acts, CAMPFIRE_ENTRIES, self._campfire)
        hv_acts = getattr(self, "_hover_acts", None)
        if hv_acts:
            sync_choice_checks(
                hv_acts, HOVER_ENTRIES,
                cfg_get(self._overlay_cfg, "hide_on_hover", "off"))
        scn_acts = getattr(self, "_screen_acts", None)
        if scn_acts:
            sync_choice_checks(scn_acts, self._screen_entries,
                              int(cfg_get(self._overlay_cfg, "screen", 0)))

    # ---------------- 托盘 ----------------

    def _build_tray(self):
        self._tray = QSystemTrayIcon(dial_icon(), self)
        self._tray.setToolTip("键盘热度")
        self._tray.activated.connect(self._on_tray_activated)

        menu = QMenu()

        # —— 第一块：统计面板（顶层动作，打开历史 / 统计报告）——独占一组：
        # 结尾必须有 addSeparator()，否则它会和下面的计时组粘成一整块（用户反馈的
        # "统计面板没有单独成组"就是这个分隔线漏了，不是顺序问题）。
        act_report = QAction("打开统计面板", self)
        act_report.triggered.connect(self._open_report)
        menu.addAction(act_report)
        menu.addSeparator()

        # —— 计时组：倒计时 在 停止计时 之上 ——
        # 倒计时：子菜单只放真正会开始倒计时的时长（25 / 10 / 5，向上展开让 5 分钟
        # 最接近父菜单），不再含「关闭」。
        _sub, self._countdown_acts, self._countdown_group = build_choice_menu(
            self, menu, "倒计时", COUNTDOWN_DURATIONS, self._countdown_min,
            self._set_countdown)

        # 停止计时：清掉进行中 / 已触发的计时与提示（旧复位档，不落库）。
        act_stop_cd = QAction("停止计时", self)
        act_stop_cd.triggered.connect(self._stop_countdown)
        menu.addAction(act_stop_cd)

        menu.addSeparator()

        # 三组**单选**子菜单。互斥与初始对号统一交给 build_choice_menu（见它的
        # docstring：光 setCheckable 不互斥，这正是"两个对号"那个 bug 的根因）。
        cur_pos = cfg_get(self._overlay_cfg, "position", "bottom-right")
        self._pos_sub, self._pos_acts, self._pos_group = build_choice_menu(
            self, menu, "停靠位置", POSITIONS, cur_pos, self._set_position)

        # 显示器选择：仅在多屏时挂出（单屏只有「显示器 1」没意义）。
        # 索引 0 = 主屏，与 _place 里 screens[idx] 一致。
        # 挂出后由 _build_screen_menu 自己插到「停靠位置」**上面**（见那里的注释）。
        self._build_screen_menu(menu)

        cur_alpha = int(round(float(cfg_get(self._overlay_cfg, "bg_alpha", 0.72)) * 100))
        _sub, self._alpha_acts, self._alpha_group = build_choice_menu(
            self, menu, "透明度", ALPHA_ENTRIES, _snap_alpha(cur_alpha),
            lambda pct: self._set_alpha(pct / 100.0))

        # 篝火 ⇄ 表盘：二选一的子菜单（渲染形态互换，采集/热度不变）。写 config。
        _sub, self._campfire_acts, self._campfire_group = build_choice_menu(
            self, menu, "表盘样式", CAMPFIRE_ENTRIES, self._campfire,
            self._set_campfire)

        # 「鼠标悬停时隐藏表盘」：单选子菜单（关 / 悬停时隐藏），默认「关」= 不改变既有行为。
        # 放在「隐藏表盘」**上方**：两者都是「让表盘别碍事」的手段，挨在一起才成组；
        # 且「隐藏表盘」是组内最后一个（用户此前明确要求它置于位置/透明度/样式之下）。
        _sub, self._hover_acts, self._hover_group = build_choice_menu(
            self, menu, "鼠标悬停时", HOVER_ENTRIES,
            cfg_get(self._overlay_cfg, "hide_on_hover", "off"),
            self._set_hover_hide)

        # 隐藏表盘：纯隐藏 / 显示前台界面（不暂停数据采集）。勾选 = 隐藏，取消 = 显示。
        # 放在「停靠位置 / 透明度 / 表盘样式」这一组的**最下面**（用户要求：与这三者同组、
        # 且置于三者的下方）。
        self._act_hide_dial = QAction("隐藏表盘", self, checkable=True)
        self._act_hide_dial.triggered.connect(self._toggle_hide_dial)
        menu.addAction(self._act_hide_dial)

        menu.addSeparator()

        # —— 两个快捷入口各自一组，置于菜单末（在退出上方）——
        # 单击 / 双击各是托盘图标的一种快捷操作入口，各自在右键菜单里配置动作，
        # 都不弹菜单。单选，写盘，默认都打开统计面板。
        _sub, self._singleclk_acts, self._singleclk_group = build_choice_menu(
            self, menu, "托盘按钮单击效果", SINGLECLK_ENTRIES,
            cfg_get(self._overlay_cfg, "tray_single_click", "open_stats"),
            self._set_single_click)

        _sub, self._doubleclk_acts, self._doubleclk_group = build_choice_menu(
            self, menu, "托盘按钮双击效果", SINGLECLK_ENTRIES,
            cfg_get(self._overlay_cfg, "tray_double_click", "open_stats"),
            self._set_double_click)

        # 托盘按钮右键效果：固定为「弹出菜单」，不可更改，仅作提示（右键本就弹菜单）。
        # 单独一个子菜单、唯一项「菜单」默认勾选且禁用，不走 build_choice_menu（不计入
        # 那 6 组单选；禁用项也不该参与互斥组）。
        right_sub = QMenu("托盘按钮右键效果", menu)
        right_act = QAction("菜单", self, checkable=True)
        right_act.setChecked(True)
        right_act.setEnabled(False)
        right_sub.addAction(right_act)
        menu.addMenu(right_sub)

        menu.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_quit)

        self._menu = menu
        self._tray.show()

        # 显示器热插拔：屏幕增删时重建「显示器」子菜单并重新落位，避免窗口留在
        # 已消失的屏外（_place 本身也会在 idx 越界时回退主屏，这里双保险）。
        app = QApplication.instance()
        if app is not None:
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screens_changed)

    def _on_tray_activated(self, reason):
        # 左键单击与左键双击是两套快捷操作入口（各自在右键菜单里配置动作，都不弹
        # 菜单）。单击先走去抖定时器，给双击留识别窗口；期间若收到双击，取消单击、
        # 立即执行双击动作，避免双击被拆成两次单击。右键：弹出右键菜单（锚定托盘
        # 图标、随屏幕边缘翻转，和左键菜单同一套几何），不用 setContextMenu 默认锚定。
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._click_timer.stop()
            self._do_double_click_action()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._schedule_single_click()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            self._popup_menu()

    def _do_single_click_action(self):
        """执行左键单击托盘图标的配置行为：打开统计面板 / 倒计时 5|10|25 分钟。"""
        action = cfg_get(self._overlay_cfg, "tray_single_click", "open_stats")
        if action in ("cd5", "cd10", "cd25"):
            self._set_countdown(int(action[2:]), "single_click")
        else:
            self._open_report()

    def _schedule_single_click(self):
        """单击去抖：启动单次定时器，延迟 SINGLE_CLICK_DELAY_MS 后跑单击动作。

        给双击留出识别窗口 —— 双击到达时（_on_tray_activated 的 DoubleClick 分支）
        会先 stop 这个定时器，改跑双击动作，这样双击不会先误触发一次单击。
        """
        self._click_timer.start(SINGLE_CLICK_DELAY_MS)

    def _do_double_click_action(self):
        """执行左键双击托盘图标的配置行为：打开统计面板 / 倒计时 5|10|25 分钟。"""
        action = cfg_get(self._overlay_cfg, "tray_double_click", "open_stats")
        if action in ("cd5", "cd10", "cd25"):
            self._set_countdown(int(action[2:]), "double_click")
        else:
            self._open_report()

    def _popup_menu(self):
        """在托盘图标旁边弹出菜单，位置贴着图标、随屏幕边缘自动翻转。

        之前用 ``QCursor.pos()`` 当锚点，光标落在任务栏图标偏下/偏右时，菜单会显得
        「靠下」、和原生右键菜单不对齐。这里改用托盘图标自身的屏幕矩形
        （``QSystemTrayIcon.geometry()``）当锚点，按所在屏幕边缘决定向上翻（底部任务栏）
        还是向下翻（顶部任务栏），并把水平方向收拢到图标左缘、避免超出左右边界 ——
        和 Windows 原生托盘右键菜单的贴手感一致。
        """
        menu = self._menu
        if menu is None:
            return
        geom = self._tray.geometry()
        if geom.isNull():
            # 极少数平台拿不到图标几何，退回光标位置。
            menu.popup(QCursor.pos())
            return
        screen = QApplication.screenAt(geom.center()) or QApplication.primaryScreen()
        sg = screen.geometry() if screen is not None else QApplication.primaryScreen().geometry()
        mw = menu.sizeHint().width()
        mh = menu.sizeHint().height()
        # 水平：默认左缘对齐图标左缘；会超出右边界则左移到图标右缘 - 宽；再夹回屏内。
        x = geom.x()
        if x + mw > sg.right():
            x = geom.right() - mw
        if x < sg.left():
            x = sg.left()
        # 垂直：图标贴屏幕下边 → 向上翻（底边贴图标上边）；贴上边 → 向下；否则默认向下。
        if geom.bottom() >= sg.bottom() - 4:
            y = geom.top() - mh
        elif geom.top() <= sg.top() + 4:
            y = geom.bottom()
        else:
            y = geom.bottom()
        if y < sg.top():
            y = sg.top()
        menu.popup(QPoint(x, y))

    def _set_single_click(self, value):
        """左键单击托盘图标的效果：open_stats / cd5 / cd10 / cd25。写盘。"""
        cfg_set(self._overlay_cfg, "tray_single_click", value)
        save_config(self._service.config)
        self._sync_tray_checks()

    def _set_double_click(self, value):
        """左键双击托盘图标的效果：open_stats / cd5 / cd10 / cd25。写盘。"""
        cfg_set(self._overlay_cfg, "tray_double_click", value)
        save_config(self._service.config)
        self._sync_tray_checks()

    def _set_campfire(self, value):
        """篝火 ⇄ 表盘。采集和热度是同一套，切换的只是渲染。value: True=篝火 / False=表盘。"""
        self._campfire = bool(value)
        cfg_set(self._overlay_cfg, "campfire", self._campfire)
        save_config(self._service.config)
        self._timer.setInterval(self._refresh_interval())
        self.update()
        self._sync_tray_checks()

    def _toggle_hide_dial(self):
        """隐藏表盘：只隐藏 / 显示前台界面，不暂停数据采集。

        勾选 = 隐藏窗口（托盘图标仍在，数据采集继续）；取消勾选 = 显示窗口。
        这是「暂停记录」的替代：用户要的是「不显示界面」而非「停止记录」。

        ⚠ 与「悬停隐藏」共用同一个可见性开关：手动隐藏期间不接受悬停恢复
          （_hover_hidden 与setHidden 是两条独立的隐藏路径，见 _apply_hover）。
        """
        hidden = self._act_hide_dial.isChecked()
        self._manually_hidden = hidden
        if hidden:
            self._hover_hidden = False
        else:
            self._restore_after_hover()
        self.setHidden(hidden)
        self._sync_tray_checks()
        self.update()

    # ---------------- 悬停隐藏 ----------------
    def _cursor_on_dial(self):
        """鼠标是否落在表盘矩形内。

        为什么不用 Qt 的 enterEvent/leaveEvent：窗口旗标含
        `WindowTransparentForInput`（鼠标穿透），Qt 根本收不到指针事件。
        为什么不用 Win32 的 WM_MOUSEENTER/WM_MOUSELEAVE + nativeEvent：
        PyQt6 传进来的 `message` 是 **PyCapsule**，用 `int()` 当指针、
        再 `MSG.from_address()` 解释，会按错误的结构体布局读原生内存 ——
        实测直接 **0xC0000409（栈缓冲区溢出）秒退**，且 Python 层连
        error.log 都写不出来（崩溃在原生层）。风险与收益完全不成比例。
        → 采用**几何判断**：读QCursor 的全局坐标，和表盘的全局矩形比对。
          不碰任何原生指针，纯 Qt API，不可能崩。
        表盘被拖动/改位置后矩形随之变化（Qt 自动更新），故不需要额外同步。
        """
        try:
            global_rect = self.frameGeometry()      # 含边框的全局矩形
            return global_rect.contains(QCursor.pos())
        except Exception:
            return False

    def _poll_hover(self):
        """轮询鼠标是否在表盘上：进入则隐藏、离开则恢复。

        挂在已有刷新定时器之外单独跑（_hover_timer），因为关闭本功能时
        _refresh 的间隔会变，且表盘隐藏时也要继续轮询才能恢复显示。
        """
        if not self._hover_hide:
            return
        if self._manually_hidden:
            return                       # 手动隐藏中：不参与，交给菜单项
        on = self._cursor_on_dial()
        if on and not self._hover_hidden:
            self._hover_hidden = True
            self._apply_hover(True)
        elif not on and self._hover_hidden:
            self._hover_hidden = False
            self._apply_hover(False)

    def _set_hover_hide(self, value):
        """「鼠标悬停时隐藏表盘」：on = 进入即隐藏；off = 始终显示。"""
        cfg_set(self._overlay_cfg, "hide_on_hover", value)
        self._hover_hide = (value == "on")
        save_config(self._service.config)
        self._sync_hover_timer()
        if not self._hover_hide:
            self._restore_after_hover()
        self._sync_tray_checks()

    def _sync_hover_timer(self):
        """按开关起停轮询定时器。关闭时不跑 —— 零开销、不改变既有行为。"""
        if not hasattr(self, "_hover_timer"):
            return
        if self._hover_hide and not self._hover_timer.isActive():
            self._hover_timer.start()
        elif not self._hover_hide and self._hover_timer.isActive():
            self._hover_timer.stop()

    def _on_mouse_leave(self):
        """鼠标离开表盘：若此前是「悬停隐藏」藏起来的，这里恢复显示。

        保留这个方法是为了让状态流转仍可被探针直接驱动（`_poll_hover` 内部
        走的是同一套判断，不经过它）。
        """
        if self._hover_hidden:
            self._hover_hidden = False
            if not self._manually_hidden:
                self._apply_hover(False)

    def _on_mouse_enter(self):
        """鼠标进入表盘：开启「悬停隐藏」时立即藏起来。"""
        if self._hover_hide and not self._manually_hidden and not self._hover_hidden:
            self._hover_hidden = True
            self._apply_hover(True)

    def _apply_hover(self, hidden):
        """真正执行隐藏/恢复。与「隐藏表盘」菜单项共用 setHidden，
        但各自维护自己的标志位，互不覆盖对方的意图。"""
        self.setHidden(hidden)
        self.update()

    def _restore_after_hover(self):
        """从「悬停隐藏」恢复：仅当没有手动隐藏时才显示出来。"""
        if self._hover_hidden:
            self._hover_hidden = False
            if not self._manually_hidden:
                self._apply_hover(False)

    def _stop_countdown(self):
        """停止计时（顶层动作「停止计时」）：清掉进行中 / 已触发的倒计时与提示。

        等价于旧版倒计时子菜单里的「关闭」档。minutes=0 不落库 —— 停止不算一次使用。
        """
        self._set_countdown(0, "menu")

    def _set_countdown(self, minutes, source="menu"):
        """倒计时档位：0=关闭；>0=开始倒计时 minutes 分钟。

        到点后由 `_refresh` 把 `_fired` 置 True 并触发提示（篝火呼吸 / 数字「时间到」）。
        选「关闭」/「停止计时」同时清掉已触发的提示 —— 这是用户关掉效果的唯一入口。

        source 记录触发来源（menu / single_click / double_click / hotkey），只在
        真正开始（minutes>0）时落库，供报告「每天按类型计数」使用。「关闭」不算
        一次使用。single_click 来自左键单击、double_click 来自左键双击配置的快捷入口。
        """
        self._countdown_min = minutes
        if minutes > 0:
            self._countdown_deadline = time.time() + minutes * 60.0
            self._fired = False
            log_countdown(minutes, source, self._service.db_path)
        else:
            self._countdown_deadline = None
            self._fired = False
        # 进入/退出倒计时要重设刷新率（倒计时时强制 80ms，保证耗尽与闪烁平滑）。
        self._refresh_ms = self._refresh_interval()
        self._timer.setInterval(self._refresh_ms)
        self._sync_tray_checks()
        self.update()

    def _open_report(self):
        import report                                    # 延迟导入，避免循环依赖
        out = report.generate(self._service.config, db_path=self._service.db_path)
        os.startfile(str(out))                           # noqa: S606  Windows 专用
        return out

    def _quit(self):
        self._timer.stop()
        self._tray.hide()
        self._service.stop()
        QApplication.quit()

    # ---------------- 置顶看门狗 ----------------

    def _enforce_topmost(self):
        """周期性把窗口重新声明为 HWND_TOPMOST，抵消运行中被动降格。

        Qt6 + Windows 下，带 WindowDoesNotAcceptFocus 的窗口在别的窗口被前置 /
        最大化时，WindowStaysOnTopHint 的置顶位会被 OS/Qt 在焦点事件里降格，导致
        一个普通最大化窗也能盖住悬浮层。代码里 topmost 只在 __init__ 设一次、之后
        从不自降，所以是外部把它降下来的。这里每隔 1s 用 SetWindowPos 重新置顶，
        SWP_NOACTIVATE 保证不抢焦点、不打断用户当前操作。
        """
        if not self.isVisible():
            return
        try:
            hwnd = int(self.winId())
            # HWND_TOPMOST = -1；SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE = 0x1|0x2|0x10
            ctypes.windll.user32.SetWindowPos(
                hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010
            )
        except Exception:
            pass

    # ---------------- 绘制 ----------------

    def _refresh_interval(self):
        """稳态刷新间隔。篝火模式要跑摇曳动画，最迟 80ms 一步。

        倒计时进行 / 已触发时也拉到 80ms —— 圆环要平滑地耗尽、到点后还要整圈
        闪烁，帧率太低闪烁会卡顿（尤其数字模式默认 250ms）。
        """
        if self._countdown_min > 0:
            return 80
        base = max(80, int(cfg_get(self._overlay_cfg, "refresh_ms", 250)))
        return min(base, 80) if self._campfire else base

    def _refresh(self):
        now = time.time()
        # 倒计时到点 → 触发提示（篝火呼吸 / 数字「时间到」）。提示一直持续到用户
        # 在菜单选「关闭」或换一个时长（都会把 _fired 清掉）。
        if self._countdown_min > 0 and not self._fired \
                and self._countdown_deadline is not None \
                and now >= self._countdown_deadline:
            self._fired = True
            self._fire_start = now
        if self._last_t is not None:
            self._phase += min(0.5, now - self._last_t)   # 摇曳的时间相位
        self._last_t = now
        self._snap = self._service.snapshot()
        # 篝火模式屏幕上没有数字，精确读数挂到托盘 tooltip 上 —— 鼠标悬停就能看
        tip = "键盘热度 · %d %s · %s" % (
            self._snap.get("kpm", 0),
            HEAT_UNIT,
            STATE_LABEL.get(self._snap.get("state", "idle"), ""),
        )
        if tip != self._tip:
            self._tip = tip
            self._tray.setToolTip(tip)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        d = float(min(self.width(), self.height()))
        cx, cy = self.width() / 2.0, self.height() / 2.0
        thickness = flame.ring_thick(d)
        radius = flame.ring_radius(d)
        arc_rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        booting = not self._boot_done
        boot_t = 0.0
        if booting:
            boot_t = (time.time() - self._boot_start) / BOOT_SWEEP_SECONDS
            if boot_t >= 1.0:
                self._boot_done = True
                booting = False
                self._timer.setInterval(self._refresh_ms)      # 动画结束，帧率回落

        # 底盘：开屏期间也使用配置透明度（self._bg_alpha），与开屏后完全一致 ——
        # 否则「100%透明」用户在开屏时会先看到一块不透明圆盘、开屏结束再突然变透明，
        # 切换很突兀。开屏扫圈 / 点火动画照常播放，只是盘底从一开始就按配置透明。
        plate_r = d / 2.0 - max(2.0, d * 0.012)
        plate = QColor(*self._theme["plate"])
        plate.setAlpha(self._bg_alpha)
        p.setBrush(plate)
        # **不画描边**。原来这里是 `setPen(QPen(QColor(*theme["rim"]), 2.0))`：
        # dark 用半透明白、light 用半透明黑。pen 以路径居中，正好压在底盘半径上，
        # 于是最外圈多出一条高对比的细环 —— 实测（`_rim_off_probe.py`，沿正下方
        # 270° 扫描，那里是弧的缺口，没有弧也没有轨道）：
        #     dark  α=72% 深终端：盘内 lum 27.3 → 边界 135.2（Δ+108）
        #     dark  α=72% 浅色底：盘内 85.2 → 边界 244.1（Δ+159）
        #     light α=72% 深终端：盘内 190.3 → 边界 21.5（Δ−169）
        # 用户报的"圈圈最外面有一个白色的圆形线条"就是它。去掉后圆盘是个干净的
        # 剪影，轮廓交给盘面自身与桌面的色差（`bg_alpha` 别低于 0.8，见 README）。
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), plate_r, plate_r)

        # 盘中央的底 **两种模式都要画**，且必须画在环带轮廓之前：它的半径
        # （`pit_radius`）和轮廓内弧只差 1.5px，晚一步就把内弧切掉半条 —— 实测内弧
        # 可见宽度从 2.1px 掉到 1.5px，一个纯色像素都挤不出来（`_test_ring.py`
        # 第 6 节盯这个）。放在这里还有个好处：暗色不会渗到轮廓线外。
        #   · 篝火模式 = 「灶膛」：给火一块够暗的底（火靠与背景的对比度被看见）。
        #   · 数字模式 = 「盘芯」：给文字一块底。100% 透明度时若没有它，文字会悬在
        #     桌面上，而篝火模式中央却是一块深色灶膛 —— 两种模式切来切去观感割裂
        #     （用户报："篝火部分有深色背景色，文字部分却没有"）。
        # 颜色随模式：灶膛**永远**是深的（与主题无关 —— 火是夜里的东西，见 CAMP_PIT
        # 注释）；盘芯按主题取（dark 用与灶膛**同色**的深色 → 两模式中央一模一样，
        # light 用浅色 → 暗字才压得住，见 THEMES.center_bg）。
        center_rgb = CAMP_PIT if self._campfire else self._theme["center_bg"]
        center_r = flame.pit_radius(d)
        center_c = QColor(*center_rgb)
        center_c.setAlpha(max(self._bg_alpha, CAMP_PIT_MIN_ALPHA))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(center_c)
        p.drawEllipse(QPointF(cx, cy), center_r, center_r)

        # 环带轮廓：**沿整条轨道带描一圈**（外弧 → 末端半圆 → 内弧 → 起点半圆）。
        # 先描轮廓、再把轨道压上去：pen 以路径为中心，两条弧都挪到带外半个笔宽，
        # 所以轨道盖不住它们。这条线是「进度条 vs 圆盘底色」的分界（理由见
        # THEMES.track_edge）；**四条边缺一条都会看着像半条边** —— 用户第 6 轮报的
        # 「现在只有外圈有，内圈和转角的那个地方也应该有」就是它。端头那两个半圆
        # 正好包住轨道的圆笔帽（`round_cap`），所以末尾那个圆头也被圈在里面。
        edge_w = flame.ring_edge_w(d)
        r_out = flame.ring_edge_radius(d)
        r_in = flame.ring_edge_inner_radius(d)
        cap_r = flame.ring_edge_cap_radius(d)
        mid_r = (r_out + r_in) / 2.0                       # = ring_radius
        end_deg = START_DEG - SWEEP_DEG
        rect_o = QRectF(cx - r_out, cy - r_out, r_out * 2, r_out * 2)
        rect_i = QRectF(cx - r_in, cy - r_in, r_in * 2, r_in * 2)
        ea, sa = math.radians(end_deg), math.radians(START_DEG)
        cap_ex, cap_ey = cx + mid_r * math.cos(ea), cy - mid_r * math.sin(ea)
        cap_sx, cap_sy = cx + mid_r * math.cos(sa), cy - mid_r * math.sin(sa)
        rect_e = QRectF(cap_ex - cap_r, cap_ey - cap_r, cap_r * 2, cap_r * 2)
        rect_s = QRectF(cap_sx - cap_r, cap_sy - cap_r, cap_r * 2, cap_r * 2)
        path = QPainterPath()
        path.arcMoveTo(rect_o, START_DEG)
        path.arcTo(rect_o, START_DEG, -SWEEP_DEG)          # 外弧
        path.arcTo(rect_e, end_deg, -180.0)                # 末端半圆（绕缺口那一侧）
        path.arcTo(rect_i, end_deg, SWEEP_DEG)             # 内弧，反向画回起点
        path.arcTo(rect_s, START_DEG + 180.0, -180.0)      # 起点半圆
        path.closeSubpath()
        p.setBrush(Qt.BrushStyle.NoBrush)
        # 线的**不透明度**与底盘反相（`flame.track_edge_alpha`：底盘越实线越淡，
        # 底盘全不透明时线完全消失、底盘全透明时线画满）。理由见那个函数。
        edge_col = QColor(*self._theme["track_edge"])
        edge_col.setAlphaF(flame.track_edge_alpha(self._bg_alpha / 255.0))
        pen = QPen(edge_col, edge_w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)

        p.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor(*self._theme["track"]), thickness)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(arc_rect, int(START_DEG * 16), int(-SWEEP_DEG * 16))

        # 热度弧：开屏时扫一圈，完全空闲时留一小段，其余按真实热度
        frac = max(0.0, min(1.0, float(self._snap.get("heat", 0.0)) / 100.0))
        state = self._snap.get("state", "idle")
        cd = self._countdown_progress()
        if booting:
            arc_frac, arc_color = boot_t, heat_color(boot_t)
        elif cd == "flash":
            # 倒计时结束（环已耗尽到 0%）：整圈闪烁提示时间到。亮帧画满圈蓝弧、
            # 暗帧不画（整圈消失），一眼能看出"进度条在闪"。固定蓝，与热度、
            # 暂停色都区分开。
            arc_color = QColor(*COUNTDOWN_ARC_COLOR)
            arc_frac = 1.0 if self._countdown_flash_on() else 0.0
        elif cd is not None:
            # 倒计时进行中：圆环表示**剩余时间**（满圈→空，随时间耗尽），
            # 不再表示热度。固定蓝色。
            arc_frac, arc_color = cd, QColor(*COUNTDOWN_ARC_COLOR)
        elif state == "paused":
            # 暂停：弧长照旧（那是已有成绩），但换成琥珀色，一眼看出"没在记"
            arc_frac, arc_color = max(frac, IDLE_ARC_DEG / SWEEP_DEG), QColor(0xE0, 0xB0, 0x2C)
        elif frac > IDLE_ARC_DEG / SWEEP_DEG:
            # 阈值是"下限弧长"，不是随便一个小数：早先写 0.002，于是热度从 0
            # 升到刚过 0.2% 时，弧长会从 2.5° **缩到 0.5°** 再重新长起来 ——
            # 热度升、弧反而变短，是个非单调的小跳变（0.5 热度处 2.5°→1.3°）。
            # 拿 IDLE_ARC_DEG/SWEEP_DEG 当阈值，弧就只可能不短于空闲段。
            arc_frac, arc_color = frac, heat_color(frac)
        else:
            arc_frac, arc_color = IDLE_ARC_DEG / SWEEP_DEG, heat_color(0.0)
        pen = QPen(arc_color, thickness)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(arc_rect, int(START_DEG * 16), int(-SWEEP_DEG * arc_frac * 16))

        # ---------------- 中心内容：篝火 或 数字 ----------------
        if self._campfire:
            self._paint_fire(p, cx, cy, d, frac, state, booting, boot_t)
        else:
            self._paint_digits(p, cx, cy, d, radius, frac, state, booting, boot_t)

        p.end()

    # ---------------- 数字仪表盘 ----------------

    def _hud_text(self, p, rect, text, font, fill, align):
        """带描边光晕的文字。

        底盘半透明甚至全透明时，文字**不再有可靠的底色**，纯色文字会直接糊进桌面。
        这道光晕 = 把同一段文字在 8 个方向各偏移 1px、用「与填充反相」的颜色先铺一层，
        再在原位用真色填字 —— 等效于给字形描了一圈 1px 的边。底色是深是浅、盘体透明
        与否都不影响：边框那圈反相色总能勾出字形轮廓。位置与原 drawText 完全一致
        （只把 rect 平移后重画，不改基线算法），所以不引入形态变化。

        判据见 `_text_read_probe.py`：dark/light × 三种桌面 × α=0.45/0.0，文字相对
        局部合成底的 Δlum 从个位数提到 40+。
        """
        if not text:
            return
        p.setFont(font)
        halo = QColor(*self._theme["text_halo"])
        for dx, dy in _HALO_OFFSETS:
            p.setPen(halo)
            p.drawText(rect.adjusted(dx, dy, dx, dy), int(align), text)
        p.setPen(fill)
        p.drawText(rect, int(align), text)

    def _paint_digits(self, p, cx, cy, d, radius, frac, state, booting, boot_t):
        """原来的画法：状态灯 + 大数字 + 单位 + 键鼠分解 + 峰值。"""
        if booting:
            label = ""
            dot_color = heat_color(boot_t)
        else:
            label = STATE_LABEL.get(state, "")
            dot_color = heat_color(frac) if state in ("typing", "pointing", "pause") else QColor(*self._theme["muted"])
            if state == "paused":
                dot_color = QColor(0xE0, 0xB0, 0x2C)

        f_label = QFont()
        f_label.setPixelSize(max(11, int(d * 0.068)))

        p.setFont(f_label)
        fm = p.fontMetrics()
        text_w = fm.horizontalAdvance(label)
        dot_r = max(3.0, d * 0.019)
        gap = d * 0.026
        total_w = dot_r * 2 + gap + text_w
        start_x = cx - total_w / 2.0
        dot_y = cy - d * 0.193

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dot_color)
        p.drawEllipse(QPointF(start_x + dot_r, dot_y), dot_r, dot_r)

        self._hud_text(
            p,
            QRectF(start_x + dot_r * 2 + gap, dot_y - fm.height() / 2.0, text_w + 4, fm.height()),
            label,
            f_label,
            QColor(*self._theme["text"]),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        )

        # 中心大数字 —— 综合活跃度（键盘 + 鼠标折算后并进同一个热度）
        # 倒计时到点 → 数字模式用「时间到」替掉大数字做文字提示（盖过真实读数）。
        if self._fired and not booting:
            f_num = QFont()
            f_num.setPixelSize(max(20, int(d * 0.16)))
            f_num.setWeight(QFont.Weight.Bold)
            num_text = "时间到"
            num_color = QColor(*self._theme["text"])
        else:
            f_num = QFont("Consolas")
            f_num.setPixelSize(max(18, int(d * 0.20)))
            f_num.setWeight(QFont.Weight.DemiBold)
            f_num.setStyleHint(QFont.StyleHint.Monospace)
            p.setFont(f_num)
            if booting:
                num_text, num_color = "就绪", heat_color(boot_t)
            else:
                num_text = str(self._snap.get("kpm", 0))
                num_color = heat_color(frac) if frac > 0.02 else QColor(*self._theme["muted"])
        self._hud_text(
            p,
            QRectF(cx - radius, cy - d * 0.15, radius * 2, d * 0.30),
            num_text,
            f_num,
            num_color,
            int(Qt.AlignmentFlag.AlignCenter),
        )

        # 单位。分母仍是 60 秒，但分子已包含折算后的鼠标活动
        f_unit = QFont()
        f_unit.setPixelSize(max(10, int(d * 0.058)))
        p.setFont(f_unit)
        self._hud_text(
            p,
            QRectF(cx - radius, cy + d * 0.085, radius * 2, d * 0.13),
            HEAT_UNIT,
            f_unit,
            QColor(*self._theme["muted"]),
            int(Qt.AlignmentFlag.AlignCenter),
        )

        # 键 / 鼠 分解：回答"这份热度是敲出来的还是划出来的"
        f_split = QFont()
        f_split.setPixelSize(max(9, int(d * 0.055)))
        p.setFont(f_split)
        self._hud_text(
            p,
            QRectF(cx - radius, cy + d * 0.167, radius * 2, d * 0.13),
            "" if booting else split_text(self._snap.get("kpm_keys", 0),
                                          self._snap.get("kpm_mouse", 0)),
            f_split,
            QColor(*self._theme["muted"]),
            int(Qt.AlignmentFlag.AlignCenter),
        )

        # 底部今日峰值（开屏期间换一句话报个到）
        peak = self._snap.get("peak", 0.0)
        f_peak = QFont()
        f_peak.setPixelSize(max(9, int(d * 0.054)))
        p.setFont(f_peak)
        self._hud_text(
            p,
            QRectF(cx - radius, cy + d * 0.247, radius * 2, d * 0.13),
            "键鼠热度已启动" if booting else "峰值 %d" % round(peak),
            f_peak,
            QColor(*self._theme["muted"]),
            int(Qt.AlignmentFlag.AlignCenter),
        )

    # ---------------- 篝火 ----------------

    def _paint_fire(self, p, cx, cy, d, frac, state, booting, boot_t):
        """盘中央的火堆。圆环照旧画着做精确读数，中心不给任何文字。

        火的高度和颜色都由热度驱动：低热是暗红余烬，旺火才亮到橙黄 ——
        具体造型和配色在 flame.py 里。
        """
        # 灶膛不在这儿画 —— `paintEvent` 把它提到环带轮廓之前了
        # （晚画的话灶膛会把轮廓内弧切掉半条，见那里的注释）。
        heat = flame.fire_heat(frac, state, booting, boot_t)
        # 倒计时到点 → 篝火做呼吸：在小火/大火之间反复变更，盖过真实热度。
        # 开屏期间不抢戏（booting 时火在"点燃"，heat 由 boot_t 驱动）。
        if self._fired and not booting:
            heat = self._breathe_heat()
        # 暂停时不放火星 —— 火星是"正在燃烧"的信号，余烬不该冒火星。
        # 哨兵必须是 False 而不是 None：draw_campfire_qt 里 None 的意思是
        # "没传 field，自己新建一个默认的"，传 None 等于**放弃**这个开关
        # （实测暂停帧里还有 18 个火星像素）。
        field = False if state == "paused" else self._sparks
        # 柴堆 PNG 由 _preload_log_images() 在后台线程异步加载并缓存；这里只读、
        # 不阻塞——加载完成前（首帧）draw_campfire_qt 收到 None 走代码绘制，
        # 线程加载完 self.update() 触发下一帧再切到位图。
        flame.draw_campfire_qt(p, cx, cy, d, heat, self._phase, field,
                               log_style=self._log_style,
                               log_image=self._log_image_obj,
                               log_image_front=self._log_image_front_obj,
                               floor=self._flame_floor)

    def _breathe_heat(self):
        """倒计时提示的呼吸热度：在小火/大火之间按正弦往复。"""
        t = time.time() - self._fire_start
        b = 0.5 + 0.5 * math.sin(2.0 * math.pi * t / COUNTDOWN_BREATHE_PERIOD)
        return COUNTDOWN_FIRE_LOW + (COUNTDOWN_FIRE_HIGH - COUNTDOWN_FIRE_LOW) * b

    def _countdown_progress(self):
        """倒计时进行 / 已触发期间，返回**剩余时间占比**（1.0=刚选时长满圈，
        0.0=到点）；未进入倒计时返回 None —— 此时圆环照旧表示热度。

        因为是倒计时，环随计时**耗尽**（从满圈递减到空）。到点（_fired）返回
        字符串 "flash" —— 圆环不再表示剩余，而是**整圈闪烁**提示时间到
        （paint 端按时间相位做亮/暗开关）。
        """
        if self._countdown_min <= 0 or self._countdown_deadline is None:
            return None
        if self._fired:
            return "flash"
        total = self._countdown_min * 60.0
        remaining = self._countdown_deadline - time.time()
        return max(0.0, min(1.0, remaining / total))

    def _countdown_flash_on(self):
        """倒计时结束后闪烁的相位：亮/暗各占半个周期，按当前时间切换。"""
        return (time.time() * COUNTDOWN_BLINK_HZ) % 1.0 < 0.5


def run():
    # 关闭 stdout 重定向带来的 GBK 编码问题
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not claim_single_instance():
        print("[i] 已经有一个实例在运行，不再重复启动。")
        notify_already_running()
        return 0

    service = HeatService().start()
    app = QApplication(sys.argv)
    app.setApplicationName("键盘热度")
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(service)
    dial.show()
    dial._enforce_topmost()   # 启动即声明一次置顶，不等看门狗第一拍
    # 「悬停时隐藏表盘」的轮询在 __init__ 里已按开关起停（默认关 → 不跑）。

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
