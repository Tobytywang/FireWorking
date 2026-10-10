"""Tkinter 版圆形仪表盘 —— 零第三方依赖的实现。

PyQt6 版（overlay.py）窗口效果更好：真透明、抗锯齿圆环、系统托盘。
这个版本只用标准库，代价是圆环边缘有锯齿、没有托盘图标（改成全局热键）。
两个版本共用 heatcore 里的同一套热度色阶，所以观感一致。

篝火模式这里同样有，但 Tk 的画力差得远：没有渐变、没有逐元素透明度、
没有叠加混合。所以火焰用「三层 smooth 多边形」近似，光晕用三层嵌套的
暗色椭圆伪装，火星用「向灶膛底色混色」冒充淡出。造型来自 flame.py 的
同一套几何函数，远看轮廓一致，近看没有 Qt 版的体积感 —— 这是刻意的
取舍：这个版本存在的意义是"零依赖也能跑"，不是"画得跟 Qt 一样好"。

点击穿透靠 Win32 扩展样式实现，和 PyQt6 版的 WindowTransparentForInput 等效：
    WS_EX_LAYERED      允许逐像素透明（配合 -transparentcolor 把圆形外的区域抠掉）
    WS_EX_TRANSPARENT  鼠标事件穿透到下层窗口
    WS_EX_TOOLWINDOW   不进任务栏、不占 Alt+Tab

因为窗口完全收不到鼠标事件，所有操作都走全局热键。热键用 pynput 的
GlobalHotKeys —— pynput 本来就是采集必需的依赖，不额外增加成本。
"""

from __future__ import annotations

import ctypes
import math
import os
import time
import tkinter as tk

from heatcore import (
    HeatService,
    cfg_get,
    cfg_set,
    claim_single_instance,
    heat_hex,
    log_countdown,
    notify_already_running,
    save_config,
)
import flame

START_DEG = 220.0
SWEEP_DEG = 260.0

TRANSPARENT_KEY = "#FF00FE"        # 抠色键，和界面配色不可能撞上

# 深色盘的底盘刻意比纯黑亮一档 —— 实测教训：深色圆盘叠在深色终端/壁纸上时，
# 盘面自身要和桌面拉开色差，否则整块会"糊"进背景，程序明明在跑却看着像没启动。
#
# **rim（描边）已去掉**（用户要求，与 Qt 版对齐）。这里原来写的是
# `outline=th["rim"], width=2`，而 Tk 版那个色是不透明亮灰（#8B96A8），
# 比盘面亮 120 左右，是一圈非常抢眼的白线 —— 用户报的"圈圈最外面有一个白色的
# 圆形线条"就是它。Qt 版同样去掉了（见 overlay.py draw 处的注释与
# `_rim_off_probe.py` 的实测表）。
#
# **`track_edge`（环外沿的描边）是另一回事**：它不是底盘的轮廓，而是**进度条自己的
# 边框** —— 用户报"透明度 72 的时候，进度条的底色和圆盘背景底色区分度太低"，要求
# 把边沿的设计挪到进度条上。轨道定色只解决了"弧 vs 轨道"，**轨道 vs 底盘**那一档
# 还得靠这条线切开（实测 dark α=72% 浅底 ΔRGB 只有 10.7）。理由和实测见 overlay.py
# 的 THEMES.track_edge 与 `_ring_edge_probe.py`。
#
# **线的透明度与底盘反相**（用户第 7 轮）：不透明度 = `flame.track_edge_alpha(bg_alpha)`
# = `1 − bg_alpha`，两版 UI 同一个公式。Tk 的 canvas item 没有逐元素 alpha，所以
# `_build_items` 里把线色按这个比例**混向它身下的颜色**（外弧/端头混底盘色、内弧混
# 灶膛色）来等价模拟 Qt 的 `setAlphaF`。
THEMES = {
    "dark": {
        "plate": "#181B23",
        "track": "#4A5261",
        "track_edge": "#C4CBD8",
        "text": "#F6F7FB",
        "muted": "#A9B0C0",
        # 盘芯（数字模式中央底）：与 CAMP_PIT_RGB 同色，两种模式的中央底一致。
        "center_bg": "#0E0C11",
    },
    "light": {
        "plate": "#FCFCFE",
        "track": "#C2C7D1",
        "track_edge": "#5F6674",
        "text": "#1A1C22",
        "muted": "#5F6674",
        # 盘芯（数字模式中央底）：浅色，暗字才压得住；100% 透明度时数字模式也有
        # 一块浅底，不再悬空（与篝火模式同半径，见 `_render_normal`）。
        "center_bg": "#ECEEF3",
    },
}

# 开屏动画：启动瞬间窗口全不透明，圆环扫一圈，1.4 秒后再淡回配置的透明度。
# 存在的意义就是回答"我到底起来没有" —— 之前是静默出现，深色桌面上根本发现不了。
BOOT_SWEEP_SECONDS = 1.4
IDLE_ARC_DEG = 2.5          # 完全空闲时保留的一小段弧，让表盘位置随时可见

STATE_LABEL = {
    "typing": "输出中",
    "pointing": "操作中",     # 只动鼠标、没打字
    "pause": "停顿",
    "idle": "空闲",
    "paused": "已暂停",
}

# 中心大数字的单位。鼠标活动已被折算成等效击键并进同一个热度，所以再叫 "KPM"
# 就不准确了 —— 改叫「活跃/分」，分母仍是 60 秒。
HEAT_UNIT = "活跃/分"

# 灶膛底色。Tk 没有透明度，这层只能画成实色 —— 好在底盘本来就是深色系，
# 实色的暗膛在两种 theme 下都不突兀。
CAMP_PIT_RGB = (14, 12, 17)
PAUSED_ARC = "#E0B02C"         # 暂停时圆环换琥珀色，和 Qt 版一致


def _hex(rgb):
    return "#%02X%02X%02X" % (rgb[0], rgb[1], rgb[2])


def _rgb(hex_str):
    """`#RRGGBB` → (r, g, b)。主题表里写的是十六进制，混合要拆成三个分量。"""
    s = hex_str.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _mixc(a, b, k):
    """Tk 版的颜色混合。k=0 → a，k=1 → b。火星的假淡出全靠它。"""
    return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))


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

# 倒计时（与 Qt 版同步的语义）：关闭 / 5 / 10 / 25 分钟。选时长后开始倒计时，
# 到点触发提示（篝火呼吸 / 数字「时间到」）；选「关闭」清除。Tk 版用热键
# <ctrl>+<alt>+t 循环切换（Tk 没有托盘菜单）。
COUNTDOWN_ENTRIES = [("5分钟", 5), ("10分钟", 10), ("25分钟", 25), ("关闭", 0)]

# 倒计时结束后的「呼吸」效果参数（篝火模式在小火/大火间往复），与 Qt 版一致。
COUNTDOWN_BREATHE_PERIOD = 2.6    # 一个呼吸周期的秒数
COUNTDOWN_FIRE_LOW = 0.16         # 小火（低热度）
COUNTDOWN_FIRE_HIGH = 0.95        # 大火（高热度）

# 倒计时进行 / 已触发期间，圆环（进度条）改表示倒计时进度，用这个固定色，
# 和「热度暖色」「暂停琥珀色」都区分开。与 Qt 版 COUNTDOWN_ARC_COLOR 同源。
COUNTDOWN_ARC_COLOR = "#3B82F6"

# 倒计时结束（_fired）后，整圈圆环**闪烁**提示时间到：亮/暗各占半个周期。
COUNTDOWN_BLINK_HZ = 2.0

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
GA_ROOT = 2
SPI_GETWORKAREA = 0x0030


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _monitor_work_areas():
    """所有显示器的『工作区』矩形（rcWork，已排除各屏任务栏），主屏排第一。

    Tk 没有多屏 API，走 Win32：EnumDisplayMonitors 枚举 + GetMonitorInfoW 取
    rcWork。主屏（含 (0,0) 的那块）排 index 0，这样 work_area(0) 永远等于旧行为
    的主屏，单屏时也与原来 SPI_GETWORKAREA 一致。
    """
    raw = []

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong),
                    ("rcMonitor", _RECT),
                    ("rcWork", _RECT),
                    ("dwFlags", ctypes.c_ulong)]

    def cb(hmonitor, hdc, lprect, lparam):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
            raw.append((mi.rcMonitor, mi.rcWork))
        return True

    enum_proc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(_RECT), ctypes.c_void_p)
    ctypes.windll.user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    ctypes.windll.user32.GetMonitorInfoW.restype = ctypes.c_bool
    ctypes.windll.user32.EnumDisplayMonitors.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, enum_proc, ctypes.c_void_p]
    ctypes.windll.user32.EnumDisplayMonitors.restype = ctypes.c_bool
    ctypes.windll.user32.EnumDisplayMonitors(0, 0, enum_proc(cb), 0)
    if not raw:
        return []
    # 主屏（含 (0,0) 的那块）排第一，保证 work_area(0) == 主屏
    primary = 0
    for i, (m, _w) in enumerate(raw):
        if m.left <= 0 < m.right and m.top <= 0 < m.bottom:
            primary = i
            break
    ordered = [raw[primary][1]] + [raw[i][1] for i in range(len(raw)) if i != primary]
    return [(r.left, r.top, r.right, r.bottom) for r in ordered]


def work_area(idx=0):
    """屏幕工作区（已排除任务栏）。idx=0 为主屏；多屏时 idx 取对应显示器。

    单屏退化路径仍走 SPI_GETWORKAREA，与原行为一致。
    """
    areas = _monitor_work_areas()
    if not areas:
        rect = _RECT()
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        if not ok:
            return 0, 0, ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
        return rect.left, rect.top, rect.right, rect.bottom
    return areas[idx % len(areas)]


class HeatDialTk:
    def __init__(self, service: HeatService):
        self.service = service
        cfg = service.config.get("overlay", {})
        self.cfg = cfg
        self.theme = THEMES.get(cfg_get(cfg, "theme", "dark"), THEMES["dark"])
        self.size = int(cfg_get(cfg, "size", 176))
        # 原样的底盘不透明度（0~1）—— 环带轮廓线的透明度由它反相得来
        # （`flame.track_edge_alpha`），所以要把未夹取的配置值留着；
        # `win_alpha` 是**整窗**用的，Tk 不允许窗口全透明，最低夹到 0.15。
        self.cfg_alpha = max(0.0, min(1.0, float(cfg_get(cfg, "bg_alpha", 0.72))))
        self.win_alpha = max(0.15, self.cfg_alpha)
        self.snap = {"heat": 0.0, "kpm": 0, "peak": 0.0, "state": "idle"}
        self.visible = True
        self._hotkeys = None

        self._boot_start = time.time()
        self._boot_done = False
        self._campfire = bool(cfg_get(cfg, "campfire", True))
        # 木柴样式（flat / bark / charred / gnarled），见 flame.LOG_STYLES
        self._log_style = str(cfg_get(cfg, "log_style", flame.LOG_STYLE_DEFAULT))
        # 位图柴堆（相对项目根目录的 PNG 路径；空 = 代码绘制三对柴塔 + 端向柴）。
        # 后景画在火焰后面，前景画在火焰前面（压住火焰下半段和平直底边）。
        self._log_image = str(cfg_get(cfg, "log_image", flame.LOG_IMAGE_DEFAULT))
        self._log_image_obj = None      # flame.LogImage，加载一次缓存
        self._log_photo = None          # ImageTk.PhotoImage（必须挂住，否则被 GC）
        self._log_image_front = str(
            cfg_get(cfg, "log_image_front", flame.LOG_IMAGE_DEFAULT))
        self._log_image_front_obj = None
        self._log_photo_front = None
        # 底火层：固定高度的一层暗火，低热时也压住柴堆的炭化柴尖（见 flame.FLAME_FLOOR_*）
        self._flame_floor = bool(cfg_get(cfg, "flame_floor", True))
        self._phase = 0.0            # 火苗摇曳的时间相位
        self._last_t = None
        # 已探测到的显示器数量（用于热插拔后重新落位）。
        self._mon_count = len(_monitor_work_areas()) or 1
        self._sparks = flame.SparkField()
        # 倒计时：选时长后才开始（不写盘，一次性）。_fired 后触发提示效果，
        # 一直持续到用户用热键循环到「关闭」或换一个时长。
        self._countdown_min = 0
        self._countdown_deadline = None
        self._fired = False
        self._fire_start = 0.0

        self.root = tk.Tk()
        self._setup_window()
        self.canvas = tk.Canvas(
            self.root, width=self.size, height=self.size,
            highlightthickness=0, bd=0, bg=TRANSPARENT_KEY,
        )
        self.canvas.pack()
        self._build_items()
        self._build_camp_items()
        self._show_camp(self._campfire)      # 初始按配置决定显示哪套
        self._bind_hotkeys()
        self._preload_log_images()       # 窗口显示前同步解码柴堆 PNG，首帧不再卡（~232ms）
        self.root.after(50, self._tick)

    # ---------------- 启动优化 ----------------

    def _preload_log_images(self):
        """窗口显示前同步解码位图柴堆 PNG（后景 + 前景），避免首帧渲染卡顿。

        原实现在渲染循环里惰性解码（self._log_image_obj is None 时），两张大图
        （2560×1440 / 2560×1400）的 PIL 解码 + 抠底约 232ms，会让「窗口出现后的
        第一帧」明显顿一下。Tk 单线程无法像 Qt 那样丢到 daemon 线程
        （PhotoImage 必须在主线程建），所以这里在 __init__ 里、窗口与事件循环
        启动之前就把解码 + PhotoImage 包装完成——总启动耗时不变，但消除了
        「窗口已可见却卡一下」的观感。渲染循环里的惰性分支保留作兜底
        （解码失败 / 路径为空时退回代码绘制或重试）。
        """
        back, front = self._log_image, self._log_image_front
        if not back and not front:
            return
        from PIL import Image, ImageTk
        if back and self._log_image_obj is None:
            li = flame.log_image_load(back)
            if li is not None:
                self._log_image_obj = li
                self._log_photo = ImageTk.PhotoImage(
                    Image.frombytes("RGBA", (li.w, li.h), li.data))
        if front and self._log_image_front_obj is None:
            li = flame.log_image_load(front, slot="front")
            if li is not None:
                self._log_image_front_obj = li
                self._log_photo_front = ImageTk.PhotoImage(
                    Image.frombytes("RGBA", (li.w, li.h), li.data))

    # ---------------- 窗口 ----------------

    def _setup_window(self):
        r = self.root
        r.title("键盘热度")
        r.overrideredirect(True)                       # 无边框
        r.attributes("-topmost", True)                 # 置顶
        r.configure(bg=TRANSPARENT_KEY)
        try:
            r.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass                                       # 非 Windows 平台没有这个属性
        # 启动即使用配置的整窗透明度（win_alpha），与开屏后保持一致，
        # 避免「开屏不透明 → 开屏后透明」的突兀切换。开屏扫圈照常播放。
        r.attributes("-alpha", self.win_alpha)
        self._place()
        r.update_idletasks()
        self._set_click_through()
        # 置顶看门狗：周期性重新声明 -topmost，抵消运行中被动降格（见 _topmost_watchdog）。
        self.root.after(1000, self._topmost_watchdog)
        # 显示器数量变化时重新落位（热插拔保护），2s 探一次。
        self.root.after(2000, self._screen_watchdog)

    def _place(self):
        idx = int(cfg_get(self.cfg, "screen", 0))
        left, top, right, bottom = work_area(idx)
        margin = int(cfg_get(self.cfg, "margin", 28))
        pos = cfg_get(self.cfg, "position", "bottom-right")
        w = h = self.size
        x = (right - w - margin) if "right" in pos else (left + margin)
        y = (bottom - h - margin) if "bottom" in pos else (top + margin)
        self.root.geometry("%dx%d+%d+%d" % (w, h, int(x), int(y)))

    def _set_click_through(self):
        """把窗口标记成"看得见、摸不着"。"""
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW,
            )
        except Exception as exc:
            print("[!] 点击穿透设置失败（窗口会挡住鼠标）：%s" % exc)

    def _topmost_watchdog(self):
        """周期性重新声明 -topmost，抵消运行中被动降格。

        与 Qt 版 _enforce_topmost 同目的：普通最大化窗本不该盖住置顶层，但 Tk 的
        -topmost 在别的窗口被前置 / 最大化时偶尔会被动失效，这里每秒重新置顶一次。
        不抢焦点（attributes 置顶不改激活态），不打断用户当前操作。
        """
        try:
            self.root.attributes("-topmost", True)
        except Exception:
            pass
        self.root.after(1000, self._topmost_watchdog)

    # ---------------- 绘制元素 ----------------

    def _edge_colors(self):
        """环带轮廓线的两个**等效**颜色 —— Tk 没有逐元素 alpha，只能混色模拟。

        把线色按 `keep` 的比例混向它身下那块颜色：
          · 外弧 + 两个端头：身下是底盘
          · 内弧：身下是灶膛（篝火模式）／底盘
        `keep = flame.track_edge_alpha(cfg 的底盘不透明度)`，与 Qt 版的
        `setAlphaF` **同源**，不许各写一套（双 UI 分叉是踩过的坑）。
        """
        th = self.theme
        keep = flame.track_edge_alpha(self.cfg_alpha)
        edge_out = _hex(_mixc(_rgb(th["plate"]), _rgb(th["track_edge"]), keep))
        # 内弧身下那块色 = 盘中央的底：篝火模式是灶膛，数字模式是盘芯（THEMES.center_bg）。
        # 两种模式这块底都在同一半径上（见 _render_camp / _render_normal），所以内弧的
        # 混色底也要跟着模式走，不能写死底盘 —— 否则亮主题数字模式下内弧会比它身下的
        # 浅色盘芯偏亮，露出一条线。
        under_in = CAMP_PIT_RGB if self._campfire else _rgb(th["center_bg"])
        edge_in = _hex(_mixc(under_in, _rgb(th["track_edge"]), keep))
        return edge_out, edge_in

    def _sync_edge_colors(self):
        """把等效色写回那三组 item。

        建的时候要用，篝火 ⇄ 数字切换时**也要** —— 内弧身下的颜色在那两种模式下
        是灶膛/底盘两块不同的色。Qt 版每帧重绘，没有这个问题。
        """
        if getattr(self, "i_edge", None) is None:
            return
        out, inn = self._edge_colors()
        self.canvas.itemconfig(self.i_edge, outline=out)
        for item in self.i_edge_caps:
            self.canvas.itemconfig(item, outline=out)
        self.canvas.itemconfig(self.i_edge_in, outline=inn)

    def _build_items(self):
        c = self.canvas
        d = self.size
        th = self.theme
        thick = int(round(flame.ring_thick(d)))
        pad = max(2, int(round(d * 0.012)))
        radius = flame.ring_radius(d)
        box = (d / 2.0 - radius, d / 2.0 - radius, d / 2.0 + radius, d / 2.0 + radius)

        # 不画描边（与 Qt 版一致，见 THEMES 上面的说明）
        self.i_plate = c.create_oval(pad, pad, d - pad, d - pad,
                                     fill=th["plate"], outline="", width=0)
        # 盘中央的底（篝火=灶膛 / 数字=盘芯）**必须先于环带轮廓建**：Tk 的层序 =
        # 创建顺序，它和轮廓内弧只差 1.5px，晚建就把内弧盖掉半条（Qt 版同理，见
        # overlay.py）。坐标/颜色每帧由 `_render_camp` / `_render_normal` 各自设；
        # 它**不属于 `_camp_items`**，两种模式都常驻（见 `_camp_items` 处的说明）。
        self.i_pit = c.create_oval(0, 0, 0, 0, fill=_hex(CAMP_PIT_RGB), outline="")
        # 环带轮廓：外弧 + 内弧 + 两个端头半圆（与 Qt 版的 QPainterPath 同几何）。
        # Tk 没有 z-index，层序 = 创建顺序，所以这一组必须建在 i_track **之前**
        # （后建的压在上面）。端头半圆以**环中心线**为圆心、半径取
        # thick/2 + edge_w/2 —— 正好包住轨道的圆笔帽，末尾那个圆头也被圈在里面。
        edge_w = max(2, int(round(flame.ring_edge_w(d))))
        r_out = flame.ring_edge_radius(d)
        r_in = flame.ring_edge_inner_radius(d)
        cap_r = flame.ring_edge_cap_radius(d)
        mid_r = (r_out + r_in) / 2.0                       # = ring_radius(d)
        end_deg = START_DEG - SWEEP_DEG
        hub = d / 2.0
        # Tk 的 canvas item **没有逐元素 alpha**（`-alpha` 是整窗的），所以这里用
        # **颜色混合**等价模拟 Qt 的 `setAlphaF`：见 `_edge_colors`。
        edge_out, edge_in = self._edge_colors()
        self.i_edge = c.create_arc(
            hub - r_out, hub - r_out, hub + r_out, hub + r_out,
            start=START_DEG, extent=-SWEEP_DEG,
            style="arc", outline=edge_out, width=edge_w)
        self.i_edge_in = c.create_arc(
            hub - r_in, hub - r_in, hub + r_in, hub + r_in,
            start=START_DEG, extent=-SWEEP_DEG,
            style="arc", outline=edge_in, width=edge_w)
        self.i_edge_caps = []
        for _deg, _sgn in ((end_deg, -1.0), (START_DEG, 1.0)):
            _a = math.radians(_deg)
            _ex = hub + mid_r * math.cos(_a)
            _ey = hub - mid_r * math.sin(_a)
            _start = _deg if _sgn < 0 else _deg + 180.0
            self.i_edge_caps.append(c.create_arc(
                _ex - cap_r, _ey - cap_r, _ex + cap_r, _ey + cap_r,
                start=_start, extent=-180.0,
                style="arc", outline=edge_out, width=edge_w))
        self.i_track = c.create_arc(*box, start=START_DEG, extent=-SWEEP_DEG,
                                    style="arc", outline=th["track"], width=thick)
        self.i_heat = c.create_arc(*box, start=START_DEG, extent=-1,
                                   style="arc", outline=heat_hex(0), width=thick,
                                   state="hidden")

        self._dot_r = max(3.0, d * 0.019)
        self._dot_y = d / 2.0 - d * 0.193

        # ⚠ **文字可读性的兜底只在 Qt 版有**（`overlay._hud_text` 给每段文字描一圈反相
        # 光晕）。Tk 的 canvas item **没有逐元素 alpha**、文字也不能描边，窗口整体靠
        # `-alpha`（`win_alpha`）透明 —— 底盘调透明时文字会**跟着一起淡**。所以透明度
        # 拉很低时 Tk 版文字本就糊，没法用同一招救。需要「底盘透明但文字仍清晰」就用
        # Qt 版（`main.py` 默认优先 Qt）。这一条不改 Tk 渲染，只留个话，免得下次有人
        # 只改一边还以为两边一致。
        self.i_dot = c.create_oval(0, 0, 0, 0, fill=th["muted"], outline="")
        self.i_state = c.create_text(0, self._dot_y, text="空闲", fill=th["text"],
                                     anchor="w",
                                     font=("Microsoft YaHei", -max(11, int(d * 0.068))))
        # 中心大数字 = 综合活跃度（键盘 + 鼠标折算后并进同一个热度）
        self.i_kpm = c.create_text(d / 2.0, d / 2.0, text="0", fill=th["muted"],
                                   font=("Consolas", -max(18, int(d * 0.20)), "bold"))
        self.i_unit = c.create_text(d / 2.0, d / 2.0 + d * 0.150, text=HEAT_UNIT,
                                    fill=th["muted"],
                                    font=("Microsoft YaHei", -max(10, int(d * 0.058))))
        # 键 / 鼠 分解：回答"这份热度是敲出来的还是划出来的"
        self.i_split = c.create_text(d / 2.0, d / 2.0 + d * 0.232, text="",
                                     fill=th["muted"],
                                     font=("Microsoft YaHei", -max(9, int(d * 0.055))))
        self.i_peak = c.create_text(d / 2.0, d / 2.0 + d * 0.312, text="峰值 0",
                                    fill=th["muted"],
                                    font=("Microsoft YaHei", -max(9, int(d * 0.054))))
        # 倒计时到点后的「时间到」提示（数字模式专用）。建在最后 → 压在其它数字之上；
        # 不属于 `_camp_items`，只有数字模式用，平时隐藏。
        self.i_timeout = c.create_text(d / 2.0, d / 2.0, text="", fill=th["text"],
                                       anchor="center", state="hidden",
                                       font=("Microsoft YaHei", -max(20, int(d * 0.16)), "bold"))
        self._center_state_row()

    # ---------------- 篝火画素 ----------------

    def _build_camp_items(self):
        """篝火模式的全套画素。Tk 不能"画完就扔"，只能先全部建好、每帧改
        坐标和颜色 —— 项的数量固定，多余的火星用 state=hidden 藏起来。"""
        c = self.canvas

        # 灶膛（i_pit）不在这儿建 —— 它在 `_build_items` 里、环带轮廓**之前**就建好了，
        # 否则会把轮廓内弧盖掉半条（理由见那里的注释）。

        # 光晕：四层嵌套椭圆，由外向内一层比一层暖 —— 伪装径向衰减。
        # Tk 做不了加法混合，这是不引入图片素材的前提下唯一像样的替代。
        self.i_glow = [
            c.create_oval(0, 0, 0, 0, fill="", outline="") for _ in range(4)
        ]

        # 炭火床：画在柴堆**下面**。Qt 版是半透明径向渐变，叠在柴上也无妨；
        # Tk 版是实色椭圆，叠上去会把柴的中段整个盖掉 —— 顺序必须是
        # 灶膛 → 光晕 → 炭火床 → 柴堆 → 火焰。
        self.i_ember = c.create_oval(0, 0, 0, 0, fill="", outline="")

        # 后对柴堆：数量按最复杂样式的上限建（flame.LOG_ITEMS_MAX），
        # 简单样式用不到的项每帧藏起来。多边形支持 smooth，断面圆环才不是三角块。
        self.i_logs = [
            c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True, outline="")
            for _ in range(flame.LOG_ITEMS_MAX)
        ]

        # 中对柴堆：填后对与前垛之间的空档。建在 i_logs 之后、i_flames 之前
        # —— 层叠仍在火焰后面，但盖住后对（物理上它靠观众那一侧）。
        self.i_mid_logs = [
            c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True, outline="")
            for _ in range(flame.LOG_ITEMS_MAX)
        ]

        # 后景位图柴堆：开启 log_image 后用它代替后对/中对柴塔的代码绘制。
        # 建在 i_mid_logs 之后、i_floor 之前 —— 仍在火焰**下面**（与 Qt 版一致：
        # 后景柴堆先画，火焰压在上面）。PhotoImage 一生成所有引用失效，必须挂 self。
        self._log_photo = None
        self.i_log_img = c.create_image(0, 0, image=None, state="hidden")

        # 底火层：固定跨度的一层暗火，压在柴尖上不随热度缩（见 flame.FLAME_FLOOR_*）。
        # 建在 i_flames 之前 → 位于主火**下面**：高热时被主火包住看不出，
        # 低热时它就是唯一可见的那层火，负责盖住柴堆的炭化黑尖。
        self.i_floor = c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True, outline="")

        # 火焰三层：外焰 → 中焰 → 焰芯。smooth=True 让折线趋近曲线。
        self.i_flames = [
            c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True, outline="")
            for _ in range(len(flame.LAYERS))
        ]

        # 前对柴堆：横卧在火前，**建在火焰之后**才压在火焰上面 —— Tk 的层叠
        # 顺序就是创建顺序，这一点和 Qt 版的绘制顺序一一对应。
        self.i_front_logs = [
            c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True, outline="")
            for _ in range(flame.LOG_ITEMS_MAX)
        ]

        # 端向柴：最前面一根，**建在前对柴之后**才压在所有火焰图层之上，
        # 挡住火焰那条直底边从柴塔缝隙里漏出来。数量按 flame.FORE_ITEMS_MAX。
        self.i_fore_logs = [
            c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True, outline="")
            for _ in range(flame.FORE_ITEMS_MAX)
        ]

        # 前景位图柴堆：建在端向柴之后、火星之前 —— 压在**所有**火焰图层之上，
        # 专门遮掉火焰的下半段和平直底边（等价于 Qt 版的 log_image_front 那一步）。
        self._log_photo_front = None
        self.i_log_front = c.create_image(0, 0, image=None, state="hidden")

        # 火星：数量取 SparkField 的上限（2 + 7）
        self.i_sparks = [
            c.create_oval(0, 0, 0, 0, fill="", outline="", state="hidden")
            for _ in range(9)
        ]

        # ⚠ i_pit（盘中央的底）**不在这个列表里**：它是**两种模式共用**的 ——
        # 篝火模式当灶膛（深色），数字模式当盘芯（THEMES.center_bg）。`_show_camp`
        # 会把 `_camp_items` 整组 hide，i_pit 若留在组里，切到数字模式就连盘芯一起
        # 消失、文字又悬空（正是用户报的"割裂"）。所以它只建一次、永远可见，
        # 颜色和半径每帧由 `_render_camp` / `_render_normal` 各自设。
        self._camp_items = (self.i_glow + [self.i_ember]
                            + self.i_logs + self.i_mid_logs
                            + [self.i_log_img, self.i_floor]
                            + self.i_flames + self.i_front_logs
                            + self.i_fore_logs + [self.i_log_front]
                            + self.i_sparks)

    def _show_camp(self, show):
        """篝火 ⇄ 数字仪表盘的切换，本质就是两套画素互.hide。"""
        c = self.canvas
        state = "normal" if show else "hidden"
        for item in self._camp_items:
            c.itemconfig(item, state=state)
        for item in (self.i_dot, self.i_state, self.i_kpm,
                     self.i_unit, self.i_split, self.i_peak):
            c.itemconfig(item, state="hidden" if show else "normal")

    def _render_camp(self, now):
        """篝火模式的每一帧：几何全部重算，颜色跟着热度走。"""
        c = self.canvas
        d = self.size
        cx = d / 2.0
        cy = d / 2.0

        booting = not self._boot_done
        boot_t = 0.0
        if booting:
            boot_t = (now - self._boot_start) / BOOT_SWEEP_SECONDS
            if boot_t >= 1.0:
                self._boot_done = True
                booting = False

        snap = self.snap
        frac = max(0.0, min(1.0, float(snap.get("heat", 0.0)) / 100.0))
        state = snap.get("state", "idle")
        heat = flame.fire_heat(frac, state, booting, boot_t)
        # 倒计时到点 → 篝火做呼吸：在小火/大火之间反复变更，盖过真实热度。
        # 开屏期间不抢戏（booting 时火在"点燃"，heat 由 boot_t 驱动）。
        if self._fired and not booting:
            heat = self._breathe_heat()

        # 圆环：开屏扫一圈、空闲留一小段、暂停换琥珀色；倒计时进行/已触发时
        # 改表示倒计时进度（已用时间占比），不再表示热度。
        cd = self._countdown_progress()
        if booting:
            c.itemconfig(self.i_heat, state="normal",
                         extent=-SWEEP_DEG * boot_t, outline=heat_hex(boot_t))
        elif cd == "flash":
            # 倒计时结束：整圈闪烁提示时间到。亮帧画满圈蓝弧，暗帧隐藏（整圈消失）。
            if self._countdown_flash_on():
                c.itemconfig(self.i_heat, state="normal",
                             extent=-SWEEP_DEG, outline=COUNTDOWN_ARC_COLOR)
            else:
                c.itemconfig(self.i_heat, state="hidden")
        elif cd is not None:
            c.itemconfig(self.i_heat, state="normal",
                         extent=-SWEEP_DEG * cd, outline=COUNTDOWN_ARC_COLOR)
        elif state == "paused":
            c.itemconfig(self.i_heat, state="normal",
                         extent=-SWEEP_DEG * max(frac, IDLE_ARC_DEG / SWEEP_DEG),
                         outline=PAUSED_ARC)
        elif frac > IDLE_ARC_DEG / SWEEP_DEG:
            # 阈值用"下限弧长"而不是一个小常数 0.002 —— 否则热度刚从 0 起来时
            # 弧长会先缩到 0.5° 再重新长，热度升而弧变短（非单调的小跳变）。
            c.itemconfig(self.i_heat, state="normal",
                         extent=-SWEEP_DEG * frac, outline=heat_hex(frac))
        else:
            c.itemconfig(self.i_heat, state="normal",
                         extent=-IDLE_ARC_DEG, outline=heat_hex(0.0))

        # 盘中央的底（半径公式在 flame 里，两版共用）。篝火模式下它就是灶膛：暗色，
        # 给火当底。半径与数字模式的盘芯**完全相同**，所以两模式切来切去这块圆盘的
        # 位置/大小不变，只有颜色（灶膛 ⇄ 盘芯）和里面的内容在换。
        pit_r = flame.pit_radius(d)
        c.coords(self.i_pit, cx - pit_r, cy - pit_r, cx + pit_r, cy + pit_r)
        c.itemconfig(self.i_pit, fill=_hex(CAMP_PIT_RGB))

        # 火的几何 —— 与 Qt 版同一套函数，见 flame.py。root_y/h/w 是主火形状的
        # 底边 / 跨度 / 宽度；anchor_y 是**起火点**（柴堆交叉处），光晕和炭火床
        # 跟着它走 —— 低热时那团火是在炭化点上，不是从盘底往上伸。
        base_y = flame.flame_base_y(cy, d)
        fg = flame.flame_geom(cx, cy, d, heat, self._log_image_obj)
        root_y, h, w = fg.root_y, fg.span, fg.w
        outer, mid, core = flame.flame_colors(heat)

        # 光晕四层（由外向内），颜色从灶膛底色往火色混 —— Tk 做不了加法混合，
        # 只能拿实色椭圆伪装径向衰减；层数多一层，色带就少一道。
        # 半径必须封在灶膛以内：这些椭圆是实色不透明的，一旦超出底盘画到
        # 透明区，桌面上就会多出一块方方正正的棕色补丁。
        gx, gy = cx, root_y - h * 0.28
        for i, (kr, kc) in enumerate(((1.00, 0.07), (0.72, 0.13),
                                      (0.48, 0.19), (0.28, 0.27))):
            r = min(h * kr + d * 0.03, pit_r)
            c.coords(self.i_glow[i],
                     gx - r, gy - r * 0.72, gx + r, gy + r * 0.72)
            c.itemconfig(self.i_glow[i], fill=_hex(_mixc(CAMP_PIT_RGB, mid, kc)))

        # 位图后景柴堆：加载（一次）+ 定位（每帧，随盘尺寸）。开启后隐藏代码柴塔。
        if self._log_image and self._log_image_obj is None:
            li = flame.log_image_load(self._log_image)
            if li is not None:
                from PIL import Image, ImageTk
                self._log_image_obj = li
                self._log_photo = ImageTk.PhotoImage(
                    Image.frombytes("RGBA", (li.w, li.h), li.data))
        if self._log_photo is not None:
            lx, ly, lw, lh = self._log_image_obj.box(cx, cy, d)
            c.itemconfig(self.i_log_img, state="normal",
                         image=self._log_photo)
            c.coords(self.i_log_img, lx + lw / 2.0, ly + lh / 2.0)
            for grp in (self.i_logs, self.i_mid_logs):
                for item in grp:
                    c.itemconfig(item, state="hidden")
        else:
            c.itemconfig(self.i_log_img, state="hidden")

        # 后对柴堆：几何全部来自 flame.log_pile，这里只是把点连成面。
        # 画法在 Tk 上被限制得很死（不能旋转、没有渐变、没有透明度），所以
        # 木头做成了「多边形清单」—— 同一条清单 Qt 也照着画。
        if self._log_photo is None:
            draw = flame.log_draw_list(
                flame.log_pile(cx, base_y, d, heat, mid, self._log_style))
            for i, item in enumerate(self.i_logs):
                if i >= len(draw):
                    c.itemconfig(item, state="hidden")
                    continue
                pts, col = draw[i]
                c.coords(item, *[v for pt in pts for v in pt])
                c.itemconfig(item, state="normal", fill=_hex(col))

        # 中对柴堆：火焰后面、后对之上，填两截柴塔之间的空档
        if self._log_photo is None:
            draw = flame.log_draw_list(
                flame.log_pile(cx, base_y, d, heat, mid, self._log_style,
                               pair="mid"))
            for i, item in enumerate(self.i_mid_logs):
                if i >= len(draw):
                    c.itemconfig(item, state="hidden")
                    continue
                pts, col = draw[i]
                c.coords(item, *[v for pt in pts for v in pt])
                c.itemconfig(item, state="normal", fill=_hex(col))

        # 炭火：半径不跟火苗缩放（同样为了"没火时也有锚点"），亮度跟热度走。
        # Tk 没有透明度，只能用向底色混色冒充明暗。
        ew = max(w * 0.60, d * 0.15)
        eh = ew * 0.70
        c.coords(self.i_ember, cx - ew, base_y - eh, cx + ew, base_y + eh)
        c.itemconfig(self.i_ember,
                     fill=_hex(_mixc(CAMP_PIT_RGB, core, 0.16 + 0.52 * heat)))

        # 底火层：跨度固定、压暗配色（几何与配色调的是 Qt 版同一套函数）。
        # 跨度与主火无关 —— 低热时它反而比主火高，那正是它的用武之地。
        flg = (flame.flame_floor_geom(cx, cy, d, self._log_image_obj)
               if self._flame_floor else None)
        if flg is not None:
            fb, ft = flame.flame_floor_colors(heat)
            pts = flame.outline(cx, flg.root_y, flg.span, flg.w,
                                self._phase, flame.FLAME_FLOOR_SEED)
            flat = []
            for x, y in pts:
                flat.append(x)
                flat.append(y)
            c.coords(self.i_floor, *flat)
            # Tk 没有渐变，用一个中间色冒充（火焰三层也是这个手法）
            c.itemconfig(self.i_floor, state="normal",
                         fill=_hex(flame._mix(fb, ft, 0.50)))
        else:
            c.itemconfig(self.i_floor, state="hidden")

        # 火焰三层
        for i, (shrink, seed) in enumerate(flame.LAYERS):
            pts = flame.outline(cx, root_y, h, w, self._phase, seed, shrink)
            flat = []
            for x, y in pts:
                flat.append(x)
                flat.append(y)
            c.coords(self.i_flames[i], *flat)
            if i == 0:
                # 外焰压暗：往灶膛底色混。0.86 是与 Qt 的 _L1_KEEP 对应的"保留
                # 比例"，所以本轮给 Qt 加的第 1 层提亮在这里必须一起跟 —— 都乘
                # flame._l12_weight：空闲档为 0，Tk 的外焰与验收时逐像素相同。
                k_edge = (flame._L1_TK_KEEP
                          + flame._L1_TK_KEEP_UP * flame._l12_weight(heat))
                fill = _hex(_mixc(CAMP_PIT_RGB, outer, k_edge))
            elif i == 1:
                # 本轮提亮：按热度往焰芯色混一点。Qt 那边是把纵向渐变的顶端
                # 保留比例抬高（_L2_KEEP_UP），Tk 画不了渐变，混色是等效写法。
                fill = _hex(_mixc(mid, core,
                                  flame._L2_TK_MIX_UP * flame._l12_weight(heat)))
            else:
                # 焰芯提亮。0.30 乘热度折扣 —— 冷态不提亮，否则柴堆交叉点上
                # 会出现一块灰白的"芯"（见 flame.flame_core_lift_k）。
                #
                # 往什么白里混，必须跟 Qt 同源：原来这里是硬编码的
                # `(255, 255, 255)` —— **中性白**，跟 Qt 那版 _CORE_TINT 的
                # (255,250,224) 一样会把焰芯的暖意冲掉（R−G 被稀释），观感
                # 就是用户说的"绿/灰"。现在两版都走 flame._CORE_TINT（暖白）。
                #
                # Tk 没有 _L3_KEEP_UP 这一档：Qt 的焰芯中位亮度只有 V59.6 是
                # 因为纵向渐变把上半段压暗了，而 Tk 画的是实色 core（V≈98），
                # 本来就处在"提亮之后"的状态，没有可提的顶端。
                k = 0.30 * flame.flame_core_lift_k(heat)
                fill = _hex(_mixc(core, flame._CORE_TINT, k))
            c.itemconfig(self.i_flames[i], fill=fill)

        if self._log_photo_front is None:
            # 前对柴堆：压在最上面（背光版配色，见 flame.log_pile 的 pair 参数）
            draw = flame.log_draw_list(
                flame.log_pile(cx, base_y, d, heat, mid, self._log_style,
                               pair="front"))
            for i, item in enumerate(self.i_front_logs):
                if i >= len(draw):
                    c.itemconfig(item, state="hidden")
                    continue
                pts, col = draw[i]
                c.coords(item, *[v for pt in pts for v in pt])
                c.itemconfig(item, state="normal", fill=_hex(col))

            # 端向柴：最前面一根，压在所有火焰图层之上，遮住火焰平底边漏出的缝
            draw = flame.fore_draw_list(
                flame.log_fore(cx, base_y, d, heat, mid, self._log_style))
            for i, item in enumerate(self.i_fore_logs):
                if i >= len(draw):
                    c.itemconfig(item, state="hidden")
                    continue
                pts, col = draw[i]
                c.coords(item, *[v for pt in pts for v in pt])
                c.itemconfig(item, state="normal", fill=_hex(col))
        else:
            for grp in (self.i_front_logs, self.i_fore_logs):
                for item in grp:
                    c.itemconfig(item, state="hidden")

        # 位图前景柴堆：压在所有火焰图层之上，遮掉火焰下半段和平直底边。
        if self._log_image_front and self._log_image_front_obj is None:
            li = flame.log_image_load(self._log_image_front, slot="front")
            if li is not None:
                from PIL import Image, ImageTk
                self._log_image_front_obj = li
                self._log_photo_front = ImageTk.PhotoImage(
                    Image.frombytes("RGBA", (li.w, li.h), li.data))
        if self._log_photo_front is not None:
            lx, ly, lw, lh = self._log_image_front_obj.box(cx, cy, d)
            c.itemconfig(self.i_log_front, state="normal",
                         image=self._log_photo_front)
            c.coords(self.i_log_front, lx + lw / 2.0, ly + lh / 2.0)
        else:
            c.itemconfig(self.i_log_front, state="hidden")

        # 火星：Tk 没有透明度，用"向灶膛底色混色"冒充淡出。
        # 跨度取两层里大的那个（与 Qt 版一致）—— 低热时底火层比主火高，
        # 火星得从**看得见的**火焰顶端冒出去。
        field = None if state == "paused" else self._sparks
        h_spark = max(h, flg.span if flg is not None else 0.0)
        sparks = (field.at(self._phase, heat, cx, root_y, h_spark)
                  if field else [])
        for i, item in enumerate(self.i_sparks):
            if i >= len(sparks):
                c.itemconfig(item, state="hidden")
                continue
            sx, sy, sr, sa = sparks[i]
            c.coords(item, sx - sr, sy - sr, sx + sr, sy + sr)
            c.itemconfig(item, state="normal",
                         fill=_hex(_mixc(CAMP_PIT_RGB, core, max(0.15, sa))))

    def _center_state_row(self):
        """状态点是活的，文字宽度会变，每帧重新把「点 + 文字」整体居中。"""
        c = self.canvas
        gap = self.size * 0.026
        bbox = c.bbox(self.i_state)
        if not bbox:
            return
        text_w = bbox[2] - bbox[0]
        total = self._dot_r * 2 + gap + text_w
        start_x = self.size / 2.0 - total / 2.0
        c.coords(self.i_state, start_x + self._dot_r * 2 + gap, self._dot_y)
        c.coords(self.i_dot,
                 start_x, self._dot_y - self._dot_r,
                 start_x + self._dot_r * 2, self._dot_y + self._dot_r)

    # ---------------- 刷新 ----------------

    def _tick(self):
        now = time.time()
        # 倒计时到点 → 触发提示（篝火呼吸 / 数字「时间到」）。提示一直持续到用户
        # 用热键循环到「关闭」或换一个时长（都会把 _fired 清掉）。
        if self._countdown_min > 0 and not self._fired \
                and self._countdown_deadline is not None \
                and now >= self._countdown_deadline:
            self._fired = True
            self._fire_start = now
        if self._campfire and self._last_t is not None:
            self._phase += min(0.5, now - self._last_t)   # 摇曳的时间相位
        self._last_t = now
        self.snap = self.service.snapshot()
        self._render()
        # 篝火要跑摇曳动画，250ms 一步会明显"跳"，压到 80ms；倒计时进行/已触发
        # 时也要 80ms —— 圆环要平滑耗尽、到点后还要整圈闪烁。
        interval = (80 if (self._campfire or self._countdown_min > 0)
                    else max(80, int(cfg_get(self.cfg, "refresh_ms", 250))))
        self.root.after(interval, self._tick)

    def _render(self):
        now = time.time()
        if self._campfire:
            self._render_camp(now)          # 开屏/稳态都在里面处理
        elif not self._boot_done:
            self._render_boot(now)
        else:
            self._render_normal()

    def _render_boot(self, now):
        """开屏扫一圈 —— 让用户一眼确认"它确实起来了"。"""
        c = self.canvas
        t = (now - self._boot_start) / BOOT_SWEEP_SECONDS
        if t >= 1.0:
            self._boot_done = True
            return
        c.itemconfig(self.i_heat, state="normal",
                     extent=-SWEEP_DEG * t, outline=heat_hex(t))
        c.itemconfig(self.i_kpm, text="就绪", fill=heat_hex(t))
        c.itemconfig(self.i_split, text="")
        c.itemconfig(self.i_peak, text="键鼠热度已启动")
        c.itemconfig(self.i_state, text="")
        c.itemconfig(self.i_dot, fill=heat_hex(t))
        self._center_state_row()

    def _render_normal(self):
        c = self.canvas
        snap = self.snap
        frac = max(0.0, min(1.0, float(snap.get("heat", 0.0)) / 100.0))
        state = snap.get("state", "idle")

        # 盘中央的底：数字模式下换成盘芯（THEMES.center_bg）。100% 透明度时若没有它，
        # 文字会悬在桌面上，而篝火模式中央却是一块深色灶膛 —— 两模式切来切去割裂
        # （用户报）。半径与灶膛**完全相同**（flame.pit_radius），颜色随主题取
        # （dark 是与灶膛同色的深色，light 是浅色 —— 暗字要浅底才压得住）。
        d = self.size
        pit_r = flame.pit_radius(d)
        c.coords(self.i_pit, d / 2.0 - pit_r, d / 2.0 - pit_r,
                 d / 2.0 + pit_r, d / 2.0 + pit_r)
        c.itemconfig(self.i_pit, fill=_hex(self.theme["center_bg"]))

        cd = self._countdown_progress()
        if cd == "flash":
            # 倒计时结束：整圈闪烁提示时间到。亮帧画满圈蓝弧，暗帧隐藏（整圈消失）。
            if self._countdown_flash_on():
                c.itemconfig(self.i_heat, state="normal",
                             extent=-SWEEP_DEG, outline=COUNTDOWN_ARC_COLOR)
            else:
                c.itemconfig(self.i_heat, state="hidden")
        elif cd is not None:
            # 倒计时进行中：圆环表示剩余时间（满圈→空），不表示热度
            c.itemconfig(self.i_heat, state="normal",
                         extent=-SWEEP_DEG * cd, outline=COUNTDOWN_ARC_COLOR)
        elif frac > IDLE_ARC_DEG / SWEEP_DEG:
            # 阈值用"下限弧长"（= 空闲那段的长度），不能用一个小常数：否则热度
            # 刚起来时弧长会先从 2.5° 缩下去再长起来 —— 非单调的小跳变。
            c.itemconfig(self.i_heat, state="normal",
                         extent=-SWEEP_DEG * frac, outline=heat_hex(frac))
        elif state == "paused":
            # 暂停：弧长照旧（已有成绩），但换琥珀色，一眼看出"没在记"
            c.itemconfig(self.i_heat, state="normal",
                         extent=-SWEEP_DEG * max(frac, IDLE_ARC_DEG / SWEEP_DEG),
                         outline=PAUSED_ARC)
        else:
            # 空闲时不把弧藏起来：留一小段冷色弧，让表盘的位置随时有存在感
            c.itemconfig(self.i_heat, state="normal",
                         extent=-IDLE_ARC_DEG, outline=heat_hex(0.0))

        c.itemconfig(self.i_kpm,
                     text=str(snap.get("kpm", 0)),
                     fill=heat_hex(frac) if frac > 0.02 else self.theme["muted"])
        c.itemconfig(self.i_split,
                     text=split_text(snap.get("kpm_keys", 0), snap.get("kpm_mouse", 0)))
        c.itemconfig(self.i_peak, text="峰值 %d" % round(snap.get("peak", 0.0)))

        if state == "paused":
            dot_color = "#E0B02C"
        elif state in ("typing", "pointing", "pause"):
            dot_color = heat_hex(frac)      # pointing 同样是活跃状态，用热度色
        else:
            dot_color = self.theme["muted"]

        c.itemconfig(self.i_state, text=STATE_LABEL.get(state, ""))
        c.itemconfig(self.i_dot, fill=dot_color)
        self._center_state_row()

        # 倒计时到点 → 数字模式用「时间到」替掉大数字做文字提示（盖过真实读数）。
        if self._fired:
            c.itemconfig(self.i_kpm, text="")
            c.itemconfig(self.i_unit, text="")
            c.itemconfig(self.i_split, text="")
            c.itemconfig(self.i_peak, text="")
            c.itemconfig(self.i_timeout, text="时间到", state="normal",
                         fill=self.theme["text"])
        else:
            c.itemconfig(self.i_timeout, state="hidden")

    # ---------------- 操作 ----------------

    def _bind_hotkeys(self):
        from pynput import keyboard as kb
        self._hotkeys = kb.GlobalHotKeys({
            "<ctrl>+<alt>+h": lambda: self.root.after(0, self.toggle_visible),
            "<ctrl>+<alt>+r": lambda: self.root.after(0, self.open_report),
            "<ctrl>+<alt>+p": lambda: self.root.after(0, self.toggle_pause),
            "<ctrl>+<alt>+f": lambda: self.root.after(0, self.toggle_campfire),
            "<ctrl>+<alt>+t": lambda: self.root.after(0, self.cycle_countdown),
            "<ctrl>+<alt>+m": lambda: self.root.after(0, self.cycle_screen),
            "<ctrl>+<alt>+q": lambda: self.root.after(0, self.quit),
        })
        self._hotkeys.daemon = True
        self._hotkeys.start()

    def toggle_campfire(self):
        """篝火 ⇄ 数字仪表盘。采集是同一套，切的是渲染，写回 config.json。"""
        self._campfire = not self._campfire
        cfg_set(self.cfg, "campfire", self._campfire)
        save_config(self.service.config)
        self._show_camp(self._campfire)
        self._sync_edge_colors()          # 内弧身下从灶膛换成底盘（或反过来）
        print("[i] 显示样式 → %s" % ("篝火" if self._campfire else "数字"))

    def cycle_countdown(self):
        """热键循环倒计时档位：关闭 → 5 → 10 → 25 → 关闭。"""
        seq = [v for _, v in COUNTDOWN_ENTRIES]
        cur = self._countdown_min
        nxt = seq[(seq.index(cur) + 1) % len(seq)] if cur in seq else seq[1]
        self._countdown_min = nxt
        if nxt > 0:
            self._countdown_deadline = time.time() + nxt * 60.0
            self._fired = False
            log_countdown(nxt, "hotkey", self.service.db_path)
        else:
            self._countdown_deadline = None
            self._fired = False
        print("[i] 倒计时 → %s" % dict(COUNTDOWN_ENTRIES)[nxt])

    def _breathe_heat(self):
        """倒计时提示的呼吸热度：在小火/大火之间按正弦往复。"""
        t = time.time() - self._fire_start
        b = 0.5 + 0.5 * math.sin(2.0 * math.pi * t / COUNTDOWN_BREATHE_PERIOD)
        return COUNTDOWN_FIRE_LOW + (COUNTDOWN_FIRE_HIGH - COUNTDOWN_FIRE_LOW) * b

    def _countdown_progress(self):
        """倒计时进行 / 已触发期间，返回**剩余时间占比**（1.0=刚选时长满圈，
        0.0=到点）；未进入倒计时返回 None —— 此时圆环照旧表示热度。

        因为是倒计时，环随计时**耗尽**（从满圈递减到空）。到点（_fired）返回
        字符串 "flash" —— 圆环不再表示剩余，而是**整圈闪烁**提示时间到。
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

    def toggle_visible(self):
        if self.visible:
            self.root.withdraw()
        else:
            self.root.deiconify()
            self._set_click_through()      # deiconify 之后扩展样式会丢，得补回来
        self.visible = not self.visible

    def open_report(self):
        import report
        out = report.generate(self.service.config, db_path=self.service.db_path)
        os.startfile(str(out))

    def toggle_pause(self):
        paused = self.service.toggle_pause()
        # 暂停记录被选中 → 桌面上也不再显示这个图形（与 Qt 版一致，用户第 14+ 轮）。
        # deiconify 之后扩展样式（点击穿透）会丢，得补回来；self.visible 也跟着翻，
        # 免得和 toggle_visible 的开关状态打架。
        if paused:
            self.root.withdraw()
            self.visible = False
        else:
            self.root.deiconify()
            self._set_click_through()
            self.visible = True

    def cycle_position(self):
        values = [v for _, v in POSITIONS]
        cur = cfg_get(self.cfg, "position", "bottom-right")
        nxt = values[(values.index(cur) + 1) % len(values)] if cur in values else values[0]
        cfg_set(self.cfg, "position", nxt)
        save_config(self.service.config)
        self._place()
        print("[i] 停靠位置 → %s" % nxt)

    def cycle_screen(self):
        """热键循环切换显示器：0 → 1 → … → 0。写 config 并重新落位。"""
        n = len(_monitor_work_areas()) or 1
        cur = int(cfg_get(self.cfg, "screen", 0))
        nxt = (cur + 1) % n
        cfg_set(self.cfg, "screen", nxt)
        save_config(self.service.config)
        self._place()
        print("[i] 显示器 → %d（共 %d 块）" % (nxt + 1, n))

    def _screen_watchdog(self):
        """显示器数量变化时重新落位，避免拔掉选中的屏后窗口留在屏外。"""
        try:
            n = len(_monitor_work_areas())
            if n and n != self._mon_count:
                self._mon_count = n
                self._place()
        except Exception:
            pass
        self.root.after(2000, self._screen_watchdog)

    def quit(self):
        try:
            if self._hotkeys is not None:
                self._hotkeys.stop()
        except Exception:
            pass
        self.service.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return 0


def run():
    if not claim_single_instance():
        print("[i] 已经有一个实例在运行，不再重复启动。")
        notify_already_running()
        return 0

    service = HeatService().start()
    dial = HeatDialTk(service)

    print("键盘热度显示器已启动 —— 屏幕右下角会先扫一圈亮个相，那就是它。")
    print("热度 = 键盘击键 + 鼠标移动/点击/滚轮（后三者折算成等效击键后合并）")
    print("全局热键：")
    print("  Ctrl+Alt+H   显示 / 隐藏悬浮窗")
    print("  Ctrl+Alt+R   打开历史报告")
    print("  Ctrl+Alt+P   暂停 / 恢复记录")
    print("  Ctrl+Alt+F   篝火 / 数字样式切换")
    print("  Ctrl+Alt+Q   退出")

    if os.environ.get("HEAT_SELFTEST"):
        dial.root.after(1200, dial.quit)

    return dial.run()


if __name__ == "__main__":
    raise SystemExit(run())
