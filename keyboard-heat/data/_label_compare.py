# -*- coding: utf-8 -*-
"""标签被裁对照图：单标签高倍放大 + 标出容器上沿（裁剪线）。

实测（dsf=1.5, width 1144）：
  容器(.cal-scroll) top = 1402.41 CSS → device 2103.6
  改前(line-height:1)：墨迹在 device 2104..2117，顶行被削平
  改后(line-height:14px)：墨迹在 device 2106..2120，完整
"""
from PIL import Image, ImageDraw, ImageFont

DSF = 1.5
X0, X1 = 84, 182          # CSS x：第一个标签 "12月"
Y0, Y1 = 1397, 1425       # CSS y：标签带（含上下留白）
Z = 12                    # 放大倍数
CONT_TOP_CSS = 1402.41    # 容器上沿（裁剪线）
PAD, GAP, TOPBAR = 18, 22, 78

def crop(path):
    im = Image.open(path).convert('RGB')
    b = im.crop((int(X0*DSF), int(Y0*DSF), int(X1*DSF), int(Y1*DSF)))
    b = b.resize((b.width*Z, b.height*Z), Image.NEAREST)
    return b

bb, ba = crop('_lab_before15.png'), crop('_lab_after15.png')

W = PAD + bb.width + GAP + ba.width + PAD
H = TOPBAR + bb.height + PAD
cv = Image.new('RGB', (W, H), (255, 255, 255))
d = ImageDraw.Draw(cv)
def F(sz):
    try: return ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', sz)
    except Exception: return ImageFont.load_default()
d.text((PAD, 6), '月份标签「12月」在 150% 缩放下放大 12 倍', font=F(25), fill=(33, 27, 21))
d.text((PAD, 40), '红色虚线 = 容器(.cal-scroll)上沿。改前字形顶部越过该线 → 被纵向裁剪切平；改后完整落在盒内。',
       font=F(16), fill=(120, 110, 100))

xb, xa = PAD, PAD + bb.width + GAP
d.text((xb, TOPBAR - 32), '改前 line-height:1（顶被切）', font=F(19), fill=(192, 57, 43))
d.text((xa, TOPBAR - 32), '改后 line-height:14px（完整）', font=F(19), fill=(22, 130, 93))
cv.paste(bb, (xb, TOPBAR))
cv.paste(ba, (xa, TOPBAR))

# 容器上沿在裁剪窗口内的 y（两图同页面坐标，故同一相对位置）
line_y = TOPBAR + (CONT_TOP_CSS - Y0) * DSF * Z
for x0, x1 in ((xb, xb + bb.width), (xa, xa + ba.width)):
    for x in range(x0, x1, 22):
        d.line([(x, line_y), (x + 11, line_y)], fill=(214, 48, 48), width=3)
d.text((xb - 2, line_y - 26), '容器上沿', font=F(15), fill=(214, 48, 48))

cv.save('_label_compare.png')
print('saved _label_compare.png', cv.size)
