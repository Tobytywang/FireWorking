"""决定性对拍：离屏绘制像素 vs 真实屏幕像素 —— 判断「灰蒙蒙」是不是合成层的遮罩。

两种取图方式的差别就是全部关键：

  离屏 grab()   = 我们**画出去**的东西，不经过窗口合成（无遮罩也照原样）
  ImageGrab     = 用户**眼睛看到**的东西，经过 Windows 合成器

判据：
  · 两者逐像素一致  → 合成层没有引入任何混合，问题是观感/配色，别去动窗口
  · 抓屏明显更暗/更灰 → 遮罩确实存在，差值就是它的强度与方向

同时打印 windowOpacity（Qt 的整窗透明度）与 WA_TranslucentBackground 状态。
用 PER_MONITOR_AWARE 保证 Qt 坐标 == 物理像素，否则抓屏会偏。
"""
from __future__ import annotations

import ctypes
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    from PIL import Image, ImageGrab
except ImportError as exc:                                   # pragma: no cover
    print("SKIP 需要 PIL：%s" % exc)
    raise SystemExit(2)

from PyQt6.QtCore import Qt, QTimer                          # noqa: E402
from PyQt6.QtGui import QImage                               # noqa: E402
from PyQt6.QtWidgets import QApplication                     # noqa: E402

from heatcore import load_config                             # noqa: E402
from overlay import HeatDial                                 # noqa: E402

SCENE = {"heat": 0.0, "kpm": 0, "kpm_keys": 0, "kpm_mouse": 0,
         "peak": 214.0, "state": "idle", "idle_seconds": 1.0, "total_keys": 100}


class FakeService:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"
        self.snap = dict(SCENE)

    def snapshot(self):
        return dict(self.snap)

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def sat(c):
    mx, mn = max(c[:3]), min(c[:3])
    return 0.0 if mx == 0 else (mx - mn) / float(mx) * 100.0


def med_color(img, box):
    """区域内的中位 RGB —— 比均值抗火星/抗锯齿噪点。"""
    px = list(img.crop(box).convert("RGB").getdata())
    if not px:
        return (0, 0, 0)
    return tuple(int(statistics.median([p[i] for p in px])) for i in range(3))


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(FakeService())
    dial._boot_done = True
    dial._snap = dict(SCENE)
    dial._timer.stop()                 # 冻结时间，相位/热度都不许漂
    dial._phase = 0.0
    dial.show()
    dial.raise_()
    dial.update()

    print("WA_TranslucentBackground = %s"
          % dial.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
    print("windowOpacity()           = %.3f" % dial.windowOpacity())
    print("几何 x=%d y=%d w=%d h=%d  DPR=%.2f"
          % (dial.x(), dial.y(), dial.width(), dial.height(),
             dial.devicePixelRatioF()))

    def shoot():
        # 再确认一次状态没漂
        dial._snap = dict(SCENE)
        dial._phase = 0.0
        dial.update()
        for _ in range(12):                 # 把内容真正推到屏幕上
            app.processEvents()
            time.sleep(0.04)

        pm = dial.grab()
        qimg = pm.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        off_path = HERE / "_probe_offscreen.png"
        qimg.save(str(off_path), "PNG")

        x, y, w, h = dial.x(), dial.y(), dial.width(), dial.height()
        scr = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
        scr_path = HERE / "_probe_screen.png"
        scr.convert("RGB").save(str(scr_path))

        off = Image.open(off_path)               # RGBA
        scr_img = Image.open(scr_path).convert("RGB")
        if scr_img.size != (off.width, off.height):
            print("!! 抓屏尺寸 %s != 离屏 %s，按离屏尺寸缩放对齐"
                  % (scr_img.size, off.size))
            scr_img = scr_img.resize((off.width, off.height), Image.NEAREST)

        op = off.load()
        sp = scr_img.load()
        W, H = off.size

        total = same = 0
        dsum = 0.0
        dmax = 0
        worst = None
        for yy in range(H):
            for xx in range(W):
                r, g, b, a = op[xx, yy]
                if a < 250:
                    # 只比**完全不透明**的像素。半透明像素（灶膛 alpha 232、光晕、抗锯齿边）
                    # 本来就要和桌面合成：离屏图里存的是自身色，屏幕上是合成色，两者必然
                    # 不同 —— 那是正常合成，不是遮罩。判据放宽到 200 会把它们算进来，
                    # 一致率会假性掉到 20% 左右（踩过）。
                    continue
                sr, sg, sb = sp[xx, yy]
                d = (abs(r - sr) + abs(g - sg) + abs(b - sb)) / 3.0
                total += 1
                dsum += d
                if d > dmax:
                    dmax = d
                    worst = (xx, yy, (r, g, b), (sr, sg, sb))
                if d < 6:
                    same += 1

        print()
        print("=" * 74)
        print("逐像素对拍（只统计离屏图中不透明的像素：%d 个）" % total)
        print("=" * 74)
        if total:
            print("  平均色差 %.2f/255   完全一致(<6) 占 %.1f%%   最大色差 %.0f"
                  % (dsum / total, same * 100.0 / total, dmax))
            if worst:
                print("  最大差处 (x=%d,y=%d) 离屏 rgb%s → 屏幕 rgb%s"
                      % (worst[0], worst[1], worst[2], worst[3]))
            # 一致率崩掉时先怀疑"窗口没被看见"，别怀疑遮罩：这个探针的窗口和真机
            # 实例都落在屏幕右下角同一位置，**只要用户还开着一个实例，抓屏抓到的
            # 就是那个实例或桌面，不是这一帧**（踩过一次：屏幕色是深蓝桌面，
            # 一致率 0%，看着像"加了遮罩"）。判据：屏幕里出现离屏图没有的冷色
            # 大块（蓝/灰），就是被盖住了。
            if dsum / total > 20.0:
                print()
                print("  ⚠ 差异过大，先排查窗口有没有被抓到 —— 是不是还有实例在跑？")
                print("     tasklist | grep -i python     # 有 pythonw.exe 就先退掉再跑本探针")
        else:
            print("  离屏图没有不透明像素？渲染可能失败了")

        print()
        print("=" * 74)
        print("分区域中位色（离屏 = 画出去的 / 屏幕 = 眼睛看到的）")
        print("=" * 74)
        # 区域框按**当前几何**取（盘径 190：圆心 95、灶膛半径 73、前景柴堆内容
        # 顶边 y=115、柴堆横跨 x 44~145）。旧框是早先几何留下的，一个把柴堆当
        # 灶膛、一个把大片灶膛底色混进"火焰全团"，中位色会假性地变暗（踩过）。
        boxes = {
            "火焰本体(86,94)-(106,118)": (86, 94, 106, 118),
            "灶膛空白(45,55)-(65,75)": (45, 55, 65, 75),
            "柴堆前部(75,120)-(115,140)": (75, 120, 115, 140),
            "整窗": (0, 0, off.width, off.height),
        }
        for name, box in boxes.items():
            co = med_color(off, box)
            cs = med_color(scr_img, box)
            print("  %-26s 离屏 rgb%-16s 饱和%5.1f%%  |  屏幕 rgb%-16s 饱和%5.1f%%"
                  % (name, str(co), sat(co), str(cs), sat(cs)))
            print("  %-26s 屏幕/离屏 亮度比 %.2f"
                  % ("", (sum(cs) / max(1.0, sum(co)))))

        dial._quit()

    QTimer.singleShot(900, shoot)
    app.exec()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
