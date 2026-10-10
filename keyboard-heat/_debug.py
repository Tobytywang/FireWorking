import os
import random
import traceback

out = []

# 1. venv 里装了什么
sp = r"D:\Workspace\HardWorking\keyboard-heat\.venv\Lib\site-packages"
out.append("site-packages: %r" % sorted(d for d in os.listdir(sp) if not d.startswith("_")))

# 2. 逐块复现 demo_data 的生成过程
from demo_data import _blocks_for, _minutes_for_block

rng = random.Random(20260922)
for wd in (True, False, True):
    blocks = _blocks_for(rng, wd)
    out.append("weekday=%s blocks=%r" % (wd, blocks))
    for blk in blocks:
        try:
            rows = _minutes_for_block(rng, *blk)
            out.append("   block %r -> %d rows, head=%r" % (blk, len(rows), rows[:2]))
        except Exception:
            out.append("   block %r FAILED:\n%s" % (blk, traceback.format_exc()))

with open(r"D:\Workspace\HardWorking\keyboard-heat\_debug.log", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
