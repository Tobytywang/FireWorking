"""悬浮窗布局探针：伪造 service，把几种状态各渲染一帧并截图。

不挂真实钩子、不占单实例锁、不写库 —— 只为了把界面看一眼。
用途是回答"加了键/鼠分解那一行之后，文字有没有溢出圆弧、位置挤不挤"。

    .venv\\Scripts\\python.exe _dialprobe.py            # 篝火（默认）
    .venv\\Scripts\\python.exe _dialprobe.py --digits   # 数字仪表盘
    .venv\\Scripts\\python.exe _dialprobe.py --phase 3.8  # 固定摇曳相位
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import _shot                     # noqa: E402
import overlay_tk                # noqa: E402
from heatcore import load_config  # noqa: E402


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
    phase = None
    if "--phase" in args:
        phase = float(args[args.index("--phase") + 1])
    tag = "d" if digits else "c"

    overlay_tk.HeatDialTk._bind_hotkeys = lambda self: None    # 探针不占全局热键

    service = FakeService()
    dial = overlay_tk.HeatDialTk(service)
    dial._campfire = not digits
    dial._show_camp(not digits)
    dial._boot_done = True          # 跳过开屏动画，直接看稳态
    dial._fade_done = True
    dial.root.attributes("-alpha", 1.0)

    seq = list(SCENES)

    def shoot(name):
        x, y, s = dial.root.winfo_x(), dial.root.winfo_y(), dial.size
        rows = _shot.grab(x, y, s, s)
        out = HERE / ("_dial_%s_%s.png" % (tag, name))
        _shot.write_png(str(out), s, s, rows)
        print("SHOT %-16s %dx%d@%d,%d -> %s" % (name, s, s, x, y, out.name))
        dial.root.after(140, nxt)

    def nxt():
        if not seq:
            dial.quit()
            return
        name, snap = seq.pop(0)
        service.snap = snap
        if phase is not None:
            # 冻结相位：定时器还在跑会累加，两次运行没法比
            dial._phase = phase
            dial._last_t = None
        dial.root.after(220, lambda: shoot(name))     # 等两轮 tick 刷到界面

    dial.root.after(500, nxt)
    print("表盘尺寸 %d，位置 (%d,%d)，视觉=%s，相位=%s"
          % (dial.size, dial.root.winfo_x(), dial.root.winfo_y(),
             "数字" if digits else "篝火", "自由" if phase is None else phase))
    dial.root.mainloop()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
