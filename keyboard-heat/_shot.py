"""截取屏幕上指定矩形区域，存成 PNG。

用 ctypes 直接调 GDI，不依赖任何第三方库（这台机器的 .pyenv 只有 pynput）。
关键在 BitBlt 的 CAPTUREBLT 标志 —— 不加它，分层（layered）窗口不会出现在
截屏里，而我们的悬浮窗正是 layered 窗口，那样只会截到一片桌面。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import sys
import zlib

u = ctypes.windll.user32
gdi = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000

DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


def grab(x, y, w, h):
    hdc = u.GetDC(0)
    mem = gdi.CreateCompatibleDC(hdc)
    bmp = gdi.CreateCompatibleBitmap(hdc, w, h)
    old = gdi.SelectObject(mem, bmp)
    gdi.BitBlt(mem, 0, 0, w, h, hdc, x, y, SRCCOPY | CAPTUREBLT)

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h            # 负高度 = 自上而下，省得后面翻转
    bi.biPlanes = 1
    bi.biBitCount = 24
    bi.biCompression = 0

    stride = ((w * 3 + 3) // 4) * 4
    size = stride * h
    buf = ctypes.create_string_buffer(size)
    gdi.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), DIB_RGB_COLORS)
    raw = buf.raw

    gdi.SelectObject(mem, old)
    gdi.DeleteObject(bmp)
    gdi.DeleteDC(mem)
    u.ReleaseDC(0, hdc)

    # BGR (bottom-up 已由负高度解决) -> PNG 需要 RGB 行，每行前加 filter byte 0
    rows = []
    for yy in range(h):
        line = raw[yy * stride: yy * stride + w * 3]
        bgr = bytearray(line)
        bgr[0::3], bgr[2::3] = bgr[2::3], bgr[0::3]      # B<->R
        rows.append(b"\x00" + bytes(bgr))
    return rows


def write_png(path, w, h, rows):
    def chunk(typ, data):
        body = typ + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    out = b"\x89PNG\r\n\x1a\n"
    out += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    out += chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
    out += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(out)


def main():
    x, y, w, h = (int(v) for v in sys.argv[1:5])
    out = sys.argv[5]
    rows = grab(x, y, w, h)

    # 统计：完全相同的像素占比，用来判断"是不是一片纯色/纯桌面"
    from collections import Counter
    colors = Counter()
    for y_ in range(h):
        line = rows[y_][1:]
        for i in range(0, len(line), 3):
            colors[line[i:i + 3]] += 1
    total = w * h
    uniq = len(colors)
    top, topn = colors.most_common(1)[0]
    print("区域 (%d,%d) %dx%d" % (x, y, w, h))
    print("  不同颜色数     : %d" % uniq)
    print("  出现最多的颜色 : #%02X%02X%02X  占 %.1f%%"
          % (top[0], top[1], top[2], 100.0 * topn / total))
    for c, n in colors.most_common(6):
        print("    #%02X%02X%02X  %5.2f%%" % (c[0], c[1], c[2], 100.0 * n / total))

    write_png(out, w, h, rows)
    print("  已保存 -> %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
