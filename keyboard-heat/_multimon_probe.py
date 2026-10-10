"""多屏落位探针 —— 验证「固定到指定屏」的取屏 / 落位数学。

用法：python _multimon_probe.py
输出：
  - 每张显示器（主屏排第一）：index / 是否主屏 / 工作区 rcWork
  - 在该屏「右下角、margin=28、size=176」时算出的窗口坐标
  - 当前 config.json 里 overlay.screen 的值（若有）

这让你在不动 GUI 的情况下看清：screen 索引和物理显示器的对应关系、
以及悬浮层会落在哪块屏的哪个角。需 Windows + Python + ctypes（无第三方依赖）。
"""
import ctypes
import json
import os

user32 = ctypes.windll.user32


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]


def monitor_work_areas():
    raw = []

    def cb(hmonitor, hdc, lprect, lparam):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
            raw.append((mi.rcMonitor, mi.rcWork))
        return True

    Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.POINTER(_RECT), ctypes.c_void_p)
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetMonitorInfoW.restype = ctypes.c_bool
    user32.EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.c_void_p, Proc, ctypes.c_void_p]
    user32.EnumDisplayMonitors.restype = ctypes.c_bool
    user32.EnumDisplayMonitors(0, 0, Proc(cb), 0)
    if not raw:
        return []
    # 主屏（含 (0,0) 的那块）排第一，和 work_area(0)==主屏 保持一致
    primary = 0
    for i, (m, _w) in enumerate(raw):
        if m.left <= 0 < m.right and m.top <= 0 < m.bottom:
            primary = i
            break
    ordered = [raw[primary][1]] + [raw[i][1] for i in range(len(raw)) if i != primary]
    return [(r.left, r.top, r.right, r.bottom) for r in ordered]


def main():
    areas = monitor_work_areas()
    if not areas:
        print("[!] 没枚举到显示器（可能无头环境）。")
        return
    size = 176
    margin = 28
    pos = "bottom-right"
    print("显示器数量：%d\n" % len(areas))
    for i, (l, t, r, b) in enumerate(areas):
        w = r - l
        h = b - t
        x = (r - size - margin) if "right" in pos else (l + margin)
        y = (b - size - margin) if "bottom" in pos else (t + margin)
        print("显示器 %d%s  工作区 L%d T%d R%d B%d  尺寸 %dx%d"
              % (i + 1, "（主屏）" if i == 0 else "", l, t, r, b, w, h))
        print("     → 右下角落位: x=%d y=%d  (size=%d, margin=%d)\n" % (x, y, size, margin))
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        print("config.json overlay.screen = %s" % cfg.get("overlay", {}).get("screen", 0))
    except Exception:
        print("（未找到 / 无法读取 config.json，跳过当前配置显示）")


if __name__ == "__main__":
    main()
