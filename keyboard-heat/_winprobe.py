"""在真实进程内检查悬浮窗状态 —— 用 pythonw.exe 运行，和双击启动完全一致。

为什么需要它：pythonw 没有控制台，任何 print 都进不了眼睛，窗口一旦不显示
就只能靠猜。这个探针把 Tk 层和 Win32 层的窗口状态全部落盘，一次性回答
"窗口到底建出来没有、在哪、可见吗、透明度属性是什么"。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "_winprobe.log"
BUF: list[str] = []

GA_ROOT = 2
GWL_EXSTYLE = -20
LWA_COLORKEY = 0x1
LWA_ALPHA = 0x2


def log(msg=""):
    BUF.append(str(msg))
    LOG.write_text("\n".join(BUF), encoding="utf-8")


def step(name, fn):
    try:
        r = fn()
        log("[OK]   %s -> %r" % (name, r))
        return r
    except BaseException:
        log("[FAIL] %s" % name)
        log(traceback.format_exc())
        return None


log("=" * 64)
log("pythonw 探针 —— 复刻 run.bat 的启动路径")
log("=" * 64)
log("executable : %s" % sys.executable)
log("cwd        : %s" % os.getcwd())
log("sys.stdout is None : %s" % (sys.stdout is None))
log("sys.stderr is None : %s" % (sys.stderr is None))
log("")

sys.path.insert(0, str(HERE))

heatcore = step("import heatcore", lambda: __import__("heatcore"))
if heatcore is None:
    sys.exit(1)

overlay_tk = step("import overlay_tk", lambda: __import__("overlay_tk"))
if overlay_tk is None:
    sys.exit(1)

log("")
service = step("HeatService().start()", lambda: heatcore.HeatService().start())
if service is None:
    log("")
    log(">>> 采集服务没起来，后面就断了。问题在 heatcore 这一层。")
    sys.exit(1)

log("")
dial = step("HeatDialTk(service)  <- 建窗口", lambda: overlay_tk.HeatDialTk(service))
if dial is None:
    log("")
    log(">>> 窗口构造函数抛异常，Tk/Win32 这一层有问题。")
    sys.exit(1)

root = dial.root
step("root.update_idletasks()", lambda: root.update_idletasks())
step("root.update()", lambda: root.update())

u = ctypes.windll.user32

log("")
log("--- Tk 层 ---")
log("winfo_id    : 0x%08X" % root.winfo_id())
log("is_toplevel .mapped   : %s" % root.winfo_ismapped())
log("is_toplevel .viewable : %s" % root.winfo_viewable())
log("geometry    : %s" % root.winfo_geometry())
log("rootx/y     : %s, %s" % (root.winfo_rootx(), root.winfo_rooty()))
log("screen size : %s x %s" % (root.winfo_screenwidth(), root.winfo_screenheight()))
log("state       : %s" % root.state())
for attr in ("-alpha", "-transparentcolor", "-topmost"):
    try:
        log("attr %-18s: %r" % (attr, root.attributes(attr)))
    except Exception as exc:
        log("attr %-18s: <读取失败 %s>" % (attr, exc))

log("")
log("--- Win32 层 ---")
hwnd = u.GetAncestor(root.winfo_id(), GA_ROOT) or u.GetParent(root.winfo_id())
log("hwnd        : 0x%08X" % hwnd)
rect = wt.RECT()
if u.GetWindowRect(hwnd, ctypes.byref(rect)):
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    log("window rect : L=%d T=%d R=%d B=%d   (w=%d h=%d)"
        % (rect.left, rect.top, rect.right, rect.bottom, w, h))
log("IsWindowVisible : %s" % bool(u.IsWindowVisible(hwnd)))
ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
log("exstyle     : 0x%08X" % ex)
log("   LAYERED      = %s" % bool(ex & 0x00080000))
log("   TRANSPARENT  = %s" % bool(ex & 0x00000020))
log("   TOOLWINDOW   = %s" % bool(ex & 0x00000080))

alpha = wt.BYTE()
key = wt.COLORREF()
flags = wt.DWORD()
if u.GetLayeredWindowAttributes(hwnd, ctypes.byref(key), ctypes.byref(alpha), ctypes.byref(flags)):
    log("layered attr : alpha=%d flags=0x%X colorKey=0x%06X"
        % (alpha.value, flags.value, key.value))
    log("   LWA_ALPHA    = %s" % bool(flags.value & LWA_ALPHA))
    log("   LWA_COLORKEY = %s" % bool(flags.value & LWA_COLORKEY))

if u.GetWindowRect(hwnd, ctypes.byref(rect)):
    pt = wt.POINT(rect.left + (rect.right - rect.left) // 2,
                  rect.top + (rect.bottom - rect.top) // 2)
    log("窗口中心点   : (%d, %d)" % (pt.x, pt.y))
    log("所在显示器句柄: 0x%08X" % u.MonitorFromPoint(pt, 2))
    va = u.GetSystemMetrics(76)     # SM_XVIRTUALSCREEN
    vb = u.GetSystemMetrics(77)     # SM_YVIRTUALSCREEN
    vc = u.GetSystemMetrics(78)
    vd = u.GetSystemMetrics(79)
    inside = (va <= pt.x <= va + vc) and (vb <= pt.y <= vb + vd)
    log("虚拟屏范围   : (%d, %d) - (%d, %d)" % (va, vb, va + vc, vb + vd))
    log("中心点在虚拟屏内: %s" % inside)

    # 决定性检查：这个位置上，系统认为最顶层的窗口是谁？
    log("")
    log("--- 遮挡检查（WindowFromPoint） ---")
    probes = {
        "窗口中心": (pt.x, pt.y),
        "圆环左上": (rect.left + 30, rect.top + 30),
        "圆环右下": (rect.right - 30, rect.bottom - 30),
    }
    for label, (px, py) in probes.items():
        top = u.WindowFromPoint(wt.POINT(px, py))
        n = u.GetWindowTextLengthW(top)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(top, buf, n + 1)
        tpid = wt.DWORD()
        u.GetWindowThreadProcessId(top, ctypes.byref(tpid))
        log("%s (%d,%d):" % (label, px, py))
        log("   最顶层窗口 hwnd = 0x%08X  PID=%d" % (top, tpid.value))
        log("   标题 = %r" % buf.value)
        log("   是我们的窗口吗 = %s" % (top == hwnd))

log("")
log(">>> 窗口会保持 20 秒，请看屏幕右下角（1716, 828 附近）。")
root.after(20000, dial.quit)
root.mainloop()
log(">>> 已正常退出（说明窗口生命周期没问题）")
