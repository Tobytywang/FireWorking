# -*- coding: utf-8 -*-
"""一键打包：产物名带版本号，打完打印清单。

用法（在项目根目录）：
    .pyenv\\Scripts\\python.exe build.py

为什么要有这个脚本：
1. **产物名带版本号**（`键盘热度-v1.2.0.exe`）。开发期反复打包，旧产物可能带
   已知缺陷（2026-10-15之前那份双击就 0xC0000409 秒退），文件名不带版本
   就分不清手上跑的是哪一份 —— 这是真实的踩坑，故固化成流程而不是靠记性。
2. 自动把`version.py` 的 BUILD_DATE 写成今天，省得手工改。
3. 打完**逐个列出 dist/ 里的 exe 与时间戳**，方便确认"手上这份是刚打的"。

不删旧产物：故意保留同名不同版本的 exe 并列（文件名带版本号后天然不会互相覆盖），
万一新版有问题，直接换回旧版本即可，不用重新打包。
"""
from __future__ import annotations

import datetime
import io
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION_PY = HERE / "version.py"
SPEC = HERE / "键盘热度.spec"
DIST = HERE / "dist"


def refresh_build_date():
    """把 version.py 里的 BUILD_DATE 更新为今天（只替换该行，不动其它内容）。"""
    today = datetime.date.today().isoformat()
    src = VERSION_PY.read_text(encoding="utf-8")
    new, n = re.subn(r'(?m)^BUILD_DATE\s*=\s*".*"$',
                     'BUILD_DATE = "%s"' % today, src, count=1)
    if n:
        VERSION_PY.write_text(new, encoding="utf-8")
    return today, bool(n)


def load_version():
    """从 version.py 取版本（用正则读，避免 import 时受环境/编码影响）。"""
    src = VERSION_PY.read_text(encoding="utf-8")
    v = re.search(r'(?m)^VERSION\s*=\s*"([^"]+)"', src).group(1)
    app = re.search(r'(?m)^APP_NAME\s*=\s*"([^"]+)"', src).group(1)
    return app, v


def main():
    today, changed = refresh_build_date()
    app, ver = load_version()
    print("版本：%s v%s（构建日期 %s%s）"
          % (app, ver, today, "，已更新" if changed else "，沿用 version.py"))

    py = HERE / ".pyenv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    cmd = [str(py), "-m", "PyInstaller", "--noconfirm", SPEC.name]
    print("打包中（PyInstaller，onefile，约 1–2 分钟）…")
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print("\n打包失败（exit=%d）：" % p.returncode)
        print((p.stdout or "")[-2500:])
        print((p.stderr or "")[-2500:])
        return p.returncode

    DIST.mkdir(exist_ok=True)
    # 只列本次相关的 exe：带版本号的最新那个打勾，其余旧版本提示还能回退
    exes = sorted(DIST.glob("%s-v*.exe" % app), key=lambda f: f.stat().st_mtime,
                  reverse=True)
    print("\n=== dist/ 产物清单（按时间倒序）===")
    for i, f in enumerate(exes):
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
        mark = "  ← 本次打包" if i == 0 else "  （旧版本，可回退）"
        print("  %-34s %6.1f MB   %s%s"
              % (f.name, f.stat().st_size / 1048576,
                 mtime.strftime("%m-%d %H:%M"), mark))
    if not exes:
        print("  （未找到产物）")
        return 1

    # 清理中间目录（保留 dist）
    bld = HERE / "build"
    if bld.is_dir():
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(bld)],
                       capture_output=True)
    print("\n完成。双击 %s 即可运行（不依赖 Python 环境）。" % exes[0].name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())