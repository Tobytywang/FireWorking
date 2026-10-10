"""键盘热度显示器 —— 主入口。

    python main.py            启动悬浮窗（常驻，退出走托盘菜单）
    python main.py --report   生成历史报告并用浏览器打开
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import traceback
from pathlib import Path

from heatcore import PROJECT_DIR, load_config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="键盘热度显示器")
    ap.add_argument("--report", action="store_true", help="生成历史报告并立即打开")
    ap.add_argument("--out", help="报告输出路径")
    ap.add_argument("--db", help="指定数据库文件（默认用 config.json 里的）")
    ap.add_argument("--qt", action="store_true",
                    help="（保留兼容）PyQt6 可用时自动选用，无需显式传递")
    args = ap.parse_args(argv)

    if args.report:
        import report
        path = report.generate(load_config(), db_path=args.db, output=args.out, open_after=True)
        print("报告已生成：%s" % path)
        return 0

    if not _ensure_runtime():
        return 1
    return _launch_overlay()


def _launch_overlay():
    """优先 PyQt6 版（真透明 + 抗锯齿圆环 + 系统托盘），缺依赖时退回零依赖的 Tkinter 版。

    两个版本共用同一套采集、算法和色阶，切换的只是渲染层，数据格式完全一致。
    """
    try:
        import PyQt6.QtWidgets  # noqa: F401
    except ImportError:
        print("[i] 未检测到 PyQt6，使用 Tkinter 版界面（圆环边缘略有锯齿，操作走全局热键）。")
        print("    想换成 PyQt6 版：运行 setup.bat 装好依赖再启动。")
        from overlay_tk import run as run_tk
        return run_tk()

    from overlay import run as run_qt
    return run_qt()


def _fatal_box(title, text):
    """依赖缺失等致命错误：弹一个置顶提示再退出（pythonw 无控制台，必须可见）。"""
    ctypes.windll.user32.MessageBoxW(
        None, text, title,
        0x00000010 | 0x00040000 | 0x00010000,  # MB_ICONERROR | MB_TOPMOST | MB_SETFOREGROUND
    )


def _ensure_runtime():
    """在单个进程内确认采集依赖（pynput）就绪，缺失则就地安装。

    run.bat 不再为每个依赖另起冷启动 python 进程去嗅探（每次双击白等约 1 秒），
    依赖检查统一挪到这儿：正常情况（已装）零额外进程；只有真缺了才装一次。
    PIL（位图柴堆）缺失时由渲染层自动退回代码绘制，不强制安装。
    PyQt6 缺失时由 _launch_overlay 退回 Tk 版，不强制安装（避免大包下载卡顿）。
    """
    try:
        import pynput  # noqa: F401
        return True
    except ImportError:
        pass
    import subprocess
    import sys
    print("[i] 未检测到 pynput，正在安装（仅需一次）……")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "--disable-pip-version-check", "pynput",
        ])
        return True
    except Exception as exc:  # 装不上（无网等）：弹窗说明，退出
        _fatal_box(
            "键盘热度 · 无法启动",
            "必需的依赖 pynput 未安装，且自动安装失败：\n%s\n\n"
            "请手动运行：\n  python -m pip install pynput\n"
            "或运行项目里的 setup.bat。" % (exc,),
        )
        return False


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # 用 pythonw.exe 启动时没有控制台，异常必须落盘才能查
        log = PROJECT_DIR / "data" / "error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
        raise
