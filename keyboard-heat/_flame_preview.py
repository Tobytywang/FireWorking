"""篝火渲染预览：一排不同热度的火堆，用来确认画面效果。

不启动采集、不占单实例锁 —— 纯粹把 flame.py 画出来看一眼。
用法：.pyenv\\Scripts\\python.exe _flame_preview.py [帧序号]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import _shot                                        # noqa: E402
import flame                                        # noqa: E402
from heatcore import heat_rgb                       # noqa: E402

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt    # noqa: E402
    from PyQt6.QtGui import QColor, QPainter, QPen
    from PyQt6.QtWidgets import QApplication, QWidget
except ImportError as exc:
    print("SKIP 这个解释器没有 PyQt6：%s" % exc)
    raise SystemExit(2)

START_DEG = 220.0
SWEEP_DEG = 260.0

HEATS = [0.04, 0.20, 0.45, 0.72, 1.00]
D = 190


class Preview(QWidget):
    def __init__(self, t0=0.0, phase=0.0):
        super().__init__()
        self.setFixedSize(D * len(HEATS) + 24, D + 24)
        self.setWindowTitle("campfire preview")
        self.t = t0
        self.phase = phase
        self.field = flame.SparkField()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.fillRect(self.rect(), QColor(28, 30, 38))

        for i, heat in enumerate(HEATS):
            cx = 12 + i * D + D / 2.0
            cy = 12 + D / 2.0
            self._dial(p, cx, cy, D, heat)
        p.end()

    def _dial(self, p, cx, cy, d, heat):
        # 底盘
        plate_r = d / 2.0 - max(2.0, d * 0.012)
        p.setBrush(QColor(24, 27, 35))
        p.setPen(QPen(QColor(139, 150, 168), 2.0))
        p.drawEllipse(QPointF(cx, cy), plate_r, plate_r)

        # 圆环：保留下来做精确读数（用户要求）
        thickness = max(8.0, d * 0.062)
        radius = d / 2.0 - max(6.0, d * 0.045) - thickness / 2.0
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        pen = QPen(QColor(255, 255, 255, 74), thickness)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect, int(START_DEG * 16), int(-SWEEP_DEG * 16))
        pen.setColor(QColor(*heat_rgb(heat)))
        p.setPen(pen)
        p.drawArc(rect, int(START_DEG * 16), int(-SWEEP_DEG * max(0.004, heat) * 16))

        # 火
        flame.draw_campfire_qt(p, cx, cy, d, heat, self.phase, self.field)


def main():
    phase = float(sys.argv[1]) if len(sys.argv) > 1 else 1.3
    app = QApplication(sys.argv)
    w = Preview(phase=phase)
    w.move(40, 40)
    w.show()
    app.processEvents()
    time.sleep(0.4)
    app.processEvents()

    out = HERE / ("_flame_p%s.png" % str(phase).replace(".", "_"))
    rows = _shot.grab(w.x(), w.y(), w.width(), w.height())
    _shot.write_png(str(out), w.width(), w.height(), rows)
    print("SHOT %dx%d@%d,%d -> %s" % (w.width(), w.height(), w.x(), w.y(), out.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
