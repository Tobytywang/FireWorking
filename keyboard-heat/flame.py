"""篝火渲染 —— 火苗的几何造型与配色。

两个界面版本都要画火，但绘制能力差得很远：Qt 有渐变、抗锯齿路径和叠加混合模式，
Tk 只有实心多边形、没有逐元素透明度。所以这里只负责算「火苗长什么样」——
轮廓点、每层的颜色、火星位置、柴堆端点，两版各用自己的方式画。造型共享，
渲染方式互不迁就。

造型按「自发光体积」处理（shader-dev / volumetric rendering 的思路）：

**颜色由两个通道共同决定，而不是只由高度决定：**
    密度（离火苗核心的距离）→ 越靠核心越亮、越偏白黄
    半径（离根部/中轴的距离）→ 越远越暗、越偏暗红
只按高度做一条渐变会得到一块死板的色带；密度×半径两个通道才有体积感。

**热度不只改大小，也改颜色**：小火是暗红余烬，旺火才是明亮橙黄。
只缩放不换色，看起来会像同一个图标被拉伸 —— 这是最容易偷懒也最难看的做法。

**摇曳用 fbm 噪声而不是 sin**：纯 sin 摆动看着像钟摆，两个不同频率叠加再让
噪声去扰动轮廓，才有火舌那种不规则的分叉。

隐私边界不变：这里只有几何和数字，不碰任何输入数据。
"""

from __future__ import annotations

import math
from typing import NamedTuple

# ---------------------------------------------------------------- 噪声

_MASK = 0xFFFFFFFF


def _hash1(i: int, seed: int = 0) -> float:
    """整数 → [0,1) 的确定性伪随机。

    用整数位运算而不是 sin：sin 在不同平台上精度有差异，同一份代码画出来的
    火苗可能不一样。这里要的是"每台机器都长一个样"。
    """
    x = (i * 374761393 + seed * 668265263) & _MASK
    x = ((x ^ (x >> 13)) * 1274126177) & _MASK
    return ((x ^ (x >> 16)) & 0xFFFFFF) / float(0xFFFFFF)


def _noise1(x: float, seed: int = 0) -> float:
    """1D 值噪声：格点随机值 + Hermite 平滑插值。"""
    i = math.floor(x)
    f = x - i
    f = f * f * (3.0 - 2.0 * f)
    a = _hash1(i, seed)
    b = _hash1(i + 1, seed)
    return a + (b - a) * f


def _fbm1(x: float, seed: int = 0, octaves: int = 3) -> float:
    """多倍频噪声。火焰轮廓的火舌起伏和火星的随机相位都靠它。"""
    v = 0.0
    amp = 1.0
    freq = 1.0
    total = 0.0
    for _ in range(octaves):
        v += amp * _noise1(x * freq, seed)
        total += amp
        amp *= 0.5
        freq *= 2.03          # 倍频刻意偏离 2.0，打散自相似
    return v / total


# ---------------------------------------------------------------- 热度映射
#
# 「多大算大火」的规则两版界面共用，所以放在零依赖的这半边。

# 满热定在 300 活跃/分（见 heat.full_kpm），而日常办公大多落在 0.2~0.5。
# 直接拿原始热度去画火，屏幕上常年是一小簇余烬 —— 火堆就成了摆设。
# 0.75 次幂把中段抬起来：0.30 → 0.41，0.50 → 0.59，1.00 还是 1.00。
CAMPFIRE_GAMMA = 0.75

# 开屏时火苗先窜一下再落回真实热度（点燃感）。峰值高度，1.0 = 满火。
BOOT_FLARE = 0.42

# 暂停（托盘「暂停记录」）时的热度。
#
# 0.0 = 和空闲**同一个火形**：暂停是个 UI 动作，火不该因此跳一下。历史上这里是
# 0.05，而 0.05 的跨度是 41.3px、空闲是 22.4px —— 也就是**按下暂停火反而变大
# 18.9px**，和本函数注释里写的"火塌成余烬"正好相反。冷端被反复提亮之后更糟：
# 0.05 与 0 的色阶位置几乎一样（0.743 vs 0.740），只剩尺寸在跳。
# 暂停的信号由圆环的琥珀色和托盘文字承担；要一个**更小更暗**的真余烬形态，
# 得给暂停态单独一套尺寸/配色，不能靠这个热度值（flame_height 的下限就是空闲）。
EMBER_HEAT = 0.0


def fire_heat(frac, state="", booting=False, boot_t=0.0):
    """圆环的原始热度 0~1 → 火焰实际接收的热度 0~1。三件事都发生在这里：

    1. gamma 抬中段 —— 原因见 CAMPFIRE_GAMMA 的注释。
    2. 开屏点火：先窜一下（BOOT_FLARE）再落回真实热度。这是"我起来了"
       的唯一提示 —— 静默出现的话，深色桌面上根本发现不了。
    3. 暂停：火塌回空闲那一档（EMBER_HEAT）。**不是**更小更暗的余烬 ——
       见 EMBER_HEAT 的注释，暂停是个 UI 动作，不该让火跳一下。
    """
    if state == "paused":
        return EMBER_HEAT
    h = max(0.0, min(1.0, float(frac))) ** CAMPFIRE_GAMMA
    if booting:
        flare = math.sin(math.pi * boot_t ** 0.7)         # 0 → 1 → 0
        h = max(h, BOOT_FLARE * flare)
    return h


# ---------------------------------------------------------------- 配色

# 黑体辐射色阶。公式来自 shader-dev skill 的 color-palette.md（Planckian locus
# → 线性 sRGB），完整用法是三步链路，缺一步都会难看：
#     1. 色相：色温 → Planckian locus → sRGB，再归一化
#        （只做这步会得到一串纯红 —— 900K 归一化后是 (255,0,0)，像红色 LED）
#     2. 辐射强度：斯特藩-玻尔兹曼 T⁴ —— 越热越亮不是线性的
#     3. Reinhard 色调映射 col/(1+col) —— 焰心才会自然地"烧白"，而不是截断成纯色
# 曝光是唯一的艺术参数：调大焰心更白，调小整簇火更暗。
FIRE_T_MIN = 900.0            # 木柴余烬的色温
FIRE_T_MAX = 2400.0           # 焰心最热处
FIRE_EXPOSURE = 12.0
FIRE_STOPS = 9                # 色阶采样点数，_ramp() 在点间线性插值


def _blackbody_chroma(kelvin: float):
    """色温 → 归一化线性 sRGB 色相。"""
    t = float(kelvin)
    cx = (0.860117757 + 1.54118254e-4 * t + 1.28641212e-7 * t * t) \
        / (1.0 + 8.42420235e-4 * t + 7.08145163e-7 * t * t)
    cy = (0.317398726 + 4.22806245e-5 * t + 4.20481691e-8 * t * t) \
        / (1.0 - 2.89741816e-5 * t + 1.61456053e-7 * t * t)
    dd = 2.0 * cx - 8.0 * cy + 4.0
    X = 3.0 * cx / dd
    Y = 2.0 * cy / dd
    Z = 1.0 - (3.0 * cx + 2.0 * cy) / dd
    r = 3.240479 * X - 1.537150 * Y - 0.498535 * Z
    g = -0.969256 * X + 1.875992 * Y + 0.041556 * Z
    b = 0.055648 * X - 0.204043 * Y + 1.057311 * Z
    m = max(r, g, b, 1e-9)
    return (max(0.0, r) / m, max(0.0, g) / m, max(0.0, b) / m)


def _fire_stop(t: float):
    """色阶上的一点：色温插值 → T⁴ 辐射 → Reinhard → 0~255 RGB。"""
    t = max(0.0, min(1.0, float(t)))
    kelvin = FIRE_T_MIN + (FIRE_T_MAX - FIRE_T_MIN) * t
    radiance = (kelvin / FIRE_T_MAX) ** 4 * FIRE_EXPOSURE
    col = [c * radiance for c in _blackbody_chroma(kelvin)]
    return tuple(round(255.0 * (c / (1.0 + c))) for c in col)


# import 时算一次的色阶表：(位置, (R,G,B))。纯函数、无第三方依赖，
# Tk 版和 Qt 版共用同一张表。
FIRE_RAMP = tuple((i / (FIRE_STOPS - 1.0), _fire_stop(i / (FIRE_STOPS - 1.0)))
                  for i in range(FIRE_STOPS))

# 焰芯混白用的那个"白"。**它不是一个中性的白 —— 它决定了焰芯是"暖白"还是"灰白"。**
#
# 原来取 (255,250,224)：R−G 只有 5、饱和度只有 12%，是**中性白**。混白比例
# 0.70 时把色阶顶端 (235,206,99) 的 R−G 从 29（12.3% of R）冲成 12（4.8%）——
# 暖意被冲掉 2.5 倍。实测渲染出来 h100 焰芯中位色 rgb(152,144,115)：R 和 G
# 只差 8，**是三层里 R−G 最低的一层**（外焰 22 / 中焰 23 / 焰芯 8）。一块低饱
# 和的灰米色被 (192,169,81) 那种全饱和橙黄包围，就会被同时对比推成"偏冷"——
# 用户读到的"绿"就是这个。黑体色阶本身没有绿（H 最高 47.2°、全程 R>G>B）。
#
# 现在取 (255,238,186)：R−G 17（6.7%），混出来是 rgb(249,228,160)（R−G 21，
# H 46.4°，S 36%）。**只动这一个常量就够了**：它只在 flame_colors 的 core
# 上生效，而 _core_gain(0)=0 → 空闲档混白比例是 0，**改它对空闲那团火零影响**
# （用户验收过的空闲观感一个像素不动）。
#
# 度量与候选表见 _core_hue_probe.py 的 B 节。
_CORE_TINT = (255, 238, 186)      # 焰芯：逼近白，但是**暖白**
_EDGE_TINT = (46, 14, 6)          # 外焰边缘：压到暗红

# 焰芯往 _CORE_TINT 混的上限比例（满热时）。热度低时按 _core_gain 缩回去。
_CORE_MIX_MAX_K = 0.70

# 焰芯图层"额外提白"在低热时保留的比例。提白幅度本身由各版自己给上限
# （Qt 渐变 0.62、Tk 实色 0.30），这里只提供 0~1 的热度折扣，见 flame_core_lift_k。
_CORE_LIFT_MIN = 0.12


def _core_gain(t: float) -> float:
    """焰芯亮度随热度的增益，0 → 0、1 → 1，中段略鼓。

    用 heat*(2-heat) 而不是线性的 heat：上半程就接近满值，只有贴近 0 热度
    时才快速收回去 —— 这样 25 度以上的观感和原来几乎一致，只把"冷"那一端
    压下去。线性的话 50 度附近会明显变暗，那是已经看过的效果，不该动。
    """
    t = max(0.0, min(1.0, float(t)))
    return t * (2.0 - t)


def flame_core_lift_k(heat: float) -> float:
    """焰芯图层额外提白的**热度折扣**，0.12 ~ 1.0（各版再乘自己的上限）。

    提白是**燃烧温度**的表达，不是常驻装饰。写成常数就会在 0 热度下把暗红
    一路拉到接近白 —— 柴堆交叉点上冒出一块"灰水滴"，像鬼火。锚点抬到炭化点
    之后，那块芯完全暴露在柴堆之上，这个问题才显形。
    满热时返回 1.0，所以已经验收过的旺火形态逐像素不变。
    """
    return _CORE_LIFT_MIN + (1.0 - _CORE_LIFT_MIN) * _core_gain(heat)


# 空闲时纵向渐变（根部亮 → 尖端暗）保留多少**压暗量**：0.13 = 只压一成三。
# 见 flame_shade_k。不能取 0：那样整层是一条实色，火苗会失去"根亮尖暗"的
# 立体感，看着像一块橙色贴纸。
#
# 0.26 → 0.13 是"加强火的亮度"那轮做的：可见的那一段火焰本来就落在渐变的
# 暗端（见 _GRAD_TIP_COLD_RELIEF），再把尖端压掉 12% 等于两头挤。13% 已经
# 是能保住立体感的下限（实测外焰尖端 (189,131,12) 对根部 (206,148,28)，
# 差 17 个亮度单位，层次还在）。
_COLD_SHADE_MIN_K = 0.13


def flame_shade_k(heat: float) -> float:
    """纵向渐变的**热度折扣**：低热时弱化"尖端冷却"，1.0 = 原样。

    三层火各自从根部（亮）渐变到火尖（暗），那个压暗量是照满热的高度定的。
    空闲时火焰总跨度只有 ~22px（满热的 19%），渐变还没走完就顶到火尖，
    再叠上前景柴堆压掉根部那截 —— **露在柴堆上面的半团恰好是压到最黑的一段**，
    整团读出来是"漆黑"。冷态只保留 26% 的压暗量，整团维持均匀的亮红橙。

    返回值是**压暗量的折扣**（不是保留比例），用的时候交给 _soft_shade。
    用 (1-t)³ 衰减：t=0.5 只差 7.5%、t≥0.8 几乎不动、t=1 完全不变 ——
    满热形态逐像素不变，中高热的观感也守住。
    """
    t = max(0.0, min(1.0, float(heat)))
    return 1.0 - (1.0 - _COLD_SHADE_MIN_K) * (1.0 - t) ** 3


# 外焰往 _EDGE_TINT 压暗的量：冷态比满热**再轻**这么多。见 _edge_mix_k。
# 满热的外焰压暗量是 0.50 - 0.18 = 0.32，本来就比冷态轻；但空闲那一小团火
# 只剩二十来个像素高，外焰再压到 0.50 就把整圈的边缘吃掉一半 —— 整团读出来
# 还是"暗"。
#   0.28 → 冷态 0.22，外焰 (90,18,3) → (158,70,1)
#   0.41 → 冷态 0.09，外焰再亮一档 (206,148,28)，与焰芯 (233,198,83) 的色差
#          仍在（体积感不丢），但整圈不再发黑。
# 再往上加就要小心：外焰和中焰会糊成一层，"外圈先暗、芯子最亮"的体积线索没了。
_EDGE_MIX_COLD_RELIEF = 0.41


def _edge_mix_k(heat: float) -> float:
    """外焰的压暗量 —— 往 `_EDGE_TINT` 混的比例（越大越暗红）。

    满热时等于原来的 `0.50 - 0.18*t`（= 0.32，逐像素不变）；冷态减掉
    `_EDGE_MIX_COLD_RELIEF`，再按热度权重减掉 `_L1_EDGE`（默认 0，见那组旋钮）。
    同样用 (1-t)³ 衰减：t=0.5 只差 0.025、t≥0.8 几乎不动，中高热的外焰观感守住。

    下限夹 0：冷端本来就只剩 0.09，`_L1_EDGE` 给大一点就会减成负数 ——
    负的"混入比例"没有物理意义。夹到 0 即"外焰完全不混暗红、底色与中焰同色，
    层次全靠 KEEP 拉"。
    """
    t = max(0.0, min(1.0, float(heat)))
    k = ((0.50 - 0.18 * t) - _EDGE_MIX_COLD_RELIEF * (1.0 - t) ** 3
         - _L1_EDGE * _l12_weight(t))
    return max(0.0, k)


# 空闲时把色阶位置抬到这里。色阶 0 那一档是 _ramp(0) = (49,0,0) —— 900K 的余烬
# 经 T⁴ 辐射 + Reinhard 压出来的值，物理上没错（余烬本来就几乎不发光），但铺在
# 深色的灶膛底上就是"一团漆黑"，读不出在烧。
#
# 一路抬到这里的轨迹（每一步都是用户看过之后提的要求）：
#     0.28 (133,23,0) —— "看得清"的下限
#     0.52 (189,86,0) —— "再亮一些"：空闲那团火从"融进背景的暗红"变成"一眼看得见在烧"
#     0.74 (217,151,19) —— "亮度还是不太行"：实测空闲焰芯只有 lum 118、外焰尖端 77，
#                          而色阶上 0.75 那儿就有 lum 159 —— 亮度一直有，是冷端没走到。
#                          抬到 0.74 后空闲帧的火焰像素中位亮度 94 → 162（+72%）。
#
# **它不是"把整条色阶提亮"**：抬升带 (1-t)^_IDLE_RAMP_FALLOFF 衰减，中热以上回到
# 恒等，t=1 完全不变 —— 用户验收过的满火（色阶 1.0 = (235,206,99)）逐像素不动。
#
# 代价要说清楚：抬升幅度一大，**中低热的颜色也被一起抬上去了**（色阶位置是连续
# 的，t=0.5 从 0.565 → 0.758）。这是数学上的必然 —— 单调曲线在 t=0 高、在 t=1 回到
# 1，中间不可能压回原样（见 _IDLE_RAMP_FALLOFF 的推导）。热的层次感改由**火苗
# 尺寸**承担：空闲跨度 22px、h50 是 80px、满热 118px，仍然一眼分得开。
_IDLE_RAMP_POS = 0.74

# 上面那个抬升的衰减指数（配合 (1-t)^k 用）。
#
# 重映射是 `t + K(1-t)^n`，它在 t=0 处的导数是 **`1 - nK`**。导数一旦为负，曲线
# 会先往下走再掉头向上 —— 也就是"刚打几个字，火反而暗了"。所以：
#
#       **n ≤ 1/K 是硬约束**（K=0.74 → n ≤ 1.35），它保证整条曲线单调不降。
#
# K 从 0.52 加到 0.74 之后，上一版的指数 3 必须一并收小：n=3 时 nK=2.22，
# 起点导数 −1.22，低谷掉到色阶 0.546（lum 108）—— 相比空闲的 160 是**跌 33%**，
# 眼睛看得出来，等于"越打字火越暗"。指数 1.28 → nK=0.947，全程单调（实测最大
# 回落 0.0%）。
#
# 这个指数比上一版的 3 小很多，意味着衰减更慢、中低热抬得更多 —— 这正是上面
# 那条"代价"。要它小，是因为 K 大了：**K 和 n 是一对，动 K 必须回头看 n。**
_IDLE_RAMP_FALLOFF = 1.28


def _ramp_pos(t: float) -> float:
    """热度 → 色阶位置。只在冷端抬起来，中热以上回到恒等。

    **单调性由 `_IDLE_RAMP_POS * _IDLE_RAMP_FALLOFF ≤ 1` 保证**（t=0 处导数
    `1 − nK ≥ 0`）—— 这是硬约束，见 _IDLE_RAMP_FALLOFF 的推导。
    """
    t = max(0.0, min(1.0, float(t)))
    return t + _IDLE_RAMP_POS * (1.0 - t) ** _IDLE_RAMP_FALLOFF


# 焰芯比中焰**再往色阶上面走**多少（灼热的芯子本来就比外圈温度高）。
#
# 为什么不是"往白里混"：混白会掉饱和度（上上版的"灰水滴"就是这么来的，见
# _CORE_LIFT_MIN 的注释）。沿色阶往上走提的是**亮度和色温**，饱和度反而保得住
# ——(189,86,0) 混白 0.30 得 (209,137,77)（饱和 63%、lum 152），而同亮度的
# 色阶位置 0.68 是 (212,141,7)（饱和 97%、lum 158）。火该有的"亮"是后者。
#
# 满热逐像素不变：`_ramp_pos(1) = 1`，再加 0.18 仍被 `_ramp` 夹回 1.0。
# 衰减同样用 (1-t)³：中热档的焰芯观感已经被验收过，不该被冷端的旋钮顺手改掉。
# 实测（不衰减的那版）中热 h50 的焰芯被推到接近全热的白，整簇火发"洗"。
_CORE_HUE_BUMP = 0.18


def _core_hue_bump(heat: float) -> float:
    """焰芯色阶位置的上移量，冷端有效、满热为 0。"""
    t = max(0.0, min(1.0, float(heat)))
    return _CORE_HUE_BUMP * (1.0 - t) ** 3


# ---- 纵向渐变的转折点 ----
#
# 每层火焰是一条"根部亮 → 尖端暗"的纵向渐变：0 处用根部色，到 `_GRAD_TIP_STOP`
# 处换成尖端色，之后一路保持（尖端是一块实色）。
#
# 这个转折点本该**跟热度走**：空闲时火焰只有 22px 高，且下半段被前景柴堆挡住
# （实测前景柴堆内容顶边 y=115，而空闲主火 root_y=117.5、tip_y=95.1）—— 也就是
# 可见的只有渐变的 **0.11~1.0 段**。转折点若钉在 0.55，可见区有近一半吃的是
# 最暗的那档，用户看到的"不亮"有一半来自这里，跟配色无关。冷态把转折点推到
# 0.87，露出来的那一段就基本是根部色了。
#
# 满热仍是 0.55，逐像素不变；衰减 (1-t)³ 保证中热档只偏一点点（t=0.5 → 0.59）。
_GRAD_TIP_STOP = 0.55
_GRAD_TIP_COLD_RELIEF = 0.32

# ---- 第 1/2 层（外焰 / 中焰）的独立提亮旋钮 ----
#
# 火焰是三层的（外焰 / 中焰 / 焰芯）。焰芯本来就是最亮最白的那一层，
# 所以"再亮一些"只能在外圈这两层上做。但**不能一视同仁地全档提** ——
# 逐层量过之后（_layer_lift_probe.py，帧差掩码取每层真正露出来的像素）：
#
#     lum 中位     空闲    h19    h50   h100        外焰是**唯一一层越旺越暗**的：
#     第1层 外焰    141     94     75      86        空闲 141 → h50 只剩 75。
#     第2层 中焰    170    144    134     152        原因不是没提，是它压暗量的折扣
#     第3层 焰芯    185    159    142     141        方向正好反了：flame_shade_k 在
#                                                    冷态只保留 13%（怕矮火焰发黑），
#                                                    满热却是 100% —— 于是外焰的
#                                                    纵向渐变在旺火时被压满，根部
#                                                    色都保不住。中高热"不亮"的
#                                                    主体就是这一圈，占了 h100 火焰
#                                                    面积的 6402/12900 ≈ 一半。
#
# 而空闲那团火**不欠亮**：外焰 141 / 中焰 170 / 焰芯 185，层次差 29 是它唯一的
# 体积线索。所以在冷端猛提的代价是把层次差压到 11 以下（外圈和中圈糊成一块）。
#
# 于是提亮量按 `_l12_weight` **随热度加权**：冷端几乎不动，中高热才给足。
# 默认旋钮全 0 时 grads 的式子逐项等于上一版，h100 逐像素不变。
#
#   KEEP / KEEP_UP
#        顶端保留比例。原值外焰 0.48、中焰 0.70；`_UP` 是**满热时**再往上加多少。
#        为什么动顶端：纵向渐变是"根亮 → 尖暗"，而露在柴堆上面的那半团恰好
#        落在偏尖的一段（见 _GRAD_TIP_STOP 的推导）—— 尖不提，底下再亮也读不出来。
#        上限感：外焰的 KEEP 追上中焰就不再是"外圈"，两者糊成一层。
#   EDGE 只有第 1 层有：外焰往 _EDGE_TINT 混暗红的比例再减多少（满热时给足）。
#        它对满热最有效 —— 实测满热外焰混 0.32 时 (174,144,68)（R−B 105），
#        减到 0.18 → (199,171,82)（R−B 117）：**亮度和饱和度同向上抬**，
#        这正是"更黄"该走的路。往 _CORE_TINT 混白（LIFT）会掉饱和，不要走。
#   HUE  只有第 2 层留了一个：中焰底端色沿黑体色阶再往上走多少。
#        色阶 0.68 的 (219,157,15) → 0.82 的 (231,193,69)，更亮更白而 R−B 不掉。
#        第 1 层不给它：外焰底端基本被前景柴堆挡住（可见的是偏尖段），
#        抬底端色对观感贡献小，却会顺手把空闲档的层次差压掉。
_L12_HOT = 0.60          # 权重指数，见 _l12_weight
_L1_EDGE = 0.16          # 满热时少混暗红的量（乘权重）
_L1_KEEP = 0.48          # 外焰顶端保留比例（空闲基准 = 原值）
_L1_KEEP_UP = 0.20       # 满热再 +多少（乘权重）
_L2_HUE = 0.09           # 中焰底端色阶上移（乘权重，满热自动封顶）
_L2_KEEP = 0.70
_L2_KEEP_UP = 0.08

#   第 3 层（焰芯）只有 KEEP 一对。它没有 EDGE（焰芯不压暗红）、没有 HUE
#   （色阶位置由 _CORE_HUE_BUMP 管）。
#
#   **焰芯的 KEEP 比中焰低是历史遗留，不是设计**：0.52 写在这里的时候，
#   上面两层还没被单独提亮过 —— 焰芯靠"底端色混了 0.70 的白"自己就够亮。
#   上一轮把外焰/中焰按 _l12_weight 提亮之后，实测 h100 三层的**实际呈现亮度**
#   变成了 外焰 59.6 / 中焰 75.3 / **焰芯 59.6** —— 最内层和被人为压暗的外圈
#   一样暗，比中圈还暗 16 点。用户看到的"灰"就是这个：焰芯顶端压得最狠
#   (0.52 保留) 而它的底色又是最亮的，压完落在中间调，饱和度从 25% 掉到 24%
#   的同时 R−G 只剩 8/152 —— 在 (192,169,81) 那种全饱和橙黄中间就是一块灰米色。
#   见 _core_hue_probe.py 的 A 节。
_L3_KEEP = 0.52          # 焰芯顶端保留比例（空闲基准 = 原值，硬编码搬过来的）
_L3_KEEP_UP = 0.24       # 满热再 +多少（乘权重）
#   0.24 是扫出来的**下限**，不是拍的：焰芯要重新成为"最亮的一层"，
#   h100 中位亮度得越过中焰的 75.3。实测（_core_hue_probe.py B 节）：
#         +0.00 → V 59.6（比中焰暗 15.7，全簇最暗）
#         +0.12 → V 68.6（仍比中焰暗）
#         +0.24 → V 78.0（终于反超，且 S 只有 32% —— 还保得住"白"）
#         +0.36 → V 87.8（过曝，焰芯糊成一块奶油色）
#   同时它把焰芯的 R−G 从 8 抬到 15 —— 观感上从"灰"变"淡金"。

# ---- 上面这几个旋钮在 Tk 版上的等效写法 ----
#
# Tk 只能画实色（没有纵向渐变、没有 alpha），所以"抬高顶端保留比例"这件事
# 在 Tk 上完全没有对应物，得换一种写法。但**提亮幅度必须同源**：同一档热度下
# 两版分叉（Qt 亮了 Tk 还暗）是最难查的一类 bug —— 用户报"还是不亮"时根本
# 不知道自己在看哪一版。所以下面三个值也乘同一个 _l12_weight。
_L1_TK_KEEP = 0.86       # Tk 外焰往灶膛底色混的比例（原来的硬编码就是 0.86）
_L1_TK_KEEP_UP = 0.10    # 满热时再少混这么多（越接近 1 越接近外焰本色）
_L2_TK_MIX_UP = 0.18     # Tk 中焰满热时往焰芯色混的比例（0 = 纯 mid，原样）


def _l12_weight(heat: float) -> float:
    """第 1/2 层提亮幅度的**热度权重**：冷端 0、满热 1。

    用 `t**0.6` 而不是线性：h50 拿到 0.66（而不是 0.5）—— 中热是"打字时一直在看"
    的那一档，值得给足；而空闲 t=0 严格为 0，已验收的空闲观感（层次差 29）
    完全不动。t 很小的时候也不会突然冒一点出来（幂函数在 0 处连续）。
    """
    t = max(0.0, min(1.0, float(heat)))
    return t ** _L12_HOT


def _grad_tip_stop(heat: float) -> float:
    """纵向渐变里"换成尖端色"的位置。满热 = `_GRAD_TIP_STOP`（逐像素不变）。"""
    t = max(0.0, min(1.0, float(heat)))
    return min(0.95, _GRAD_TIP_STOP + _GRAD_TIP_COLD_RELIEF * (1.0 - t) ** 3)


def _ramp(t: float):
    t = max(0.0, min(1.0, float(t)))
    for i in range(len(FIRE_RAMP) - 1):
        f0, c0 = FIRE_RAMP[i]
        f1, c1 = FIRE_RAMP[i + 1]
        if t <= f1:
            k = 0.0 if f1 == f0 else (t - f0) / (f1 - f0)
            return (
                round(c0[0] + (c1[0] - c0[0]) * k),
                round(c0[1] + (c1[1] - c0[1]) * k),
                round(c0[2] + (c1[2] - c0[2]) * k),
            )
    return FIRE_RAMP[-1][1]


def _mix(a, b, k: float):
    return tuple(round(a[i] + (b[i] - a[i]) * k) for i in range(3))


def flame_colors(heat: float):
    """热度 0~1 → (外焰, 中焰, 焰芯) 三个 RGB 元组。

    外焰往暗红压、焰芯往白黄提 —— 两个方向拉开的幅度越大，火苗的体积感越强。
    热度低时芯提得少（余烬没有明亮的芯），热度高时外焰也不那么黑（火旺时
    整簇都被烤亮）。

    焰芯的混白量**没有常数底**：早先是 `0.30 + 0.40*t`，那个 0.30 会让 0 热度
    的暗红 (49,0,0) 被稀释成 (111,75,67) 的暖灰 —— 与"余烬没有明亮的芯"这句
    注释自相矛盾。中焰层的渐变底端直接取 core，于是整簇火在冷态下一起发灰。
    现在改成纯热度驱动（满热仍是 0.70，逐像素不变）。

    底色取自 `_ramp(_ramp_pos(t))` —— 冷端被抬到色阶的 _IDLE_RAMP_POS 处，
    否则空闲的火是 (49,0,0) 的漆黑（见那个常量的注释）。满热时 _ramp_pos(1)=1，
    逐像素不变。
    """
    t = max(0.0, min(1.0, float(heat)))
    pos = _ramp_pos(t)
    mid = _ramp(pos)
    core = _ramp(min(1.0, pos + _core_hue_bump(t)))
    core = _mix(core, _CORE_TINT, _CORE_MIX_MAX_K * _core_gain(t))
    outer = _mix(mid, _EDGE_TINT, _edge_mix_k(t))
    return outer, mid, core


# ---------------------------------------------------------------- 几何

def flame_base_y(cy: float, d: float) -> float:
    """柴堆（也就是火焰根部）离盘心的距离。

    0.27 是被柴堆尺寸反推出来的，不是拍的：灶膛是个圆，越靠下横向越窄，
    而柴堆的长度完全受它约束。基座放 0.315 时最多只能画到盘宽的 18%，
    放 0.27 能到 33% —— 差别就是"两根小火柴"和"一垛柴"。
    再往上抬（0.26 能到 35%）底盘下缘就会空出一块，整簇火看着浮起来。
    """
    return cy + d * FLAME_BASE_Y_K


# 火苗的基准尺寸。三个参数是一套的，改一个就得重看整体比例 ——
# 之前 0.56 / 0.30 散在两版 UI 里各写一份，缩放时两边容易走形。
FLAME_BASE_Y_K = 0.27          # 基座位置（相对盘直径）
FLAME_MAX_H_K = 0.62           # 满热时火苗高度。上限由灶膛半径（0.385d）卡住，
                               # 再高火尖就顶到圆环上了（见 _test_flame.py）
FLAME_ASPECT = (0.62, 0.10)    # 宽/高：0.62 - 0.10×热度。火越旺越修长，
                               # 但满热时仍有 0.52 的宽高比 —— 早先 0.37 太瘦，
                               # 在大圆盘里像根蜡烛
# 零热度（空闲）时仍留的火苗比例。**不是**为了"别让程序看起来挂了"那么低就够 ——
# 它是空闲态唯一的火，得撑得起画面：柴堆 0.53d 宽、0.26d 高，火苗只有 0.09×0.62d
# 就显得"木头太大、火太小"。0.16 是柴堆高度的 ~38%，0.19 提到 ~45% —— 空闲时那团
# 火再大一点才压得住柴堆（0.19×0.62d = 0.118d，仍是满热的 19%，不影响"旺火"的
# 层次感）。往大调要留意：它同时抬高了整条低热曲线（0.05 热度也跟着涨）。
FLAME_IDLE_K = 0.19


def flame_height(heat: float, max_h: float) -> float:
    """热度 → 火苗高度。

    刻意不是线性的：
      · t=0 也留 FLAME_IDLE_K 的余烬小火 —— 完全没火会让人以为程序挂了，
        但也不能小到撑不住柴堆（见上面的注释）
      · 指数 0.72 让中低段增长更明显（小火变大最容易察觉）
      · 高段自然趋缓，不会一下顶到上边界
    """
    t = max(0.0, min(1.0, float(heat)))
    if t <= 0.0:
        return FLAME_IDLE_K * max_h
    return max_h * (FLAME_IDLE_K + (1.0 - FLAME_IDLE_K) * t ** 0.72)


def flame_width(h: float, heat: float) -> float:
    """火苗宽度。大火相对细长一些（h 增长快于 w），否则高热度时会变成一坨。"""
    t = max(0.0, min(1.0, float(heat)))
    return h * (FLAME_ASPECT[0] - FLAME_ASPECT[1] * t)


# ---- 起火点：火焰绕哪一点长大 ----
#
# 火不是从盘底"长上来"的，是从柴堆的**交叉 / 炭化点**烧起来的。所以整簇火焰的形状
# 锚在那一点上、随热度**向四周**均匀缩放：低热时它就是在炭化点上的一小团，旺起来
# 才向上下左右同时铺开。
#
# 与旧版的区别：旧版把形状锚在**底边**（base_y 那条直线），热度只往上长，于是低热
# 时那团火落在柴堆中下部、离炭化点差一截 —— 看着像"还没烧着"。柴堆的炭化黑尖
# 在内容顶边往下 0~25% 一段（实测分布见 _anchor_probe.py），基点就该落在那里。
#
# 起火点在形状里的相对高度（0 = 底边，1 = 火尖）由 flame_anchor_pos() 反推，同时决定
# **满热时火焰落在哪** —— 那个值不是拍的，是让满热火根正好落在火根线上的反解结果。
# 满热形态用户已经验收过，不能因为改基点而变形。
FLAME_ANCHOR_K = 0.16          # 有贴图时：起火点 = 内容顶边往下这个比例处（炭化段里）
FLAME_ANCHOR_POS_FALLBACK = 0.36   # 无贴图时的固定相对高度（= 老参数的取值）


def flame_anchor_y(cx: float, cy: float, d: float, log_image=None) -> float:
    """起火点 y —— 柴堆交叉 / 炭化的那一点，火焰围绕它向四周缩放。

    没贴图时退回"旧版落位"（把形状的锚点等效放回底边），这样代码柴堆那条老路径
    逐像素不变 —— 它有自己一套柴尖几何，不该被贴图素材的调参顺手改掉。
    """
    if log_image is not None:
        _l, top, _r, bottom = log_image.content_rect(cx, cy, d)
        if bottom > top:
            return top + (bottom - top) * FLAME_ANCHOR_K
    return flame_base_y(cy, d) - d * FLAME_MAX_H_K * FLAME_ANCHOR_POS_FALLBACK


def flame_anchor_pos(cx: float, cy: float, d: float, log_image=None) -> float:
    """起火点在火焰形状里的相对高度 —— **反推**出来的，不是常数。

    要同时钉住两个不变量，只有让这个比例跟着柴堆大小走：
      1. 起火点 = 柴堆的炭化交叉点（y 由 FLAME_ANCHOR_K 从素材包围盒算出）
      2. 满热时火根 = base_y（用户验收过的形态：火坐在火根那条线上）
    于是   pos = (base_y − 起火点) / 满热跨度
    柴堆换大换小、起火点跟着上下移动，满热火苗都仍然坐在火根上，低热那团火则
    始终坐在炭化点上。

    早先 pos 写死 0.36，等于把"柴堆宽 0.62d"这一个特例当通例：柴堆一缩小
    （0.62 → 0.53d），起火点下移，满热火根就戳到柴堆底边以下 —— 底边后面是空的，
    被 _logpile_preview.py 的逐行轮廓判定抓到。
    """
    span_full = d * FLAME_MAX_H_K
    if span_full <= 0.0:
        return FLAME_ANCHOR_POS_FALLBACK
    a = flame_anchor_y(cx, cy, d, log_image)
    pos = (flame_base_y(cy, d) - a) / span_full
    # 兜住极端素材：pos < 0 会让火根跑到起火点上面，pos 太大则火尖掉到起火点以下。
    return max(0.0, min(0.85, pos))


class FlameGeom(NamedTuple):
    """一帧火焰的几何。画火、画光晕、算火星都从这里取 —— 免得几处各算一遍算岔。"""

    anchor_y: float     # 起火点（形状锚点）
    root_y: float       # 底边（outline 的 base_y）
    span: float         # 总跨度（root_y − tip_y）
    up: float           # 起火点以上的高度（= 旧版的"火苗高度"）
    w: float            # 最大宽度

    @property
    def tip_y(self) -> float:
        return self.root_y - self.span


def flame_geom(cx: float, cy: float, d: float, heat: float,
               log_image=None) -> FlameGeom:
    """热度 → 火焰几何：形状按 span 缩放，锚点固定在起火点。

    span 用**旧版的高度公式**（所以满热总跨度仍是 0.62d、低热仍是 FLAME_IDLE_K 倍），
    只是不再把 span 全铺在锚点上方 —— 锚点下方也占 flame_anchor_pos() 那一截，
    这就是"从炭化点向四周扩展"。
    """
    a = flame_anchor_y(cx, cy, d, log_image)
    span = flame_height(heat, d * FLAME_MAX_H_K)
    pos = flame_anchor_pos(cx, cy, d, log_image)
    up = span * (1.0 - pos)
    return FlameGeom(a, a + span * pos, span, up,
                     flame_width(span, heat))


def _halfw(u: float) -> float:
    """u=0 根部、u=1 尖顶 → 相对半宽 0~1。

    根部保留一定宽度（火是坐在柴上的，不是从一点长出来），中下部最宽，
    到顶部收成尖。
    """
    return (1.0 - u) ** 0.45 * math.sin(math.pi * (0.12 + 0.88 * u))


def _sway(u: float, t: float, seed: int) -> float:
    """摇曳：越靠尖摆得越大（u 的高次幂），两个不同频率叠加避免像钟摆。

    行波方向刻意做成**从根部往柴尖传**（真实火焰的抖动：燃料在根部被扰动、
    火舌尖往上窜）。相位写成 `k·u − ω·t` —— 等相位面随 t 增大往大 u（尖）走；
    若写成 `+ω·t` 波会从尖往下扫，看着像"火在往下塌"，反直觉。
    """
    return (0.17 * u ** 1.6 * math.sin(u * 3.1 - t * 1.9 + seed)
            + 0.08 * u ** 2.2 * math.sin(u * 5.7 - t * 3.3 + seed * 1.7))


def _tongue(u: float, t: float, seed: int) -> float:
    """火舌：轮廓上的噪声起伏，让边缘不是一条光滑曲线。

    幅度乘 u —— 根部要稳（贴着柴），越往上越张牙舞爪。
    """
    return 1.0 + 0.36 * (_fbm1(u * 3.0 - t * 1.15, seed) * 2.0 - 1.0) * u


# 三层：外焰 / 中焰 / 焰芯。shrink 是相对半宽，seed 错开让三层不同步摆动。
LAYERS = (
    (1.00, 11),
    (0.66, 29),
    (0.34, 53),
)


# ---- 底火层 ----
#
# 火苗拆成两层：
#   · **底火层** —— 固定高度的一团暗火，永远坐在柴尖上；高度不跟热度走
#   · **主火层** —— 上面那三层，随热度缩放
#
# 为什么拆：主火随热度缩小时，柴堆顶部的**炭化黑尖**会整根露在外面 ——
# 低热档看着像"没烧着"（新素材炭化很重，尤其明显）。底火层补上这一段，
# 旺起来之后它更矮更窄、被主火完全包住，视觉上等于不存在。
#
# 高度按柴堆**内容包围盒**推算（有贴图时），换素材自动适配；没贴图退回兜底比例。
# 配色整体压暗：低热时它是"压在炭上的薄焰"，不是第二个火苗。
FLAME_FLOOR_TIP_K = 0.11       # 盖到"内容顶边往下"这个比例处（黑尖密集段里）
FLAME_FLOOR_PAD_K = 0.020      # 再往上多盖一截（相对盘直径）
FLAME_FLOOR_MIN_K = 0.12       # 兜底下限（无贴图 / 包围盒算不出时）
FLAME_FLOOR_ASPECT = 0.62      # 宽/高。窄了像烛芯盖不住柴尖，宽了成一坨包住整个柴堆
FLAME_FLOOR_SEED = 71          # 摇曳相位种子，与 LAYERS 的三层错开


def flame_floor_h(cx: float, cy: float, d: float, log_image=None) -> float:
    """底火层的固定跨度：保证低热时也有一段火焰压住柴堆的炭化柴尖。

    同样挂在起火点上（见 flame_floor_geom）。有贴图时按内容包围盒反推：要盖到
    内容顶边往下 FLAME_FLOOR_TIP_K 那一带（炭化段中上部），再留一点余量。
    """
    if log_image is not None:
        _l, top, _r, bottom = log_image.content_rect(cx, cy, d)
        if bottom > top:
            tip_y = top + (bottom - top) * FLAME_FLOOR_TIP_K
            cover = flame_anchor_y(cx, cy, d, log_image) - tip_y
            return max(d * FLAME_FLOOR_MIN_K, cover + d * FLAME_FLOOR_PAD_K)
    return d * FLAME_FLOOR_MIN_K


def flame_floor_geom(cx: float, cy: float, d: float,
                     log_image=None) -> FlameGeom:
    """底火层几何 —— 与主火同一套锚定规则，只是跨度不跟热度走。"""
    a = flame_anchor_y(cx, cy, d, log_image)
    span = flame_floor_h(cx, cy, d, log_image)
    pos = flame_anchor_pos(cx, cy, d, log_image)
    return FlameGeom(a, a + span * pos, span,
                     span * (1.0 - pos),
                     span * FLAME_FLOOR_ASPECT)


# 底火层的"冷态暖芯"。底火层是铺在炭上的薄焰，色相得比主火更暖更灰；而主火的
# 冷态 core 是饱和度拉满的暗红（B 通道恒为 0），铺在灶膛底上就是一块死红，
# 读不出是"薄薄一层在烧"。所以冷态时把 core 往这里混，随热度再交还给
# flame_colors。
# 数值取的是**旧版 flame_colors(0).core** —— 那一版冷态核心本来就是这种暖灰红，
# 观感跟篝火一起验收过；拿它当"冷态下限色"比重新调一个安全（现在 flame_colors
# 的冷态已经不再返回这个值了，见 _IDLE_RAMP_POS）。
_FLOOR_COLD_CORE = (111, 75, 67)


def flame_floor_colors(heat: float):
    """底火层的 (根部色, 顶端色)。

    不能直接用主火配色：主火的冷态 core 是 B 通道为 0 的纯暗红 —— 铺在灶膛底上
    就是一块死红，读不出是"薄薄一层在烧"。所以冷态先把 core 换成
    _FLOOR_COLD_CORE（暖灰红），保住"暗"但把色相拉开。
    热度越高混得越少 —— 那时候主火已经接管画面了。
    """
    _outer, mid, core = flame_colors(heat)
    core_warm = _mix(core, _FLOOR_COLD_CORE, 1.0 - _core_gain(heat))
    return (_mix(mid, core_warm, 0.42 - 0.20 * heat),
            _mix(_shade(mid, 0.62), core_warm, 0.16))


def outline(cx: float, base_y: float, h: float, w: float, t: float,
            seed: int, shrink: float = 1.0, samples: int = 18):
    """生成一层火焰的闭合轮廓点 [(x, y), ...]。

    点序：沿左半边从根走到尖，再沿右半边回到根。底边自然是直的，
    正好架在柴堆上。
    """
    pts = []
    for side, rng in ((-1.0, range(samples + 1)), (1.0, range(samples, -1, -1))):
        for i in rng:
            u = i / float(samples)
            hw = _halfw(u) * w * shrink * _tongue(u, t, seed)
            y = base_y - h * u
            pts.append((cx + _sway(u, t, seed) * h + side * hw, y))
    return pts


# ---- 盘面分区 ----
#
# 圆环笔宽和灶膛半径原先在两版 UI 里各写了一份，改一处忘一处就会出现
# "Qt 版的柴堆压在圆环上、Tk 版没有"。统一放这里，两版都调这两个函数。

RING_THICK_K = 0.062           # 圆环笔宽，相对盘直径
RING_THICK_MIN = 8.0           # 但再细也不低于 8px（小盘上才不会细成一根线）


def ring_thick(d: float) -> float:
    """圆环的笔宽。"""
    return max(RING_THICK_MIN, d * RING_THICK_K)


def ring_radius(d: float) -> float:
    """圆环的中心线半径。"""
    return d / 2.0 - max(6.0, d * 0.045) - ring_thick(d) / 2.0


def ring_inner_radius(d: float) -> float:
    """圆环的内沿半径 —— 柴堆"贴着边画"要贴的就是这一圈。"""
    return ring_radius(d) - ring_thick(d) / 2.0


RING_EDGE_W_K = 0.011          # 环带轮廓线的宽度，相对盘直径
RING_EDGE_W_MIN = 1.6          # 但再细也不低于 1.6px


def ring_edge_w(d: float) -> float:
    """环带轮廓线的宽度。

    存在的理由见 overlay.py `THEMES` 里 `track_edge` 那段：轨道（未走段）和底盘
    在"浅色桌面 + α≈72%"时会撞成同一个亮度（实测 dark 主题 Δlum −3.9 / ΔRGB 10.7，
    肉眼完全分不出），得有根线把进度条和盘面切开。

    **整条环带描一圈**（外弧 + 内弧 + 两个端头半圆），不是只描外沿。用户第 6 轮报
    「现在只有外圈有，内圈和转角的那个地方，也应该有」—— 只描外沿时环带的内侧和
    弧的两个端头还是虚的，那条线看着像半条边。端头用**包住轨道圆帽的半圆**
    （`ring_edge_cap_radius`），轮廓就闭合了，末尾那个圆头也被圈在里面。
    """
    return max(RING_EDGE_W_MIN, d * RING_EDGE_W_K)


def ring_edge_radius(d: float) -> float:
    """轮廓**外弧**中心线的半径 —— 在环外沿再往外挪半个笔宽（整条线落在带外）。"""
    return ring_inner_radius(d) + ring_thick(d) + ring_edge_w(d) / 2.0


def ring_edge_inner_radius(d: float) -> float:
    """轮廓**内弧**中心线的半径 —— 在环内沿再往里挪半个笔宽。"""
    return ring_inner_radius(d) - ring_edge_w(d) / 2.0


def ring_edge_cap_radius(d: float) -> float:
    """端头半圆的半径 —— 正好包住轨道笔帽（`RoundCap` 的圆头），再往外半个笔宽。

    数值上等于 (ring_edge_radius − ring_edge_inner_radius) / 2：两条弧中心线的
    距离是 thick + edge_w，一半就是 thick/2 + edge_w/2。因为端头半圆的圆心落在
    **环中心线**上、半径取这个值，半圆的两端才能和内外两条弧严丝合缝地接上。
    """
    return ring_thick(d) / 2.0 + ring_edge_w(d) / 2.0


TRACK_EDGE_ALPHA_MIN = 0.0     # 轮廓线不透明度的下限（0 = 两个端点严格反相）
# 曲线指数：1.0 = 严格线性反相（`1 − bg_alpha`，用户话的字面意思）。
# 改成 <1 会把**中段**抬亮而**端点一动不动**（0^k = 0、1^k = 1），想要"72% 那档线再
# 清楚一点"就调它。实测代价与收益见 `_edge_alpha_probe.py` 的 gamma 一节。
TRACK_EDGE_ALPHA_GAMMA = 1.0


def track_edge_alpha(bg_alpha: float) -> float:
    """环带轮廓线的**不透明度** —— 与底盘不透明度**反相**（用户第 7 轮要求）。

    用户原话：「也为他设计透明度，但是它的透明度和整体的透明度是反着来的」，
    并且把两个端点都点名了（把「整体透明度」换算成底盘不透明度就是）：

        底盘不透明度 100%（盘面实心）→ 线 0%  （看不见）
        底盘不透明度   0%（盘面全透）→ 线 100%（画满）

    也就是 `1 − bg_alpha`，和恒为 1 的旧行为只差这一个旋钮。

    反相**是对的**，不是纯粹照办：这条线存在的唯一理由是"底盘自己交代不清进度条的
    边界"（见 overlay.py `THEMES.track_edge`：浅色桌面 + α≈72% 时轨道 lum 81.4 撞
    底盘 84.8）。底盘越实心，它和轨道之间那点差就越由 `THEMES.plate` 决定 ——
    α=1 时 dark 盘面 lum 27、轨道 81，差 54，线纯属多余；底盘全透明时盘面根本不参与，
    环带直接压在桌面上，边界就只剩这条线能交代。所以"底盘越实、线越淡"既符合用户的
    直觉，也正好把线留在它真正被需要的那几档。

    **代价要记住**：α 居中时线是半透明的，它只能把两种颜色"拉开 1−α 的比例"——
    实测 28% 不透明的线在 light 主题撞车档只能拉开 ~25 的分离度（定色线是 117）。
    所以判据不能拿定色线的门槛（25）去卡它，改看 max(盘面自己, 线)（见
    `_test_ring.py` 第 7 节与 `_edge_alpha_probe.py`）。

    注意 α=1 时线**完全消失**（不是"很淡"）—— 那是用户点名的端点，别擅自加保底；
    `TRACK_EDGE_ALPHA_MIN` 只在真的要临时抬底时才改。
    """
    a = float(bg_alpha)
    a = 0.0 if a < 0.0 else (1.0 if a > 1.0 else a)
    return max(TRACK_EDGE_ALPHA_MIN, (1.0 - a) ** TRACK_EDGE_ALPHA_GAMMA)


def pit_radius(d: float) -> float:
    """灶膛（火塘那块暗底）的半径：圆环内沿再往里收一点点。"""
    return ring_inner_radius(d) - max(1.0, d * 0.008)


# ---- 柴堆：整个界面的视觉锚点 ----
#
# 柴堆的尺寸**不跟火苗缩放**：火苗在低热时只有几个像素，柴堆要是也跟着缩，
# 空闲/刚启动时盘里就是一片黑 —— 用户根本不知道这东西在不在。
#
# 造型参考真实篝火照片（用户给的参考图）：几根木头从左右两侧往中间**上方**搭，
# 柴尾张开、柴尖收拢交错 —— 是"塔"不是"床"。后对柴尖收在火口上方（不交叉），
# 前对柴尖互相**交错**（左柴尖越过中轴、右柴尖越过中轴，高度略错开，
# 像真柴堆里随手搭的十字）。前对画在火焰图层之上、背光。
#
# 长度不是系数拍的：柴尾落在灶膛圆周上（"贴着圆环内沿"贴的就是这一圈）。
# 盘径、笔宽一变，长度和倾角会自己跟着变，不用手调。
LOG_BUTT_DEG = 50.0            # 后对柴尾在灶膛圆周上的位置：自正下方起算，往两侧张
LOG_TIP_GAP_K = 0.045          # 后对柴尖离中轴的距离：塔尖留一道细缝，看得见是两根
LOG_TIP_RISE_K = 0.172         # 后对柴尖比火根（火焰根部）高多少（相对盘直径）。
                               # 调小 → 后对更平、收拢点更靠下（仍明显高于中对柴尖与前对
                               # 交叉点，三层才分得开；与 前对姿态角差守住 ≥12°）。
                               # 原 0.200 偏陡，塔尖像戳太高。
LOG_TIP_MARGIN = 1.0           # 柴尾离灶膛边沿留的余量（px）

# 前面那对（画在火焰图层**之上**）：柴尾比后对低（更靠观众），柴尖朝上、
# **越过中轴互相交错**，两头高度略错开 —— 完美对称的 X 会一眼假。
# 交错要"过"得足够多（0.085d），柴尖伸出交叉点一大截，才是参考照片里
# 两根柴互相搭着的十字；只过一点点会粘成一个回旋镖。
LOG_FRONT_DEG = 40.0           # 前对柴尾的角度：比后对低、更靠观众
LOG_FRONT_CROSS_K = 0.085      # 柴尖越过中轴的距离（相对盘直径）
LOG_FRONT_TIP_HI_K = 0.105     # 左柴尖的高度（相对盘直径，比火根高）
LOG_FRONT_TIP_LO_K = 0.085     # 右柴尖的高度：比左边低一点，错开

# 中间那对（画在火焰**后面**、后对之上）：低火时火焰缩成一小簇，后对（高架的 Λ）
# 和前面那垛柴之间会露出一块空档，塔看着像悬着的。中对的柴尾角介于前后对之间、
# 柴尖在中轴附近收拢，正好把这块空档填上 —— 柴塔读起来是层层叠上去的，不是两截。
LOG_MID_DEG = 45.0             # 柴尾角度：前后对（40°/50°）之间
LOG_MID_GAP_K = 0.020          # 柴尖细缝：比后对略窄，塔更收拢
LOG_MID_TIP_K = 0.130          # 柴尖高度：落在后对柴尖与前对交叉点之间的空档里

# 三层笔宽（暗底 / 木身 / 受光面），相对盘直径。三笔叠出圆润的木柴感。
# 比早先粗一档（0.064 → 0.078）：柴本来就要有分量，细笔画出来像牙签。
LOG_PEN = (0.094, 0.078, 0.032)

# 木柴受光面往上抬这么多（相对盘直径），光就从上面来，看着才像圆柱
LOG_LIFT_K = 0.010

# 三对柴：back 最远（先画），mid 填中间空档，front 最近（火焰之上后画）
LOG_PAIRS = ("back", "mid", "front")

# 最前面那根「端向柴」：一根几乎正对观众（视角方向）、略微向盘心内侧偏的短粗木桩。
# 它画在所有火焰图层的**之上**，专门去挡火焰轮廓那条平直的底边 —— 柴塔是镂空的，
# 那条直底边会从缝隙里漏出来，看着像火「坐在一条硬边上」。端向柴的端面（年轮椭圆）
# 朝观众，投影上就是一块粗短的横木桩截面 + 一点探入火里的柴身，正好压住中段底边。
LOG_FORE_DX_K = 0.0           # 中心横向偏移：0 = 正对中央，最大化遮挡中段底边
LOG_FORE_DY_K = -0.040        # 中心相对火根向上：腾出更圆的截面，同时仍沉到火根下
LOG_FORE_RX_K = 0.200         # 圆柱半径（截面横向半长，也决定横向覆盖火焰底边）
LOG_FORE_RY_K = 0.100         # 近端面高度（比旧 0.058 圆，才像斜切的木头不是薄饼）
LOG_FORE_BODY_K = 0.062       # 圆柱长度（沿轴探入火里 → 纵向透视的来源）
LOG_FORE_TILT_DEG = 14.0      # 圆柱轴相对竖直的倾角（斜躺着探入火里）
LOG_FORE_PERSP = 0.62         # 远端面透视收缩（远端比近端窄）


def log_endpoints(d: float, pair: str = "back"):
    """一对柴的端点（相对灶膛圆心，向下为 +y）：[(柴尾, 柴尖), ...]，左柴在前。

    柴尾在灶膛圆周的 ±角度 方向上，半径减掉半个笔宽和一点余量 —— 灶膛边沿离
    圆环内沿只差几个像素（见 pit_radius），所以"柴尾落在圆周上"就等于"柴贴着
    圆环内沿画"。

    pair="back"：柴尖收在中轴两侧、比火根高一大截（火口上方，不交叉）
    pair="mid" ：柴尖也在中轴附近收拢（细缝更窄），高度落在后对与前对之间 ——
                 专门填低火时两截柴塔之间的空档
    pair="front"：柴尖**越过中轴**互相交错，且左右高度略错开（随手搭的十字）
    """
    pen_half = max(1.6, d * LOG_PEN[0]) / 2.0
    reach = max(0.0, pit_radius(d) - pen_half - LOG_TIP_MARGIN)
    deg = {"front": LOG_FRONT_DEG, "mid": LOG_MID_DEG}.get(pair, LOG_BUTT_DEG)
    a = math.radians(deg)
    bx, by = reach * math.sin(a), reach * math.cos(a)
    if pair == "front":
        # 左柴的尖搭到右边、比右柴的尖高一点；右柴的尖搭到左边
        tips = [(d * LOG_FRONT_CROSS_K,
                 d * (FLAME_BASE_Y_K - LOG_FRONT_TIP_HI_K)),
                (-d * LOG_FRONT_CROSS_K,
                 d * (FLAME_BASE_Y_K - LOG_FRONT_TIP_LO_K))]
    elif pair == "mid":
        ty = d * (FLAME_BASE_Y_K - LOG_MID_TIP_K)
        tips = [(-d * LOG_MID_GAP_K, ty), (d * LOG_MID_GAP_K, ty)]
    else:
        ty = d * (FLAME_BASE_Y_K - LOG_TIP_RISE_K)
        tips = [(-d * LOG_TIP_GAP_K, ty), (d * LOG_TIP_GAP_K, ty)]
    return [((-bx, by), tips[0]), ((bx, by), tips[1])]


def log_span(d: float, pair: str = "back") -> float:
    """单根柴的长度（柴尾 → 柴尖）。跟盘径严格成正比 —— 两端点都按 d 缩放。"""
    (bx, by), (tx, ty) = log_endpoints(d, pair)[0]
    return math.hypot(bx - tx, by - ty)


def log_pile(cx: float, base_y: float, d: float, heat: float, mid, style=None,
             pair: str = "back"):
    """一对柴（两根）。

    返回一组"可画形状"，而不是两条线 —— 每根柴包含：

        shadow_pts / shadow        暗底轮廓（整根，最下层）
        bands [(pts, rgb), ...]    木身，沿轴向切成 1~5 条色带（朝柴尖那头渐黑）
        lit_pts / lit_color        受光面（贴着上沿的一条窄带）
        streaks [(pts, rgb), ...]  树皮沟纹
        ends [[(pts, rgb), ...]]   断面年轮（默认不画，见 _LOG_STYLES.ends）

    全部是「点列 + 颜色」，两版 UI 只负责把点连成面：Tk 的 canvas 连旋转都
    没有，所以断面也是采样成多边形喂给它的，不用 drawEllipse。

    **u = 0 是柴尾（靠圆环那侧），u = 1 是柴尖（靠火那侧）** —— 炭化按 u 递增：
    柴尾还是新茬、柴尖烧成黑炭，热起来时柴尖还会返出一点暗红。
    样式由 style 决定（见 _LOG_STYLES），默认取 LOG_STYLE_DEFAULT。

    pair="front" 时整根压暗、受光面改成火烤出来的暖边 —— 这一对是画在火焰
    图层之上、背光看过去的那两根，不压暗就会"贴"在火上，层次反而糊掉。
    """
    cfg = _LOG_STYLES.get(style or LOG_STYLE_DEFAULT, _LOG_STYLES[LOG_STYLE_DEFAULT])
    t = max(0.0, min(1.0, float(heat)))
    oy = base_y - d * FLAME_BASE_Y_K                    # 灶膛圆心
    w = d * LOG_PEN[1]                                  # 木身名义宽度
    front = pair == "front"
    body = _mix((126, 82, 42), mid, 0.10 + 0.20 * t)
    lit = _mix((192, 144, 88), mid, 0.14 + 0.34 * t)
    bark = _mix(body, (40, 26, 14), 0.50)
    face = _mix(lit, (236, 208, 160), 0.50)             # 断面新茬：偏亮偏黄
    ring = _mix(bark, (150, 104, 56), 0.35)             # 年轮线
    soot = (24, 20, 18)
    ember = (198, 74, 16)                               # 烧红的柴尖
    if front:
        # 背光：柴身没有正面光，只有火从后面烤出来的一圈暖边。
        # 断面也要压暗 —— 朝外的切口背对着火，亮起来会跟后对的新茬抢视线。
        body = _mix(body, (40, 26, 16), 0.42)
        bark = _mix(bark, (28, 18, 12), 0.40)
        face = _mix(face, (64, 42, 26), 0.58)
        ring = _mix(ring, (44, 28, 18), 0.30)
        lit = _mix(mid, (255, 170, 96), 0.30 + 0.34 * t)
    shadow_col = _mix((58, 36, 20) if not front else (30, 20, 14),
                      mid, 0.05 + 0.10 * t)

    def char_at(u):
        """炭化程度 0~1。指数 0.7 让中段就积起一层烟熏色 —— 不然只有最末
        几个像素是黑的，画在盘里根本看不出来。"""
        return cfg["char"] * max(0.0, min(1.0, u)) ** 0.7

    # 沟纹要不要跟着炭化断开成两段（不然一条亮纹会一路画进炭里）
    nseg = 2 if (cfg["streaks"] and cfg["char"] > 0.0) else 1

    out = []
    for idx, (b, tp) in enumerate(log_endpoints(d, pair)):
        p0 = (cx + b[0], oy + b[1])                     # 柴尾（外侧，靠圆环）
        p1 = (cx + tp[0], oy + tp[1])                   # 柴尖（内侧，靠火）
        ux, uy = _unit(p0, p1)
        nx, ny = -uy, ux
        ang_deg = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        length = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) or 1.0
        # 两根都微微往下垂。n = (-uy, ux) 在左右两侧指向相反（左侧偏下、
        # 右侧偏上），所以符号要翻一下，不然一根垂、一根翘。
        bend = cfg["bend"] * w * (1.0 if idx == 0 else -1.0)
        cap_u = (w * 0.5) / length                      # 圆头的长度（换算成 u）

        def axis_at(u, p0=p0, p1=p1, nx=nx, ny=ny, bend=bend, cfg=cfg, w=w):
            """u → (x, y, 半宽)。带侧弯、锥度、中段鼓节。"""
            off = bend * math.sin(math.pi * u)
            # 锥度刻意不对称：柴尾切得齐，柴尖被烧得细
            wear = 0.5 * abs(2.0 * u - 1.0) + 0.5 * max(0.0, u) ** 1.6
            taper = 1.0 - (1.0 - cfg["taper"]) * wear
            bulge = 1.0 + cfg["bulge"] * math.exp(-((u - 0.44) / 0.16) ** 2)
            return (p0[0] + (p1[0] - p0[0]) * u + nx * off,
                    p0[1] + (p1[1] - p0[1]) * u + ny * off,
                    w * 0.5 * taper * bulge)

        def strip(u0, u1, scale=1.0, up=0.0, cap_tip=False, cap_butt=False, n=10,
                  axis_at=axis_at, nx=nx, ny=ny, cap_u=cap_u):
            """沿中心线取一段，两侧按法向偏移成闭合多边形。

            cap_tip / cap_butt 控制两端是否补圆头。**柴尾必须是平切** ——
            圆头 + 亮断面就是"子弹头"的来源（参考照片里柴尾都是平的切口）。
            """
            us = [u0 + (u1 - u0) * i / float(n) for i in range(n + 1)]
            if cap_butt:
                us = [u0 - cap_u * 0.9, u0 - cap_u * 0.55] + us
            if cap_tip:
                us = us + [u1 + cap_u * 0.55, u1 + cap_u * 0.9, u1 + cap_u]
            left, right = [], []
            for u in us:
                x, y, hw = axis_at(u)
                if u < u0 and cap_butt:
                    k = max(0.0, 1.0 - ((u0 - u) / cap_u) ** 2) ** 0.5
                elif u > u1 and cap_tip:
                    k = max(0.0, 1.0 - ((u - u1) / cap_u) ** 2) ** 0.5
                else:
                    k = 1.0
                hw *= k
                left.append((x + nx * hw * scale, y + ny * hw * scale - up))
                right.append((x - nx * hw * scale, y - ny * hw * scale - up))
            return left + right[::-1]

        # 木身：沿轴向切色带，越靠柴尖越黑。柴尾向外延伸一小段（u<0，轴向
        # 外推）：平切没有圆头的外凸，不补这一段的话柴尾会离圆环内沿空出
        # 好几个像素，"贴着边画"就名存实亡了。
        butt_ext = cap_u * 0.62
        nb = cfg["band"]
        bands = []
        for i in range(nb):
            um = (i + 0.5) / nb
            ch = char_at(um)
            col = _mix(body, soot, ch * 0.60)           # 炭别压到纯黑，会融进灶膛底色
            col = _mix(col, lit, 0.05 + 0.14 * t)
            # 炭里返出暗红：热度高时烧得透亮，没火时余烬也留着一点微光
            col = _mix(col, ember, (0.34 if front else 0.22) * ch * t + 0.20 * ch)
            u0 = i / nb - 0.04
            if i == 0:
                u0 = -butt_ext
            bands.append((strip(max(-butt_ext, u0), min(1.0, (i + 1) / nb + 0.04),
                                0.86, cap_tip=(nb == 1)), col))

        # 树皮沟纹：沿轴向的细条，带一点起伏，不是笔直的。会炭化的样式里
        # 按 0.5 断成两段，各用自己那半的炭化程度上色。
        # sgn 必须有：法向 n 在左右两根柴上方向相反（叉积在镜像下翻转），
        # 不翻符号的话两根柴的沟纹会朝同一侧偏，看着像同一根柴复制错了。
        sgn = 1.0 if idx == 0 else -1.0
        streaks = []
        for k in range(cfg["streaks"]):
            off = -0.55 + 1.10 * (k + 0.5) / cfg["streaks"]
            for s in range(nseg):
                lo = 0.10 + 0.80 * s / nseg
                hi = 0.10 + 0.80 * (s + 1) / nseg
                col = _mix(bark, soot, char_at((lo + hi) / 2.0) * 0.62)
                pl, pr = [], []
                for i in range(7):
                    u = lo + (hi - lo) * i / 6.0
                    x, y, hw = axis_at(u)
                    c = sgn * hw * (off + 0.16 * math.sin(u * 9.0 + k * 2.7))
                    pl.append((x + nx * (c + hw * 0.09), y + ny * (c + hw * 0.09)))
                    pr.append((x + nx * (c - hw * 0.09), y + ny * (c - hw * 0.09)))
                streaks.append((pl + pr[::-1], col))

        # 断面年轮：默认不画 —— 参考照片里看不到亮切口，亮椭圆正是"子弹头"
        # 观感的另一半来源。想看新茬可以开 styles 里的 ends。
        ends = []
        if cfg["ends"]:
            for u in (0.0, 1.0):
                x, y, hw = axis_at(u)
                ch = char_at(u)
                f = _mix(face, soot, ch * 0.86)
                f = _mix(f, ember, 0.30 * ch * t)
                rr = _mix(ring, soot, ch * 0.80)
                ends.append([
                    (_ellipse(x, y, hw * 0.42, hw, ang_deg), f),
                    (_ellipse(x, y, hw * 0.26, hw * 0.62, ang_deg), rr),
                    (_ellipse(x, y, hw * 0.14, hw * 0.34, ang_deg), _mix(f, rr, 0.35)),
                ])

        out.append({
            "shadow_pts": strip(-butt_ext, 1.0, 1.0, cap_tip=True),
            "shadow": shadow_col,
            "bands": bands,
            # 受光面只画到没被炭吃掉的长度，免得一条亮线一路伸进黑柴尖
            "lit_pts": strip(0.03, 0.96 - 0.42 * cfg["char"], 0.26, up=w * 0.22),
            # 前对的受光面本身就是暖的（背光），再往火色上拉就过曝了
            "lit_color": lit if front else _mix(lit, mid, 0.10 + 0.30 * t),
            "streaks": streaks,
            "ends": ends,
        })
    return out


def log_draw_list(pile):
    """把 log_pile 的结果摊平成 [(点列, rgb), ...] —— 绘制顺序就是列表顺序。

    两版 UI 都用同一个顺序画，层叠关系（暗底 → 木身 → 受光面 → 沟纹 → 断面）
    就只有一处定义。
    """
    draw = []
    for lg in pile:
        draw.append((lg["shadow_pts"], lg["shadow"]))
        draw.extend(lg["bands"])
        draw.append((lg["lit_pts"], lg["lit_color"]))
        draw.extend(lg["streaks"])
        for end in lg["ends"]:
            draw.extend(end)
    return draw


def log_fore(cx: float, base_y: float, d: float, heat: float, mid, style=None):
    """最前面一根端向柴（近乎正对观众、略向盘心内侧偏）。

    返回一组可画形状（与 log_pile 同构，但只有 5 块）：

        shadow_pts / shadow   暗影：贴近近端面的小光晕，整根最底层
        tube_pts / tube       柱身：连接近/远两端面长轴母线的四边形（纵向透视的轮廓）
        far_pts / far         远端面（透视收缩、烧得更黑，藏在柱身里只露一点）
        face_pts / face       近端面（朝观众的年轮椭圆）—— 圆柱斜躺着探入火里，
                              所以这一侧是带年轮的木头截面，不再是浮在火前的薄饼
        rings [(pts, rgb)...] 年轮两圈（透视压扁）

    **位置刻意压在火焰平底边（base_y）上**：近端面中心略沉到火根下，柱身沿轴
    向斜向上、略向盘心内侧探入火里，合起来把 base_y 那条直线的中段整个盖住。

    配色走 front 的背光调色（同处火焰之前）：近端面朝火的这一侧烧得最黑、返一点
    暗红；柱身是背光面，整体压暗。
    """
    cfg = _LOG_STYLES.get(style or LOG_STYLE_DEFAULT, _LOG_STYLES[LOG_STYLE_DEFAULT])
    t = max(0.0, min(1.0, float(heat)))
    body = _mix(_mix((126, 82, 42), mid, 0.10 + 0.20 * t), (40, 26, 16), 0.42)
    face = _mix(_mix((192, 144, 88), mid, 0.14 + 0.34 * t), (64, 42, 26), 0.58)
    ring = _mix((150, 104, 56), (44, 28, 18), 0.30)
    soot = (24, 20, 18)
    ember = (198, 74, 16)
    shadow_col = _mix((30, 20, 14), mid, 0.05 + 0.10 * t)
    ch = cfg["char"]

    ang = LOG_FORE_TILT_DEG
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    cx0 = cx + d * LOG_FORE_DX_K
    cy0 = base_y + d * LOG_FORE_DY_K
    r = d * LOG_FORE_RX_K           # 圆柱半径 = 截面横向半长
    ry = d * LOG_FORE_RY_K          # 近端面高度（比旧值圆，才像斜切的木头）
    Lb = d * LOG_FORE_BODY_K        # 圆柱长度（沿轴探入火里 → 纵向透视）
    pf = LOG_FORE_PERSP             # 远端面透视收缩

    # 圆柱轴：自近端面(朝观众)沿 ang 斜向上、向盘心内侧探入火里
    axx, axy = -math.sin(math.radians(ang)), -math.cos(math.radians(ang))
    fx, fy = cx0 + axx * Lb, cy0 + axy * Lb

    # 近端面（朝观众的截面，年轮）
    face_pts = _ellipse(cx0, cy0, r, ry, ang)
    fcol = _mix(face, soot, 0.45 * ch)
    fcol = _mix(fcol, ember, 0.22 * ch * t + 0.16 * ch)

    rc1 = _mix(ring, soot, 0.55 * ch)
    rc1 = _mix(rc1, ember, 0.18 * ch * t + 0.12 * ch)
    rc2 = _mix(rc1, soot, 0.30)
    ring1 = _ellipse(cx0, cy0, r * 0.64, ry * 0.64, ang)
    ring2 = _ellipse(cx0, cy0, r * 0.32, ry * 0.32, ang)

    # 远端面：透视收缩、烧得更黑，藏在柱身里只露一点截面
    far_pts = _ellipse(fx, fy, r * pf, ry * pf, ang)
    farc = _mix(face, soot, 0.62 * ch)
    farc = _mix(farc, ember, 0.14 * ch * t + 0.10 * ch)

    # 柱身：连接近/远两端面长轴（旋转后 ±(r·ca, r·sa)）两条母线的四边形。
    # 远端更窄，四边形自然收拢 → 这就是"纵向透视"的轮廓来源。
    Ln = (cx0 - r * ca, cy0 - r * sa)
    Rn = (cx0 + r * ca, cy0 + r * sa)
    Lf = (fx - r * pf * ca, fy - r * pf * sa)
    Rf = (fx + r * pf * ca, fy + r * pf * sa)
    tube_pts = [Ln, Rn, Rf, Lf]

    # 暗影：仅贴近端面的小光晕（不包住整个柱身，否则会压到圆环）
    shadow_pts = _ellipse(cx0, cy0, r * 1.05, ry * 1.06, ang)
    return {
        "shadow_pts": shadow_pts, "shadow": shadow_col,
        "tube_pts": tube_pts, "tube": body,
        "far_pts": far_pts, "far": farc,
        "face_pts": face_pts, "face": fcol,
        "rings": [(ring1, rc1), (ring2, rc2)],
    }


def fore_draw_list(fore):
    """把 log_fore 的结果摊平成 [(点列, rgb), ...]，绘制顺序即列表顺序。

    由远及近：暗影 → 远端面 → 柱身 → 近端面 → 年轮。远端面先画、被柱身盖住
    大半，只露顶端一点截面，读起来是"木头斜着钻进火里"。
    """
    return [(fore["shadow_pts"], fore["shadow"]),
            (fore["far_pts"], fore["far"]),
            (fore["tube_pts"], fore["tube"]),
            (fore["face_pts"], fore["face"])] + list(fore["rings"])


# 端向柴最多画几块（暗影 / 远端面 / 柱身 / 近端面 / 年轮×2）。Tk 版按这个数预建画素。
FORE_ITEMS_MAX = 6


def _unit(p0, p1):
    ex, ey = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(ex, ey) or 1.0
    return ex / L, ey / L


def _ellipse(x, y, rx, ry, ang_deg, n=14):
    """采样成多边形的椭圆。rx 沿木柴轴向（被透视压扁），ry 垂直于轴向。

    不用"椭圆图元"是因为 Tk 的 canvas 不能旋转 oval —— 采样成多边形，
    两版就能画同一个东西。
    """
    a = math.radians(ang_deg)
    ca, sa = math.cos(a), math.sin(a)
    pts = []
    for i in range(n):
        th = 2.0 * math.pi * i / n
        ex, ey = math.cos(th) * rx, math.sin(th) * ry
        pts.append((x + ex * ca - ey * sa, y + ex * sa + ey * ca))
    return pts


# 四个样式。柴堆的**布局**（后对围拢 + 前对交错）是共用的，这里只管质感：
#   taper   两端相对中段的宽度（锥度）—— 柴尖额外收细（被火啃掉的那头）
#   bend    侧弯幅度，单位 = 柴宽（两根都微微往下垂）
#   bulge   中段鼓节幅度（柴宽倍数）
#   streaks 树皮沟纹条数
#   ends    断面年轮。默认全关：亮切口椭圆是"子弹头"观感的来源之一，
#           参考照片里也看不到断面
#   char    炭化：1 = 靠火的柴尖烧成黑炭，柴尾还是新茬
#   band    木身沿轴向切几条色带（1 条 = 单色；炭化需要多条才过渡得开）
_LOG_STYLES = {
    "flat":    dict(taper=1.00, bend=0.00, bulge=0.00, streaks=0, ends=False, char=0.0, band=1),
    "bark":    dict(taper=0.88, bend=0.04, bulge=0.04, streaks=3, ends=False, char=0.0, band=1),
    "charred": dict(taper=0.86, bend=0.05, bulge=0.05, streaks=3, ends=False, char=1.0, band=5),
    "gnarled": dict(taper=0.82, bend=0.10, bulge=0.13, streaks=2, ends=False, char=0.35, band=3),
}

LOG_STYLES = tuple(_LOG_STYLES)


def _style_items(cfg) -> int:
    """一个样式下一根柴最多画几块。沟纹在会炭化的样式里断成两段。"""
    nseg = 2 if (cfg["streaks"] and cfg["char"] > 0.0) else 1
    return 1 + cfg["band"] + 1 + cfg["streaks"] * nseg + (6 if cfg["ends"] else 0)


# 用户选定的默认：树皮纹 + 柴尖碳化（charred 就是这两个特征的组合）。
# 没写在配置里就用它；配置里写别的样式名就按名字取。
LOG_STYLE_DEFAULT = "charred"

# 一根柴最多会画几块：暗底 + 若干色带 + 受光面 + 沟纹 + 断面（2 端 × 3 圈）。
# Tk 版按这个数给**每一对**柴预建画素（前后两对各一套），任何样式都不许超
# （见 _test_flame.py）。
LOG_ITEMS_MAX = 2 * max(_style_items(c) for c in _LOG_STYLES.values())


# ---------------------------------------------------------------- 火星

class SparkField:
    """上升的火星。

    不用真正的粒子系统（要维护生命周期、随机重置，还得担心状态在暂停/恢复时错乱），
    改成**纯函数**：第 i 颗火星的位置完全由 (时间, 序号) 算出来，没有状态。
    好处是帧率再低也不会漂、暂停恢复不会突变，代价是每颗火星的轨迹是固定周期的。
    """

    def __init__(self, seed: int = 7):
        self.seed = seed

    def at(self, t: float, heat: float, cx: float, base_y: float, h: float):
        """返回 [(x, y, r, alpha), ...]，越往上越小越淡。"""
        n = int(round(2 + 7 * max(0.0, min(1.0, heat))))
        out = []
        for i in range(n):
            s = self.seed + i * 17
            period = 1.7 + 1.6 * _hash1(i, s)
            k = ((t / period) + _hash1(i + 101, s)) % 1.0
            spread = h * (0.26 + 0.34 * _hash1(i + 202, s))
            x = (cx + (_hash1(i + 303, s) - 0.5) * spread
                 + 0.10 * h * math.sin(t * 2.2 + i))
            y = base_y - h * (0.42 + 0.74 * k)
            r = 0.9 + 1.4 * (1.0 - k)
            a = (1.0 - k) ** 1.7 * (0.30 + 0.70 * heat)
            out.append((x, y, r, a))
        return out


# ---------------------------------------------------------------- Qt 渲染
#
# 下面这段是 PyQt6 专用的画法。刻意延迟 import —— 上面那些几何函数保持零
# 第三方依赖，Tk 版只 import 上半部分，不会因为这台机器没装 PyQt6 就崩掉。

def _shade(c, k):
    """亮度缩放，k < 1 压暗。"""
    return tuple(max(0, min(255, round(v * k))) for v in c)


def _lift(c, k):
    """向白提亮。"""
    return tuple(max(0, min(255, round(v + (255 - v) * k))) for v in c)


def _soft_shade(c, base: float, k: float):
    """弱化版的 `_shade`：`k` 是**压暗量的折扣**（1 = 原样，0 = 完全不压）。

    注意别直接写 `_shade(c, base * k)` —— `_shade` 的第二个参数是**保留比例**，
    乘下去是压得更狠，方向正好相反。
    """
    return _shade(c, 1.0 - (1.0 - base) * k)


def _layer_path(pts):
    from PyQt6.QtGui import QPainterPath

    path = QPainterPath()
    path.moveTo(pts[0][0], pts[0][1])
    for x, y in pts[1:]:
        path.lineTo(x, y)
    path.closeSubpath()
    return path


# 用位图素材贴图当柴堆。两张图、两个层次，方向由**所在的槽位**决定：
#
#     后景（overlay.log_image）        → 柴堆（篝火2）
#     火焰（底火层 + 三层主火）
#     前景（overlay.log_image_front）  → 柴堆（低矮篝火），压住火焰下半段和平直底边
#
# 贴图不随热度"烧红/炭化"（那是逐像素配色，位图只能整张贴），但落位全自动：
# 按**内容包围盒**（不是整张图）锚定 —— 素材换一张、构图变了，柴堆依然坐正。
# 早先按整图比例定位，换图就会浮起/压偏几像素。
# 落位参数在 LOG_SLOT_* 里（相对盘直径），改完跑 _logpile_preview.py 肉眼验收。
LOG_IMAGE_DEFAULT = ""
LOG_IMAGE_LUMA_MIN = 40      # 内容包围盒的亮度阈值：max(r,g,b) ≥ 它才算"柴"


class ImageSlot(NamedTuple):
    """一张柴堆贴图的落位参数（全部相对盘直径）。"""

    w_k: float          # 内容宽度
    sink_k: float       # 内容底边沉到火焰根部（flame_base_y）下方多少
    dx_k: float         # 水平微调（+ = 向右）
    dy_k: float         # 垂直微调（+ = 向下）


# 后景柴堆 —— 画在火焰**后面**（篝火3：高瘦柴塔 + 顶部炭化黑尖，火从它顶上冒出来）。
# 0.53 是"整个篝火缩小一圈"的结果：0.62 时柴堆横跨盘宽的 62%，冷态火苗只有
# 一小撮，木柴显得太大。素材内容宽高比 2.05，所以柴堆高 = 0.53/2.05 = 0.259d。
LOG_SLOT_BACK = ImageSlot(0.53, 0.030, 0.0, 0.0)
# 前景柴堆 —— 画在火焰**前面**（篝火3_低矮：矮而宽，压住火焰下半段和那条平直底边）。
# 宽度刻意小于后景（0.53）：前景只盖中段，后景的两侧和柴尖还露得出来。
#
# 0.41 是按"必须盖住底火层的平直底边"反推的下限（逐行轮廓判定，见
# _logpile_preview.py）：再小一档，低热时底火层的底边就会从柴堆顶沿上方露出来。
# 往上调会让前景越来越抢镜、后景的柴尖越来越少。
LOG_SLOT_FRONT = ImageSlot(0.41, 0.045, 0.0, 0.0)

LOG_SLOTS = {"back": LOG_SLOT_BACK, "front": LOG_SLOT_FRONT}


class LogImage:
    """一张抠好底的柴堆位图 + 它的内容包围盒 + 落位参数。

    包围盒用来把**内容**（而不是整张图）锚到火焰根部：素材的黑边留白有多少、
    柴堆在画面里偏上偏下，都不影响最终落位。
    """

    __slots__ = ("data", "w", "h", "bbox", "slot")

    def __init__(self, data, w, h, bbox, slot=LOG_SLOT_BACK):
        self.data = data
        self.w = w
        self.h = h
        self.bbox = bbox            # (x0, y0, x1, y1) 像素坐标；右下为开区间
        self.slot = slot            # ImageSlot：这张图贴在哪、多大

    def box(self, cx: float, cy: float, d: float):
        """画布上的绘制矩形 (left, top, w, h) —— 整张贴图的落位。"""
        x0, _y0, x1, y1 = self.bbox
        s = (d * self.slot.w_k) / max(1.0, float(x1 - x0))
        bottom = flame_base_y(cy, d) + d * self.slot.sink_k
        left = cx - (x0 + x1) * 0.5 * s + d * self.slot.dx_k
        top = bottom - y1 * s + d * self.slot.dy_k
        return left, top, self.w * s, self.h * s

    def content_rect(self, cx: float, cy: float, d: float):
        """柴堆实际占据的边界 (left, top, right, bottom) —— 自检不压圆环用。"""
        lx, ly, lw, _lh = self.box(cx, cy, d)
        x0, y0, x1, y1 = self.bbox
        s = lw / float(self.w)
        return lx + x0 * s, ly + y0 * s, lx + x1 * s, ly + y1 * s


def log_image_load(path, slot="back"):
    """读入位图、把近黑背景抠成透明、量出内容包围盒。

    slot 见 LOG_SLOTS：back = 贴到火焰后面，front = 贴到火焰前面。
    返回 LogImage；PIL 缺失或读取失败返回 None（调用方应退回代码绘制）。

    抠图用 PIL 自己的 C 实现（逐像素 max → 查找表 → alpha 通道 → getbbox），
    不用 Python 循环 —— 2560×1696 那张图逐像素跑要 1 秒多，两张就是启动时肉眼
    可见的卡顿；换成 C 实现是毫秒级，结果完全一致（_test_flame.py 有对拍）。
    """
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return None
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return None
    r, g, b, a = im.split()
    m = ImageChops.lighter(ImageChops.lighter(r, g), b)    # 逐像素 max(r,g,b)
    # 近黑底（生成器 anti-alias 出来是 1~30 的深灰，不是纯 0）抠成透明，
    # 按亮度比例留 alpha —— 边缘软过渡，不会在深色灶膛上留一圈亮边。
    # 木头上的暗色阴影（更亮）保留，否则会"镂空"。
    lo = LOG_IMAGE_LUMA_MIN
    lut = [0 if i < lo else (255 if i >= lo + 24 else int(255 * (i - lo) / 24.0))
           for i in range(256)]
    alpha = m.point(lut)
    if a.getextrema() != (255, 255):        # 素材自带透明：按位相乘，别丢掉
        alpha = ImageChops.multiply(alpha, a)
    im.putalpha(alpha)
    bbox = alpha.getbbox()                  # alpha=0 的像素不算内容
    if bbox is None:                        # 整张图都是黑的？当作加载失败
        return None
    return LogImage(im.tobytes(), im.width, im.height, bbox,
                    LOG_SLOTS.get(slot, LOG_SLOT_BACK))


# LogImage → QImage 的缓存：同一次运行里素材不变，没必要每帧重建一个 6MB 的位图。
# 值与 LogImage 一起存，既做有效性判断，也保证 bytes 不被回收（QImage 不持有它）。
_QT_IMAGE_CACHE = {}


def _qt_log_image(li):
    key = id(li)
    hit = _QT_IMAGE_CACHE.get(key)
    if hit is not None and hit[0] is li:
        return hit[1]
    from PyQt6.QtGui import QImage
    qi = QImage(li.data, li.w, li.h, li.w * 4, QImage.Format.Format_RGBA8888)
    _QT_IMAGE_CACHE[key] = (li, qi)
    return qi


def _blit_log_image(p, li, cx, cy, d):
    """把位图柴堆按 LogImage.box() 画上去（位置由内容包围盒推出，见 LogImage）。"""
    from PyQt6.QtCore import QRectF, Qt
    lx, ly, lw, lh = li.box(cx, cy, d)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawImage(QRectF(lx, ly, lw, lh), _qt_log_image(li))


def draw_campfire_qt(p, cx, cy, size, heat, t, spark_field=None, samples=26,
                     log_style=None, log_image=None, log_image_front=None,
                     floor=True):
    """在 QPainter 上画一簇篝火。cx/cy 是圆盘中心，size 是盘直径。

    log_style 见 LOG_STYLES；None = 用 LOG_STYLE_DEFAULT。
    log_image 给一个 LogImage（slot="back"）就贴**后景**柴堆（画在火焰后面）。
    log_image_front 给一个 LogImage（slot="front"）就贴**前景**柴堆 —— 画在火焰
    之上，专用来压住火焰的下半段（轮廓那条平直底边画在圆盘上很生硬）。
    floor=False 关掉底火层（见 FLAME_FLOOR_*），低热时柴尖会整根露出来。
    spark_field：SparkField 实例 = 用它；None = 新建默认的（照常放）；
    **False = 这一帧不放火星**（暂停态用）。三者别混，见第 5 步的注释。

    火焰的几何全部来自 flame_geom：形状锚在**起火点**（柴堆交叉/炭化的那一点），
    随热度向四周缩放 —— 低热时就是炭化点上的一小团，不是从盘底往上伸的小火苗。

    绘制顺序对应真实的光学层次（与 config 里的贴图槽位一一对应）：
        光晕（加法混合，把周围底盘烤亮）
        → 后景柴堆（篝火2）
        → 后对柴 / 中对柴（代码柴堆时）
        → 炭火（柴堆缝隙里的余烬）
        → 底火层（不随热度缩，压着柴尖）
        → 火焰三层（外焰 → 中焰 → 焰芯，每层一条纵向渐变）
        → 前对柴 / 端向柴（代码柴堆时）或**前景柴堆**（低矮篝火）
        → 火星（最上层）
    """
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import (QBrush, QColor, QLinearGradient, QPainter,
                             QPen, QRadialGradient)

    d = float(size)
    heat = max(0.0, min(1.0, float(heat)))

    base_y = flame_base_y(cy, d)        # 柴堆落位用的地面参考（火焰自己的锚点见下）
    g = flame_geom(cx, cy, d, heat, log_image)
    root_y, h, w = g.root_y, g.span, g.w
    # outer 在第 3.5 步按层重算（见 _L1_*），这里只取 mid / core。
    _outer, mid, core = flame_colors(heat)

    prev_mode = p.compositionMode()

    # ---- 1. 光晕：加法混合 —— 火焰周围那一圈被烤亮的暖光 ----
    gx, gy = cx, root_y - h * 0.28
    gr = h * 1.05 + d * 0.06
    # 衰减刻意做得比"看起来对"更快：光晕半径比灶膛大，尾巴会溢到桌面上去。
    # 悬浮窗是真透明的，溢出去的部分会叠在桌面上 —— 慢衰减会留下一圈脏脏的橙雾。
    a0 = int(58 + 96 * heat)
    glow = QRadialGradient(QPointF(gx, gy), gr)
    glow.setColorAt(0.00, QColor(mid[0], mid[1], mid[2], a0))
    glow.setColorAt(0.32, QColor(mid[0], mid[1], mid[2], int(a0 * 0.42)))
    glow.setColorAt(0.62, QColor(mid[0], mid[1], mid[2], int(a0 * 0.11)))
    glow.setColorAt(1.00, QColor(0, 0, 0, 0))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(glow))
    p.drawEllipse(QPointF(gx, gy), gr, gr)
    p.setCompositionMode(prev_mode)

    # ---- 2. 后景柴堆 ----
    # 位图贴图模式：贴一张抠掉黑底的 PNG，跳过代码绘制的三对柴塔 + 端向柴。
    if log_image is not None:
        _blit_log_image(p, log_image, cx, cy, d)

    if log_image is None:
        # 代码绘制：全部是多边形（形状见 log_pile）：暗底 → 色带 → 受光面 →
        # 树皮沟纹 → 断面。宽度按盘直径给，不跟火苗缩放 —— 火苗可以小到
        # 看不见，柴堆始终在。
        p.setPen(Qt.PenStyle.NoPen)
        for pts, col in log_draw_list(log_pile(cx, base_y, d, heat, mid, log_style)):
            p.setBrush(QBrush(QColor(*col)))
            p.drawPath(_layer_path(pts))

        # ---- 2.5 中对柴堆：填后对与前垛之间的空档（低火时那块悬空的暗档）----
        # 同样画在火焰后面，受光与前对一致（不被火烤，正常照明）。
        for pts, col in log_draw_list(
                log_pile(cx, base_y, d, heat, mid, log_style, pair="mid")):
            p.setBrush(QBrush(QColor(*col)))
            p.drawPath(_layer_path(pts))

    # 柴堆缝隙里的炭火。挂在**柴堆底面**上而不是起火点：炭火物理上在柴堆内部下方，
    # 画在起火点会变成一块悬在柴尖上的暗红圆盘（低热时整个露在外面，很难看）。
    # 半径不跟火苗缩放（为了"没火时也有锚点"），亮度跟热度走。
    p.setPen(Qt.PenStyle.NoPen)
    er_r = max(w * 0.60, d * 0.15)
    er = QRadialGradient(QPointF(cx, base_y), er_r)
    er.setColorAt(0.0, QColor(core[0], core[1], core[2], int(80 + 165 * heat)))
    er.setColorAt(1.0, QColor(mid[0], mid[1], mid[2], 0))
    p.setBrush(QBrush(er))
    p.drawEllipse(QPointF(cx, base_y), er_r, er_r * 0.70)

    # ---- 3. 底火层：跨度固定、压暗配色，永远盖着柴尖 ----
    # 这就是"火苗分成两个图层"里的下层：跨度不跟热度走，主火缩到再小它也顶在
    # 柴尖上（避免黑色炭尖整根露出来）。配色刻意压低 —— 低热时它是压在炭上的
    # 薄焰，旺起来被主火整个包住，看不出有第二层。
    fg = flame_floor_geom(cx, cy, d, log_image) if floor else None
    if fg is not None:
        f_bottom, f_top = flame_floor_colors(heat)
        grad = QLinearGradient(QPointF(cx, fg.root_y), QPointF(cx, fg.tip_y))
        grad.setColorAt(0.00, QColor(*f_bottom))
        grad.setColorAt(0.62, QColor(*f_top))
        grad.setColorAt(1.00, QColor(*f_top))
        p.setBrush(QBrush(grad))
        p.drawPath(_layer_path(
            outline(cx, fg.root_y, fg.span, fg.w, t, FLAME_FLOOR_SEED, 1.0,
                    samples)))

    # ---- 3.5 主火层三层 ----
    # 每层的纵向渐变：根部亮（燃料足）、尖端暗（冷却）。
    # 三层底色不同 —— 外焰压暗红、焰芯提白，横向就拉开了体积感。
    # 两个折扣都跟热度走：
    #   flame_core_lift_k —— 提白幅度（冷态不提白，余烬没有白芯）
    #   flame_shade_k     —— 尖端压暗量（冷态火焰矮，渐变压太狠会整团发黑）
    # 满热时两个都返回 1.0，已验收的旺火形态逐像素不变。
    shade_k = flame_shade_k(heat)
    # 第 1/2 层按 _L1_* / _L2_* **单独**提亮（见那组常量的推导）。底端色在这里
    # 重算一遍（而不是直接用 flame_colors 返回的 outer / mid），因为 _L2_HUE
    # 要把色阶位置再抬一点。默认旋钮全 0 时重算结果与原式逐分量相等 ——
    # 同一组公式、同一个 heat —— 所以空闲与满热都逐像素不变。
    lw = _l12_weight(heat)     # 别叫 w —— 上面 `w` 是火焰半宽，覆盖了会毁掉几何
    pos = _ramp_pos(heat)
    l1_outer = _mix(_ramp(pos), _EDGE_TINT, _edge_mix_k(heat))
    # _L2_HUE 也乘权重：空闲那团火（lw = 0）就**逐像素不变**，验收过的观感一个
    # 像素都不动 —— 这比"提亮幅度小一点"是更硬的保证。
    l2_mid = _ramp(min(1.0, pos + _L2_HUE * lw))
    l2_core = _ramp(min(1.0, pos + _L2_HUE * lw + _core_hue_bump(heat)))
    grads = (
        (_lift(l1_outer, 0.06),
         _soft_shade(l1_outer, _L1_KEEP + _L1_KEEP_UP * lw, shade_k)),
        (_lift(l2_core, 0.02),
         _soft_shade(l2_mid, _L2_KEEP + _L2_KEEP_UP * lw, shade_k)),
        (_lift(core, 0.62 * flame_core_lift_k(heat)),
         _soft_shade(core, _L3_KEEP + _L3_KEEP_UP * lw, shade_k)),
    )
    p.setPen(Qt.PenStyle.NoPen)
    tip_stop = _grad_tip_stop(heat)
    for (shrink, seed), (c_bottom, c_top) in zip(LAYERS, grads):
        pts = outline(cx, root_y, h, w, t, seed, shrink, samples)
        grad = QLinearGradient(QPointF(cx, root_y), QPointF(cx, g.tip_y))
        grad.setColorAt(0.00, QColor(*c_bottom))
        grad.setColorAt(tip_stop, QColor(*c_top))
        grad.setColorAt(1.00, QColor(*c_top))
        p.setBrush(QBrush(grad))
        p.drawPath(_layer_path(pts))

    if log_image is None:
        # ---- 4. 前对柴堆：横卧在火前，压在火焰图层之上 ----
        # 这一对不压暗就会"贴"在火上 —— 背光处理的理由见 log_pile。
        p.setPen(Qt.PenStyle.NoPen)
        for pts, col in log_draw_list(
                log_pile(cx, base_y, d, heat, mid, log_style, pair="front")):
            p.setBrush(QBrush(QColor(*col)))
            p.drawPath(_layer_path(pts))

        # ---- 4.5 端向柴：最前面一根，几乎正对观众、略向盘心内侧偏 ----
        # 它压在所有火焰图层之上，把"柴塔镂空、火焰那条直底边从缝里漏出来"的违和感挡掉。
        p.setPen(Qt.PenStyle.NoPen)
        for pts, col in fore_draw_list(
                log_fore(cx, base_y, d, heat, mid, log_style)):
            p.setBrush(QBrush(QColor(*col)))
            p.drawPath(_layer_path(pts))

    # ---- 4.7 前景柴堆：压在所有火焰图层之上，遮掉火焰下半段和平直底边 ----
    # 位图柴堆时它就是"前对柴 + 端向柴"的位图版；代码柴堆时没有这一层。
    if log_image_front is not None:
        _blit_log_image(p, log_image_front, cx, cy, d)

    # ---- 5. 火星 ----
    # 高度取两层里高的那个 —— 低热时底火层比主火高，火星该从**看得见的**火焰
    # 顶端冒出去，否则会从主火尖端"凭空"出现（那点已经在底火层内部了）。
    #
    # spark_field 的三种取值别混：
    #   SparkField 实例 → 用它
    #   None            → 没指定，新建一个默认的（"照常放火星"）
    #   False           → 这一帧**不放**火星（暂停/余烬态）。早先调用方传 None
    #                     来表达"不放"，结果这里给它新建了一个默认 field ——
    #                     开关形同虚设（见 _smooth_probe.py 的量测）。
    h_spark = max(h, fg.span if fg is not None else 0.0)
    sparks = ([] if spark_field is False else
              (spark_field if spark_field is not None else SparkField())
              .at(t, heat, cx, root_y, h_spark))
    for sx, sy, sr, sa in sparks:
        if sa <= 0.02:
            continue
        p.setBrush(QColor(core[0], core[1], core[2], int(255 * sa)))
        p.drawEllipse(QPointF(sx, sy), sr, sr)

    return h
