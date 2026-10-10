"""放大看局部 —— 190px 的盘在对话里看不清细节，验收全靠近它。

    .pyenv\\Scripts\\python.exe _zoom.py _dialqt_c_h50.png 30,40,160,170 4
    .pyenv\\Scripts\\python.exe _zoom.py _dialqt_c_idle.png 40,60,150,170 5 _idle_zoom.png

参数：<源图> <x0,y0,x1,y1> [倍率=4] [输出=源图名_zoom.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src = HERE / sys.argv[1]
    x0, y0, x1, y1 = (int(v) for v in sys.argv[2].split(","))
    scale = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    dst = (HERE / sys.argv[4]) if len(sys.argv) > 4 else \
        src.with_name(src.stem + "_zoom.png")
    im = Image.open(src).convert("RGB").crop((x0, y0, x1, y1))
    im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    im.save(dst)
    print("ok %s  %s  %dx%d  裁剪 %s  %dx%s"
          % (dst.name, im.size, im.width, im.height,
             sys.argv[2], scale, ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
