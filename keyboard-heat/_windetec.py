"""诊断：枚举当前会话里所有顶层窗口，找出悬浮窗的实际位置和状态。

排查"程序在跑但看不到窗口"这类问题的唯一可靠办法 —— 直接问 Win32
窗口管理器，别靠猜。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
GWL_STYLE = -16
SPI_GETWORKAREA = 0x0030


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def text_of(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def main():
    out = []

    # 屏幕与工作区
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    va = user32.GetSystemMetrics(78)      # SM_CXVIRTUALSCREEN
    vb = user32.GetSystemMetrics(79)      # SM_CYVIRTUALSCREEN
    nmon = user32.GetSystemMetrics(80)    # SM_CMONITORS
    r = RECT()
    ok = user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0)
    out.append("主屏分辨率 : %d x %d" % (sw, sh))
    out.append("虚拟屏尺寸 : %d x %d" % (va, vb))
    out.append("显示器数量 : %d" % nmon)
    out.append("工作区     : %s -> left=%d top=%d right=%d bottom=%d"
               % ("OK" if ok else "调用失败", r.left, r.top, r.right, r.bottom))
    out.append("")

    # 进程 DPI 感知
    try:
        aware = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(aware))
        out.append("本进程 DPI 感知级别: %d (0=不感知 1=系统 2=每显示器)" % aware.value)
    except Exception as exc:
        out.append("DPI 感知查询失败: %s" % exc)

    try:
        ctypes.windll.user32.SetProcessDPIAware()
        out.append("尝试设置 DPI 感知后 主屏 = %d x %d"
                   % (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)))
    except Exception as exc:
        out.append("SetProcessDPIAware 失败: %s" % exc)
    out.append("")

    # 会话
    out.append("当前会话 ID: %d" % ctypes.windll.kernel32.WTSGetActiveConsoleSessionId())

    # 枚举顶层窗口
    hits = []
    total = [0]
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(hwnd, lparam):
        total[0] += 1
        title = text_of(hwnd)
        if not title:
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rr = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rr))
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        st = user32.GetWindowLongW(hwnd, GWL_STYLE)
        hits.append({
            "hwnd": hwnd, "title": title, "pid": pid.value,
            "rect": (rr.left, rr.top, rr.right, rr.bottom),
            "vis": bool(user32.IsWindowVisible(hwnd)),
            "ex": ex, "st": st,
            "alpha": wt.BYTE(), "key": wt.COLORREF(), "flags": wt.DWORD(),
        })
        # 查询 layered 属性
        try:
            a = wt.BYTE(); k = wt.COLORREF(); f = wt.DWORD()
            if user32.GetLayeredWindowAttributes(hwnd, ctypes.byref(k), ctypes.byref(a), ctypes.byref(f)):
                hits[-1]["alpha"] = a.value
                hits[-1]["key"] = k.value
                hits[-1]["flags"] = f.value
        except Exception:
            pass
        return True

    user32.EnumWindows(PROC(cb), 0)
    out.append("")
    out.append("顶层窗口总数（含无标题）: %d" % total[0])
    out.append("=" * 70)

    KEY = 0x01
    for h in hits:
        matched = "键盘热度" in h["title"]
        mark = " <<<<< 悬浮窗" if matched else ""
        out.append("hwnd=0x%08X pid=%d vis=%s%s" % (h["hwnd"], h["pid"], h["vis"], mark))
        out.append("   title : %s" % h["title"])
        out.append("   rect  : left=%d top=%d right=%d bottom=%d  (w=%d h=%d)"
                   % (h["rect"][0], h["rect"][1], h["rect"][2], h["rect"][3],
                      h["rect"][2] - h["rect"][0], h["rect"][3] - h["rect"][1]))
        out.append("   style : 0x%08X   exstyle: 0x%08X  (LAYERED=%s TRANSPARENT=%s TOOLWINDOW=%s)"
                   % (h["st"], h["ex"],
                      bool(h["ex"] & 0x00080000), bool(h["ex"] & 0x00000020),
                      bool(h["ex"] & 0x00000080)))
        if h["flags"]:
            out.append("   layered: alpha=%d flags=0x%X colorKey=0x%06X"
                       % (h["alpha"], h["flags"], h["key"]))
        out.append("")

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    txt = "\n".join(out)
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
