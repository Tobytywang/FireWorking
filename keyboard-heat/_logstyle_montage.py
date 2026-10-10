"""把 _logstyle_*.png 拼成一张对比图（不依赖第三方库，直接解 PNG）。

用法：.pyenv\\Scripts\\python.exe _logstyle_montage.py [输出文件]
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
import _shot  # noqa: E402

STYLES = ("flat", "bark", "charred", "gnarled")
HEATS = ("idle", "mid")


def read_png(path):
    data = Path(path).read_bytes()
    pos = 8
    w = h = 0
    idat = b""
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif typ == b"IDAT":
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 3 + 1
    rows = []
    prev = bytearray(w * 3)
    for y in range(h):
        f = raw[y * stride]
        line = bytearray(raw[y * stride + 1:(y + 1) * stride])
        # 只实现了用到的 filter 0/1/2（截图脚本固定写 0，这里留个保险）
        if f == 1:
            for i in range(3, len(line)):
                line[i] = (line[i] + line[i - 3]) & 0xFF
        elif f == 2:
            for i in range(len(line)):
                line[i] = (line[i] + prev[i]) & 0xFF
        rows.append(bytes(line))
        prev = line
    return w, h, rows


def crop_scale(w, h, rows, cx0, cy0, cw, ch, k):
    """裁一块 (cx0,cy0,cw,ch) 再最近邻放大 k 倍。返回 (w2, h2, rows2)。"""
    w2, h2 = cw * k, ch * k
    out = []
    for y in range(h2):
        sy = min(h - 1, cy0 + y // k)
        src = rows[sy]
        line = bytearray(b"\x00")
        for x in range(w2):
            i = (cx0 + x // k) * 3
            line += src[i:i + 3]
        out.append(bytes(line))
    return w2, h2, out


def paste(canvas, cw, ch, img, ox, oy):
    iw, ih, rows = img
    for y in range(ih):
        dst = canvas[oy + y]
        src = rows[y][1:]
        # 每行第一个字节是 PNG 的 filter byte，像素从 offset 1 开始
        dst[1 + ox * 3:1 + ox * 3 + iw * 3] = src


def main():
    out = HERE / (sys.argv[1] if len(sys.argv) > 1 else "_logstyle_compare.png")
    k = 2
    cw, ch = 190, 190                     # 直接整盘对比，尺寸一目了然
    pad, gap = 12, 8
    W = pad * 2 + cw * k * len(STYLES) + gap * (len(STYLES) - 1)
    H = pad * 2 + ch * k * len(HEATS) + gap * (len(HEATS) - 1)
    bg = (26, 24, 22)
    canvas = [bytearray(b"\x00" + bytes(bg) * W) for _ in range(H)]

    for r, heat in enumerate(HEATS):
        for c, st in enumerate(STYLES):
            w, h, rows = read_png(HERE / ("_logstyle_%s_%s.png" % (st, heat)))
            assert (w, h) == (190, 190), (st, heat, w, h)
            img = crop_scale(w, h, rows, 0, 0, cw, ch, k)
            paste(canvas, cw, ch, img,
                  pad + c * (cw * k + gap), pad + r * (ch * k + gap))

    _shot.write_png(str(out), W, H, canvas)
    print("拼图 -> %s（%dx%d，上排 idle / 下排 mid，列序 %s）"
          % (out.name, W, H, " / ".join(STYLES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
