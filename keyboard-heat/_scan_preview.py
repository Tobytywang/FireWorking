"""Scan horizontal lines of the preview to locate the dark rectangle."""
from __future__ import annotations
from pathlib import Path
from PIL import Image

HERE = Path(r"D:\Workspace\HardWorking\keyboard-heat")
im = Image.open(HERE / "_logpile_preview.png").convert("RGB")
px = im.load()
W, H = im.size
print("preview %dx%d" % (W, H))

for y in (140, 150, 200, 250, 300, 330):
    row = []
    for x in range(0, 380, 20):
        row.append("%3d:%s" % (x, px[x, y]))
    print("y=%3d  %s" % (y, "  ".join(row)))
