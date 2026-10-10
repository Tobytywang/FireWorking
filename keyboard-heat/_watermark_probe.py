"""查素材的右下角水印：它会被当成"柴堆内容"算进包围盒，把落位带偏。

对每张图输出：
  · 全图内容包围盒、逐行内容宽度（找真实内容底边，水印在它下面）
  · 右下角区域（x ≥ 0.76W 且 y ≥ 0.84H）的内容包围盒
  · 该区域的 ASCII 图（'#' = 亮像素），直观看水印的形状、离木头多远
  · 水印左侧 120px 隔离带里的内容像素数 —— 为 0 才说明"能整块擦掉"

    .pyenv\\Scripts\\python.exe _watermark_probe.py            # 默认查全部素材
    .pyenv\\Scripts\\python.exe _watermark_probe.py <路径> ...  # 或指定

全用 PIL 的 C 实现（ImageChops.lighter → point → getbbox），2560×1696 毫秒级；
早先那版是 Python 逐像素三重循环，一张图十几秒。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
GEN = HERE.parent / "generated-images"
DEFAULT = [
    ("篝火3（新后景）", GEN / "篝火3.png"),
    ("篝火3_低矮（新前景）", GEN / "篝火3_低矮.png"),
]
LUMA = 40


def mask_of(im: Image.Image, luma: int = LUMA) -> Image.Image:
    """亮于阈值的像素 → 255，其余 0。等价于逐像素 max(r,g,b) >= luma。"""
    r, g, b = im.convert("RGB").split()
    m = ImageChops.lighter(ImageChops.lighter(r, g), b)
    return m.point(lambda i: 255 if i >= luma else 0)


def main(argv):
    items = ([(Path(p).stem, Path(p)) for p in argv[1:]] if len(argv) > 1
             else DEFAULT)
    for name, path in items:
        if not path.exists():
            print("== %s  缺失 %s\n" % (name, path))
            continue
        im = Image.open(path)
        w, h = im.size
        m = mask_of(im)
        box = m.getbbox()               # (left, upper, right, lower)，右下开区间
        print("== %s  %dx%d" % (name, w, h))
        print("   全图内容      x %d..%d  y %d..%d（右下开区间）"
              % (box[0], box[2] - 1, box[1], box[3] - 1))

        # 逐行宽度：从底往上找"真实内容底边"——水印那几行是孤立的窄条
        rows = []
        for y in range(box[1], box[3]):
            bb = m.crop((0, y, w, y + 1)).getbbox()
            rows.append((y, bb[0], bb[2] - 1) if bb else (y, -1, -1))
        real = [r for r in rows if r[1] >= 0]
        gaps = [r for r in rows if r[1] < 0]
        print("   有内容的行    %d 行（y %d..%d 里 %d 行是空的）"
              % (len(real), box[1], box[3], len(gaps)))
        if gaps:
            print("   空行          %s" % _runs([r[0] for r in gaps]))
        # 真实内容底边 = 尾部那段"孤立内容块"（水印）之前的最后一行有内容的行。
        # 直接取 real[-1] 会取到水印 —— 水印跟木头之间隔着一大段全空行，
        # 所以要先把跨过空行的尾部块摘出来。
        real_body, real_tail = real, []
        if gaps:
            tail_start = gaps[-1][0] + 1
            real_body = [r for r in real if r[0] < tail_start]
            real_tail = [r for r in real if r[0] >= tail_start]
            print("   尾部孤立块    y %s  x %d..%d（水印）"
                  % (_runs([r[0] for r in real_tail]),
                     min(r[1] for r in real_tail),
                     max(r[2] for r in real_tail)))
        if real_body:
            print("   真实内容底边  y %d（该行 x %d..%d）"
                  % (real_body[-1][0], real_body[-1][1], real_body[-1][2]))
            print("   裁切线建议    %d（内容底边 +20，且在水印顶 y=%s 之上）"
                  % (real_body[-1][0] + 20,
                     real_tail[0][0] if real_tail else "无水印"))
        # 底部 8 行宽度，直观看水印是不是"窄条"
        print("   底部各行的内容宽度（x 范围）：")
        for y, x0, x1 in real[-8:]:
            print("     y=%4d  x %4d..%4d  宽 %d" % (y, x0, x1, x1 - x0 + 1))

        # 右下角区域
        x_lo, y_lo = int(0.76 * w), int(0.84 * h)
        cbox = m.crop((x_lo, y_lo, w, h)).getbbox()
        if cbox:
            cx0, cy0, cx1, cy1 = (x_lo + cbox[0], y_lo + cbox[1],
                                  x_lo + cbox[2] - 1, y_lo + cbox[3] - 1)
            n = sum(m.crop((x_lo, y_lo, w, h)).point(lambda i: 1 if i else 0)
                    .getdata())
            print("   右下角内容    x %d..%d  y %d..%d  (%d px)"
                  % (cx0, cx1, cy0, cy1, n))
        else:
            cx0 = cx1 = cy0 = cy1 = None
            print("   右下角内容    无")

        # 隔离带：水印左侧 120px 的竖条里有内容吗
        if cbox:
            gx = max(0, cx0 - 120)
            gap = m.crop((gx, y_lo, cx0, h)).getbbox()
            n_gap = 0
            if gap:
                n_gap = sum(m.crop((gx, y_lo, cx0, h))
                            .point(lambda i: 1 if i else 0).getdata())
            print("   隔离带 x %d..%d（水印左侧 120px）内容像素 %d  → %s"
                  % (gx, cx0, n_gap,
                     "水印孤立，可整块擦掉" if n_gap == 0
                     else "水印与木头相连，不能整块擦"))

        # 右下角 ASCII
        cols = 76
        step = max(1, (w - x_lo) // cols)
        print("   右下角 ASCII  x %d..%d  y %d..%d（每字符 %dpx）"
              % (x_lo, w, y_lo, h, step))
        for y in range(y_lo, h, step):
            row = ""
            for x in range(x_lo, w, step):
                v = m.getpixel((x, y))
                row += "#" if v else "."
            if row.strip("."):
                print("     %s" % row)
        print()
    return 0


def _runs(nums):
    """[1605,1606,1607,1610] → '1605..1607, 1610'"""
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if j == i else "%d..%d" % (nums[i], nums[j]))
        i = j + 1
    return "、".join(out)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
