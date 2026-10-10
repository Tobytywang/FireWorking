"""Check whether the LANCZOS downsample is what introduces the dark rectangle."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import flame  # noqa: E402

from PIL import Image  # noqa: E402

HERE = Path(__file__).parent
li = flame.log_image_load(HERE / "assets" / "log-pile.png")
im = Image.frombytes("RGBA", (li.w, li.h), li.data)

D = 380.0
cx = cy = D / 2.0
lx, ly, lw, lh = li.box(cx, cy, D)
tw, th = max(1, int(round(lw))), max(1, int(round(lh)))
print("box  left %.2f top %.2f w %.2f h %.2f" % (lx, ly, lw, lh))
print("resize -> %dx%d" % (tw, th))

for tag, resample in (("LANCZOS", Image.LANCZOS), ("NEAREST", Image.NEAREST)):
    small = im.resize((tw, th), resample)
    a = small.getchannel("A")
    hist = a.histogram()
    total = tw * th
    px = small.load()
    print("  %-8s alpha0=%.1f%% alpha255=%.1f%% mid=%.1f%%  corner=%s"
          % (tag, 100.0 * hist[0] / total, 100.0 * hist[255] / total,
             100.0 * sum(hist[1:255]) / total, px[2, 2]))
    small.save(HERE / ("_resized_%s.png" % tag))

# what does the composite look like on the pit colour?
base = Image.new("RGBA", (int(D), int(D)), (42, 36, 28, 255))
small = im.resize((tw, th), Image.LANCZOS)
base.alpha_composite(small, (int(round(lx)), int(round(ly))))
bp = base.load()
print("composite sample inside rect but outside wood (should be 42,36,28):")
for pt in ((55, 155), (320, 155), (55, 320), (200, 150)):
    print("   %s -> %s" % (pt, bp[pt]))
