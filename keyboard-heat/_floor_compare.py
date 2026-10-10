"""底火层「关 / 开」并排对比 —— 验收"低热时柴尖有没有被盖住"就看这张。

先出两套截图，再拼：
    .pyenv\\Scripts\\python.exe _dialprobe_qt.py --phase 3.8
    .pyenv\\Scripts\\python.exe _dialprobe_qt.py --phase 3.8 --no-floor
    .pyenv\\Scripts\\python.exe _floor_compare.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
LEVELS = ["idle", "h05", "h25"]
SCALE = 5
LABEL_W = 120
GAP = 14
ROW_PAD = 10
HEAD = 34


def load(tag, name):
    p = HERE / ("_dialqt_%s_%s.png" % (tag, name))
    if not p.exists():
        raise SystemExit("missing %s — 先跑 _dialprobe_qt.py（带 --no-floor 出 %s）"
                         % (p.name, tag))
    im = Image.open(p).convert("RGB")
    return im.resize((im.width * SCALE, im.height * SCALE), Image.NEAREST)


def font(size):
    for f in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/arial.ttf",
              "C:/Windows/Fonts/segoeui.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


def main():
    rows = [(lv, load("c_nf", lv), load("c", lv)) for lv in LEVELS]
    w, h = rows[0][1].size
    total_w = LABEL_W + w * 2 + GAP + ROW_PAD * 2
    total_h = HEAD + len(rows) * (h + ROW_PAD) + ROW_PAD
    out = Image.new("RGB", (total_w, total_h), (245, 245, 248))
    dr = ImageDraw.Draw(out)
    f_head, f_lab = font(22), font(18)
    dr.text((ROW_PAD + LABEL_W, 5), "底火层 OFF", fill=(20, 20, 24), font=f_head)
    dr.text((ROW_PAD + LABEL_W + w + GAP, 5), "底火层 ON", fill=(20, 20, 24), font=f_head)
    y = HEAD
    for lv, a, b in rows:
        dr.text((ROW_PAD + 10, y + h // 2 - 12), lv, fill=(20, 20, 24), font=f_lab)
        out.paste(a, (ROW_PAD + LABEL_W, y))
        out.paste(b, (ROW_PAD + LABEL_W + w + GAP, y))
        y += h + ROW_PAD
    dst = HERE / "_floor_compare.png"
    out.save(dst)
    print("ok %s -> %s" % (out.size, dst.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
