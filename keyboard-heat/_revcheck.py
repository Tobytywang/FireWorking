# -*- coding: utf-8 -*-
"""反向验证器 —— 把某一行临时注掉，确认测试真的会红。

为什么需要它：**断言最容易的失败方式是空转**。"改好了就绿"只说明两边一致，
说明不了断言真的盯着那行代码 —— 只有"把那行注掉，断言必须变红"才证明它有牙。
这个动作以前每轮都是手工做（改 → 跑 → 还原），容易忘了还原、也容易注错地方。

用法：
  .pyenv\\Scripts\\python.exe _revcheck.py <源文件> <锚点片段> <测试脚本>
  .pyenv\\Scripts\\python.exe _revcheck.py <源文件> "<锚点片段>=><替换文本>" <测试脚本>
  .pyenv\\Scripts\\python.exe _revcheck.py <源文件> "<前置片段> >> <锚点片段>" <测试脚本>
  :: 目标片段不唯一时用 `>>`：取"前置片段那一行"之后的第一个目标行

例：
  .pyenv\\Scripts\\python.exe _revcheck.py overlay.py "p.drawArc(edge_rect," _test_ring.py
  .pyenv\\Scripts\\python.exe _revcheck.py overlay.py "group.addAction(act)" _test_tray.py
  :: 上下文锚点（menu.addSeparator() 有 4 处，靠前置行定位到其中一处）
  .pyenv\\Scripts\\python.exe _revcheck.py overlay.py "menu.addAction(act_report) >> menu.addSeparator()=>pass" _test_tray.py
  :: 表达式级回退（比"注掉"更诚实：把公式换成旧行为，测试该红就必须红）
  .pyenv\\Scripts\\python.exe _revcheck.py flame.py "return (1.0 - a) ** G=>return 1.0" _test_ring.py

它做三件事：备份 → 把**含锚点的那一整行**注掉（或按 `=>` 换成替换文本）→ 跑测试脚本。
跑完无论如何都还原（`try/finally`），并把失败条目打出来。锚点必须**唯一命中一行**，
否则报错退出（宁可不动，也不要猜着注一行）。

**"注掉"与"换掉"不是一回事**：注掉一行常常让测试直接抛异常（例如函数返回 None、
属性消失），那只证明"这行被引用了"，证明不了"断言盯着它的行为"。能换就换成旧行为 ——
测试若仍然全绿，说明断言是空转的。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    src = HERE / argv[1]
    anchor_arg = argv[2]
    test = argv[3]
    if "=>" in anchor_arg:
        anchor, replacement = anchor_arg.split("=>", 1)
        anchor, replacement = anchor.strip(), replacement.strip()
    else:
        anchor, replacement = anchor_arg, None
    # 上下文锚点：`前置片段 >> 目标片段`。目标片段本身不唯一（比如满地都是
    # menu.addSeparator()）时，用唯一的前置行定位到它后面的第一个目标行 ——
    # 否则这类改动根本没法做反向验证（老工具会因为"命中 4 行"直接拒绝）。
    pre = None
    if ">>" in anchor:
        pre, anchor = anchor.split(">>", 1)
        pre, anchor = pre.strip(), anchor.strip()
    if not src.exists() or not (HERE / test).exists():
        print("文件不存在：%s / %s" % (src, HERE / test))
        return 2

    lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    if pre is not None:
        ph = [i for i, ln in enumerate(lines) if pre in ln]
        if len(ph) != 1:
            print("前置锚点必须唯一命中一行，实际命中 %d 行：%s" % (len(ph), pre))
            return 2
        after = [j for j in range(ph[0] + 1, len(lines)) if anchor in lines[j]]
        if not after:
            print("前置锚点之后找不到目标片段：%s" % anchor)
            return 2
        hits = [after[0]]
    else:
        hits = [i for i, ln in enumerate(lines) if anchor in ln]
        if len(hits) != 1:
            print("锚点必须唯一命中一行，实际命中 %d 行：%s" % (len(hits), anchor))
            return 2
    i = hits[0]
    bak = src.with_suffix(src.suffix + ".revbak")
    shutil.copy2(src, bak)
    try:
        indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
        if replacement is None:
            lines[i] = "%s# %s   # 反向验证：临时注掉\n" % (indent, lines[i].strip())
            what = "注掉"
        else:
            lines[i] = indent + replacement + "\n"
            what = "改成 %r" % replacement
        src.write_text("".join(lines), encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run([sys.executable, test], cwd=str(HERE),
                           capture_output=True, text=True, encoding="utf-8", env=env)
        out = (r.stdout or "") + (r.stderr or "")
    finally:
        shutil.copy2(bak, src)
        bak.unlink()

    print("%s %s 第 %d 行（含 %r）后跑 %s：" % (what, argv[1], i + 1, anchor, test))
    print("   " + lines[i].strip())
    fails = [ln.strip() for ln in out.splitlines() if "[FAIL]" in ln]
    tail = [ln.strip() for ln in out.splitlines()
            if ln.startswith("结果：") or ln.startswith("   结果：")]
    print("   %s" % (tail[-1] if tail else "(没跑到收尾，可能直接抛异常)"))
    for ln in fails:
        print("   " + ln)
    if not fails:
        if not tail and r.returncode != 0:
            # 多行语句被从中间注断、或属性/属性被删掉时，测试会直接抛异常而不是打出
            # [FAIL]。这**不是**空转 —— 断言确实读那行；但要看一眼异常对不对路。
            err = [ln.strip() for ln in out.splitlines()
                   if ln.strip().endswith("Error") or "Error:" in ln]
            print("\n反向验证通过（测试崩了）：注掉后 %s" % (err[-1] if err else "直接抛异常"))
            print("   崩掉同样说明这段代码是被依赖的；但若异常发生在断言之外的杂事上，"
                  "就没证明力 —— 先看上面的异常信息。")
            return 0
        print("\n!! 全绿 —— 这些断言是空转的，跟这行代码没关系，必须重写")
        return 1
    print("\n反向验证通过：红了 %d 条 —— 断言确实盯着这行代码" % len(fails))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
