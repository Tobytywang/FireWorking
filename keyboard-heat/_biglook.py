"""大盘细节预览：把默认样式（charred）放大到 320px，看木头和火焰的衔接。

用法：.pyenv\\Scripts\\python.exe _biglook.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import _shot                                     # noqa: E402
from heatcore import load_config                 # noqa: E402

try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
except ImportError as exc:
    print("SKIP 这个解释器没有 PyQt6：%s" % exc)
    raise SystemExit(2)

from overlay import HeatDial                     # noqa: E402

SIZE = 320
HEATS = (("idle", 0.0), ("mid", 50.0), ("high", 90.0))


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
    dial._timer.stop()
    dial.setFixedSize(SIZE, SIZE)
    dial.move(220, 140)               # 别贴屏幕边，截屏才截得全
    dial.show()

    jobs = list(HEATS)

    def shoot(name):
        x, y = dial.x(), dial.y()
        rows = _shot.grab(x, y, SIZE, SIZE)
        out = HERE / ("_biglook_%s.png" % name)
        _shot.write_png(str(out), SIZE, SIZE, rows)
        print("SHOT %-6s -> %s" % (name, out.name))
        QTimer.singleShot(120, nxt)

    def nxt():
        if not jobs:
            dial._quit()
            return
        name, heat = jobs.pop(0)
        dial._phase = 1.3
        dial._snap = scene(heat)
        dial.update()
        QTimer.singleShot(220, lambda: shoot(name))

    print("盘尺寸 %d，样式 %s" % (SIZE, dial._log_style))
    QTimer.singleShot(600, nxt)
    app.exec()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
