"""把生成器出的素材加工成可直接贴的 assets/*.png。

    .pyenv\\Scripts\\python.exe _asset_prep.py

每张源图做两件事：

1. **裁掉右下角的水印**（豆包/即梦都会在右下角压一行浅色文字）。不裁的话有两个
   后果：一是那行字会跟着贴到悬浮窗上（黑底已透明，字是亮的，很显眼），二是它会被
   当成"柴堆内容"算进包围盒，把落位和缩放一起带偏。
2. 顺手报一遍**内容包围盒和宽高比** —— `LOG_SLOT_*.w_k` 就是按这个反推高度用的
   （高 = 宽 / 宽高比），换素材时先看这几个数。

`CUT` 是每张图的裁切线：取在真实内容底边之下、水印之上，两边都留了余量。
换素材时按 `_watermark_probe.py` 的输出改。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
GEN = HERE.parent / "generated-images"

# (源图, 目标, 裁切线, 说明)
#   篝火3     ：内容底边 1419，水印 y1605..1661
#   篝火3_低矮：内容底边 1383，水印 y1605..1661
CUT = 40        # 与 flame.LOG_IMAGE_LUMA_MIN 同值，用来量内容包围盒
JOBS = [
    ("篝火3.png", "log-pile.png", 1440, "后景柴堆（画在火焰后面）"),
    ("篝火3_低矮.png", "log-pile-front.png", 1400, "前景柴堆（压住火焰下半段）"),
]


def content_bbox(path: Path):
    """亮于阈值的像素的包围盒 + 宽高比。等价于 flame.log_image_load 的抠图判据。"""
    im = Image.open(path).convert("RGB")
    r, g, b = im.split()
    m = ImageChops.lighter(ImageChops.lighter(r, g), b).point(
        lambda i: 255 if i >= CUT else 0)
    bx = m.getbbox()
    if bx is None:
        return None
    x0, y0, x1, y1 = bx
    return x0, y0, x1 - 1, y1 - 1


def main():
    for src, dst, cut, note in JOBS:
        sp, dp = GEN / src, HERE / "assets" / dst
        if not sp.exists():
            print("跳过（源图不存在）：%s" % sp)
            continue
        im = Image.open(sp).convert("RGB")
        w, h = im.size
        out = im if h <= cut else im.crop((0, 0, w, cut))
        dp.parent.mkdir(parents=True, exist_ok=True)
        out.save(dp, optimize=True)
        bb = content_bbox(dp)
        print("%-16s → %-20s %s" % (src, dst, note))
        print("   裁掉底部 %4dpx      %dx%d  →  %dx%d  (%.2fMB)"
              % (h - out.height, w, h, out.width, out.height,
                 dp.stat().st_size / 1e6))
        if bb:
            x0, y0, x1, y1 = bb
            print("   内容包围盒         x %d..%d  y %d..%d"
                  % (x0, x1, y0, y1))
            print("   内容 %.0f×%.0f       宽高比 %.3f   → 宽 0.62d 时高 %.3fd"
                  % (x1 - x0 + 1, y1 - y0 + 1,
                     (x1 - x0 + 1) / float(y1 - y0 + 1),
                     0.62 / ((x1 - x0 + 1) / float(y1 - y0 + 1))))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
