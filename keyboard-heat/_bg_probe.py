"""Diagnose the asset background: what exactly are the 'black' pixels?"""
from __future__ import annotations
from pathlib import Path
from PIL import Image

ASSETS = [
    (r"D:\Workspace\HardWorking\generated-images\篝火.png", "old"),
    (r"D:\Workspace\HardWorking\generated-images\篝火2.png", "new"),
]

for path, tag in ASSETS:
    p = Path(path)
    if not p.exists():
        print("MISSING", p)
        continue
    im = Image.open(p)
    print("=== %s  %s  mode=%s size=%s" % (tag, p.name, im.mode, im.size))
    rgb = im.convert("RGB")
    px = rgb.load()
    w, h = rgb.size

    # corners
    for name, (x, y) in (("TL", (3, 3)), ("TR", (w - 4, 3)),
                         ("BL", (3, h - 4)), ("BR", (w - 4, h - 4)),
                         ("mid-top", (w // 2, 3))):
        print("   %-8s %s" % (name, px[x, y]))

    # background-band histogram: sample a strip near the top edge
    buckets = {}
    for y in range(0, min(60, h)):
        for x in range(0, w, 3):
            m = max(px[x, y])
            b = (m // 16) * 16
            buckets[b] = buckets.get(b, 0) + 1
    top = sorted(buckets.items())
    print("   top-strip luma buckets:", top[:8])

    # how many pixels above the LOG_IMAGE_LUMA_MIN=40 cutoff in that strip?
    over = sum(c for b, c in buckets.items() if b >= 40)
    tot = sum(buckets.values())
    print("   strip pixels with luma>=40: %d / %d  (%.2f%%)"
          % (over, tot, 100.0 * over / max(1, tot)))
