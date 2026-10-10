"""Verify the cutout result itself: dump the RGBA the overlay would actually
get, and report alpha statistics + corner RGBA."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import flame  # noqa: E402

from PIL import Image  # noqa: E402

HERE = Path(__file__).parent
for name in ("log-pile.png",):
    p = HERE / "assets" / name
    li = flame.log_image_load(p)
    if li is None:
        print("load FAILED", p)
        continue
    print("=== %s  %dx%d  bbox=%s  datalen=%d (expect %d)"
          % (name, li.w, li.h, li.bbox, len(li.data), li.w * li.h * 4))

    im = Image.frombytes("RGBA", (li.w, li.h), li.data)
    px = im.load()
    print("   corner RGBA  TL=%s TR=%s BL=%s BR=%s"
          % (px[3, 3], px[li.w - 4, 3], px[3, li.h - 4], px[li.w - 4, li.h - 4]))

    a = im.getchannel("A")
    hist = a.histogram()
    total = li.w * li.h
    print("   alpha=0    %d (%.1f%%)" % (hist[0], 100.0 * hist[0] / total))
    print("   alpha=255  %d (%.1f%%)" % (hist[255], 100.0 * hist[255] / total))
    print("   alpha mid  %d (%.1f%%)"
          % (sum(hist[1:255]), 100.0 * sum(hist[1:255]) / total))

    out = HERE / ("_cutout_%s" % name)
    im.save(out)
    print("   saved %s" % out)
