"""静态校验并修复 bat 启动脚本。

bat 的失败模式特别恶劣：双击没反应、没有任何输出、连报错都不给。所以写完必须
做一遍机械校验，别靠人肉看。检查四件事：

1. 是否纯 ASCII   —— cmd 解析非 ASCII 内容在部分系统上会静默失败
2. 是否有 BOM     —— 带 BOM 的第一行会被当成命令执行
3. goto 标签是否齐全
4. **行尾是否 CRLF** —— 用文本工具写出的 bat 常常是 LF-only 行尾，
   cmd.exe 对这种文件处理有缺陷（尤其 goto/标签定位），同样表现为静默失败。
   这一条自动修掉。

顺带检查引号是否成对。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATS = ["run.bat", "run_qt.bat", "install.bat", "setup.bat", "start.bat"]

out: list[str] = []
ok = True


def fail(msg):
    global ok
    ok = False
    out.append("  [FAIL] " + msg)


def fix_eol(p: Path) -> bool:
    """把 LF-only 转成 CRLF，返回是否做过修改。"""
    raw = p.read_bytes()
    norm = raw.replace(b"\r\n", b"\n")
    if b"\r\n" in raw and norm.count(b"\n") == raw.count(b"\r\n"):
        return False                        # 已经是纯 CRLF
    p.write_bytes(norm.replace(b"\n", b"\r\n"))
    return True


for name in BATS:
    p = HERE / name
    if not p.exists():
        fail("%s 不存在" % name)
        continue

    raw = p.read_bytes()
    out.append("=== %s  (%d bytes) ===" % (name, len(raw)))

    # 1. 非 ASCII
    bad = [i + 1 for i, b in enumerate(raw) if b > 127]
    if bad:
        fail("含非 ASCII 字节共 %d 个，首个在第 %d 字节" % (len(bad), bad[0]))
    else:
        out.append("  [OK]   纯 ASCII")

    # 2. BOM
    if raw[:3] == b"\xef\xbb\xbf":
        fail("带 UTF-8 BOM（第一行会被当命令执行）")
    else:
        out.append("  [OK]   无 BOM")

    # 3. 行尾 -> 顺便修
    crlf = raw.count(b"\r\n")
    lf_total = raw.count(b"\n")
    if lf_total and crlf != lf_total:
        out.append("  [WARN] 行尾混合/LF-only (CRLF=%d, LF=%d) -> 自动转 CRLF"
                   % (crlf, lf_total))
        changed = fix_eol(p)
        raw = p.read_bytes()
        out.append("  [OK]   已改写为 CRLF: %s" % changed)
    else:
        out.append("  [OK]   行尾 CRLF 统一")

    text = raw.decode("ascii", errors="replace")
    lines = text.splitlines()

    # 4. goto 标签
    labels = {m.group(1).lower() for m in re.finditer(r"^[ \t]*:(\w+)", text, re.M)}
    gotos = {m.group(1).lower() for m in re.finditer(r"\bgoto\s+:?(\w+)", text, re.I)}
    missing = gotos - labels
    if missing:
        fail("goto 指向不存在的标签: %s" % ", ".join(sorted(missing)))
    else:
        out.append("  [OK]   goto 标签齐全 %s"
                   % (("-> " + ", ".join(sorted(labels))) if labels else "(无 goto)"))

    # 5. 引号配对（逐行）
    bad_quote = False
    for i, ln in enumerate(lines, 1):
        if ln.count('"') % 2:
            fail("第 %d 行引号不成对: %s" % (i, ln.strip()[:70]))
            bad_quote = True
    if not bad_quote:
        out.append("  [OK]   引号全部成对")
    out.append("")

out.append("结果：%s" % ("全部通过" if ok else "存在失败项"))
txt = "\n".join(out)
print(txt)
(HERE / "_batcheck.log").write_text(txt, encoding="utf-8")
raise SystemExit(0 if ok else 1)
