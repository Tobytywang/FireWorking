"""四套木柴样式的对比预览 —— 只用来看木头，不启动采集、不占单实例锁。

为什么单独开一个脚本而不是塞进 _dialprobe_qt.py：调样式时每次只关心
"同一热度下四套木头长什么样"，跑整套状态（9 个场景）纯属浪费。

对照组固定为「空闲」和「半热」两档：
  · 空闲 —— 火很小，木头完全露出来，是看造型最清楚的档位
  · 半热 —— 火盖住中段，能看出木头和火焰的衔接关系（真实使用时的样子）

用法：
    .pyenv\\Scripts\\python.exe _logstyle_preview.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import _shot                                     # noqa: E402
import flame                                     # noqa: E402
from heatcore import load_config                 # noqa: E402

try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
except ImportError as exc:
    print("SKIP 这个解释器没有 PyQt6：%s" % exc)
    raise SystemExit(2)

from overlay import HeatDial                     # noqa: E402

# (名字, 热度) —— 空闲 / 半热两档
HEATS = (("idle", 0.0), ("mid", 50.0))


def scene(heat):
    kpm = round(heat * 3.0)
    return {"heat": heat, "kpm": kpm, "kpm_keys": kpm, "kpm_mouse": 0,
            "peak": 214.0, "state": "idle" if heat <= 0 else "typing",
            "idle_seconds": 1.0, "total_keys": 100}


class FakeService:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"
        self.snap = scene(0.0)

    def snapshot(self):
        return dict(self.snap)

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    service = FakeService()
    dial = HeatDial(service)
    dial._campfire = True
    dial._boot_done = True
    dial._timer.stop()                      # 冻结时间：四张图必须同一个相位才可比
    dial.show()

    jobs = [(st, hn, hv) for st in flame.LOG_STYLES for hn, hv in HEATS]

    def shoot(style, heat_name):
        x, y = dial.x(), dial.y()
        w, h = dial.width(), dial.height()
        rows = _shot.grab(x, y, w, h)
        out = HERE / ("_logstyle_%s_%s.png" % (style, heat_name))
        _shot.write_png(str(out), w, h, rows)
        print("SHOT %-22s -> %s" % ("%s/%s" % (style, heat_name), out.name))
        QTimer.singleShot(120, nxt)

    def nxt():
        if not jobs:
            dial._quit()
            return
        style, heat_name, heat = jobs.pop(0)
        dial._log_style = style
        dial._phase = 1.3                   # 固定摇曳相位
        dial._snap = scene(heat)
        dial.update()
        QTimer.singleShot(220, lambda: shoot(style, heat_name))

    print("盘尺寸 %d，样式：%s" % (dial.width(), " / ".join(flame.LOG_STYLES)))
    QTimer.singleShot(600, nxt)
    app.exec()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
