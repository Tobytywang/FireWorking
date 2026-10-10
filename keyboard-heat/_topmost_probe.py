"""置顶状态探针 —— 实测「键盘热度」悬浮层的 WS_EX_TOPMOST 位有没有被降格。

用法：
    python _topmost_probe.py
    （保持悬浮层运行；中途把别的窗口最大化 / 前置，观察输出变化）

输出每 2 秒一拍，共约 10 拍：
    - 找到标题包含「键盘热度」的窗口，打印 hwnd / exstyle / TOPMOST 位（1=置顶中）
    - 打印当前前台窗口标题
    - 若 TOPMOST 位在某拍变成 0 → 确认是「运行中被动降格」（看门狗应下一拍抢回 1）
    - 若 TOPMOST 一直是 1 但仍被盖住 → 说明遮挡来自另一个同样置顶的窗口 / DWM 独占，
      看门狗会每秒重新声明，把非独占的遮挡顶下去

无第三方依赖，仅用 ctypes 调用 user32。
"""
import ctypes
import time

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008

EnumWindows = user32.EnumWindows
EnumWindows.restype = ctypes.c_bool
EnumWindows.argtypes = [ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int), ctypes.c_int]

GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowTextLengthW.argtypes = [ctypes.c_int]
GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int]
GetWindowLongW = user32.GetWindowLongW
GetWindowLongW.argtypes = [ctypes.c_int, ctypes.c_int]
GetForegroundWindow = user32.GetForegroundWindow
IsWindowVisible = user32.IsWindowVisible
IsWindowVisible.argtypes = [ctypes.c_int]


def _title(hwnd):
    n = GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _fg_title():
    fg = GetForegroundWindow()
    return _title(fg) if fg else "(none)"


def _scan():
    hits = []
    targets = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    def cb(hwnd, _lparam):
        if IsWindowVisible(hwnd):
            t = _title(hwnd)
            if "键盘热度" in t:
                ex = GetWindowLongW(hwnd, GWL_EXSTYLE)
                hits.append((hwnd, t, ex, 1 if (ex & WS_EX_TOPMOST) else 0))
        return True

    EnumWindows(cb, 0)
    return hits


def main():
    print("按 Ctrl+C 停止。中途可把别的窗口最大化 / 前置来观察。")
    for i in range(10):
        hits = _scan()
        print("\n=== 第 %d 拍 (%.1fs) ===" % (i + 1, time.time() % 100))
        print("  前台窗口 : %s" % _fg_title())
        if not hits:
            print("  [!] 没找到「键盘热度」窗口（悬浮层没在跑？）")
        for hwnd, t, ex, top in hits:
            print("  hwnd=%d  TOPMOST=%d  exstyle=0x%08X  title=%r"
                  % (hwnd, top, ex & 0xFFFFFFFF, t))
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止。")
