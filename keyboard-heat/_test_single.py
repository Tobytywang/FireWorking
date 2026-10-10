"""验证单实例互斥体：本进程应拿到锁，子进程应拿不到。

单实例是"重复双击"场景的兜底 —— 用户看不到窗口时最常见的动作就是再点一次，
没有这个保护就会叠出好几个圆盘，越叠越难看清。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import heatcore  # noqa: E402

out: list[str] = []
ok = True


def check(name, cond, detail=""):
    global ok
    ok = ok and bool(cond)
    out.append("[%s] %-22s %s" % ("PASS" if cond else "FAIL", name, detail))


first = heatcore.claim_single_instance()
check("本进程首次申请", first is True, first)

child_code = (
    "import sys; sys.path.insert(0, r'%s'); import heatcore;"
    " print('CHILD', heatcore.claim_single_instance())" % HERE
)
res = subprocess.run([sys.executable, "-c", child_code],
                     capture_output=True, text=True, timeout=30)
blob = (res.stdout or "") + (res.stderr or "")
last = blob.strip().splitlines()[-1] if blob.strip() else "<无输出>"
check("子进程申请", "CHILD False" in blob, last)

again = heatcore.claim_single_instance()
check("本进程重复申请", again is True, again)

out.append("")
out.append("结果：%s" % ("全部通过" if ok else "存在失败项"))
text = "\n".join(out)
print(text)
(HERE / "_single.log").write_text(text, encoding="utf-8")
raise SystemExit(0 if ok else 1)
