"""把探针出的热度阶梯拼成一条对比图（低热档是本次验收重点）。

    .pyenv\\Scripts\\python.exe _strip.py                    # 五档全景，3x
    .pyenv\\Scripts\\python.exe _strip.py idle h05 --scale 6  # 只看低热档，放大
"""
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DEFAULT = ["idle", "h05", "h25", "h50", "h100"]
GAP = 8


def main():
    args = sys.argv[1:]
    scale = 3
    if "--scale" in args:
        i = args.index("--scale")
        scale = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    names = args or DEFAULT

    ims = []
    for n in names:
        p = HERE / ("_dialqt_c_%s.png" % n)
        if not p.exists():
            print("missing", p.name)
            return 1
        im = Image.open(p).convert("RGB")
        ims.append(im.resize((im.width * scale, im.height * scale), Image.NEAREST))
    w = sum(i.width for i in ims) + GAP * (len(ims) - 1)
    h = max(i.height for i in ims)
    out = Image.new("RGB", (w, h), (245, 245, 248))
    x = 0
    for im in ims:
        out.paste(im, (x, 0))
        x += im.width + GAP
    dst = HERE / "_dial_strip.png"
    out.save(dst)
    print("ok %s  %s  order=%s  scale=%d" % (out.size, dst.name, " / ".join(names), scale))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
