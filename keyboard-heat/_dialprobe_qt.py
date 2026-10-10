"""PyQt6 版悬浮窗探针：伪造 service，渲染几种状态并截图。

Tkinter 版有 _dialprobe.py，这个是对应物。两版共用同一套算法，布局也刻意对齐，
所以把这个也跑一遍，确认 PyQt6 那条路径没写坏（改了 paintEvent 之后尤其需要）。

两种视觉各跑一遍：
    .pyenv\\Scripts\\python.exe _dialprobe_qt.py              # 篝火（默认）
    .pyenv\\Scripts\\python.exe _dialprobe_qt.py --digits     # 数字仪表盘
    .pyenv\\Scripts\\python.exe _dialprobe_qt.py --phase 3.8  # 固定摇曳相位

热度阶梯是篝火模式的关键验收项：火苗必须随热度单调变大、颜色从暗红余烬走到
亮黄，光看一帧看不出来。相位固定是为了两次运行能逐像素比 —— 摇曳是时间函数，
不固定相位就没法判断"这一版的火是不是真的变了"。

截图走**离屏渲染**（QWidget.grab），不抓屏：探针窗口和真机实例都在右下角同一个
位置，抓屏会抓到谁完全看运气（曾经抓到桌面和旧实例，白验一轮）。离屏结果垫一层
灰底再存，既能看到透明边，也和桌面观感接近。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from heatcore import load_config                # noqa: E402

try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtWidgets import QApplication
except ImportError as exc:
    print("SKIP 这个解释器没有 PyQt6：%s" % exc)
    raise SystemExit(2)

from overlay import HeatDial                    # noqa: E402

def scene(heat, state, kpm=None, keys=None, mouse=None):
    kpm = round(heat * 3.0) if kpm is None else kpm
    keys = 0 if keys is None else keys
    mouse = kpm - keys if mouse is None else mouse
    return {"heat": heat, "kpm": kpm, "kpm_keys": keys, "kpm_mouse": mouse,
            "peak": 214.0, "state": state, "idle_seconds": 1.0, "total_keys": 100}


# 前四个是真实业务状态；后面 h05~h100 是热度阶梯，专门用来验火苗的大小/颜色梯度
SCENES = [
    ("typing", scene(62.0, "typing", kpm=186, keys=140, mouse=46)),
    ("pointing", scene(28.0, "pointing", kpm=84, keys=0, mouse=84)),
    ("idle", scene(0.0, "idle", kpm=0, keys=0, mouse=0)),
    ("paused", scene(0.0, "paused", kpm=0, keys=0, mouse=0)),
    ("h05", scene(5.0, "typing")),
    ("h25", scene(25.0, "typing")),
    ("h50", scene(50.0, "typing")),
    ("h80", scene(80.0, "typing")),
    ("h100", scene(100.0, "typing")),
]


class FakeService:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"
        self.snap = dict(SCENES[0][1])

    def snapshot(self):
        return dict(self.snap)

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def main():
    args = sys.argv[1:]
    digits = "--digits" in args
    floor_off = "--no-floor" in args       # 关掉底火层 → 出"改前/改后"对比用
    phase = None
    if "--phase" in args:
        phase = float(args[args.index("--phase") + 1])
    tag = ("d" if digits else "c") + ("_nf" if floor_off else "")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    service = FakeService()
    dial = HeatDial(service)
    dial._campfire = not digits            # 覆盖 config，一次跑一种视觉
    dial._flame_floor = not floor_off      # 同上：底火层开关
    dial._boot_done = True                 # 跳过开屏动画，直接看稳态
    dial.show()
    if phase is not None:
        dial._timer.stop()                 # 冻结时间，否则相位会继续累加、两次跑不可比

    seq = list(SCENES)

    def shoot(name):
        # 离屏渲染（QWidget.grab），**不要**抓屏：探针窗口和真机实例都在右下角，
        # 抓屏抓到谁完全看谁在上面 —— 曾经抓到桌面和旧实例的画面，白验一轮。
        pm = dial.grab()
        img = QImage(pm.size(), QImage.Format.Format_RGB32)
        img.fill(QColor(64, 64, 68))       # 垫一层灰底冒充桌面，便于看透明边
        pp = QPainter(img)
        pp.drawPixmap(0, 0, pm)
        pp.end()
        out = HERE / ("_dialqt_%s_%s.png" % (tag, name))
        img.save(str(out), "PNG")
        print("SHOT %-16s %dx%d -> %s" % (name, img.width(), img.height(), out.name))
        QTimer.singleShot(140, nxt)

    def nxt():
        if not seq:
            dial._quit()
            return
        name, snap = seq.pop(0)
        service.snap = snap
        if phase is not None:
            # 定时器已冻结，_refresh 不会再跑 —— 快照得手动换，否则 9 张图全是第一帧
            dial._snap = dict(snap)
            dial._phase = phase            # 固定摇曳相位
            dial.update()
        QTimer.singleShot(260, lambda: shoot(name))    # 等窗口合成完

    print("表盘尺寸 %d，位置 (%d,%d)，视觉=%s，底火层=%s，相位=%s"
          % (dial.width(), dial.x(), dial.y(),
             "数字" if digits else "篝火", "off" if floor_off else "on",
             "自由" if phase is None else phase))
    QTimer.singleShot(600, nxt)
    app.exec()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
