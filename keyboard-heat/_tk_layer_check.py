"""Tk 版的层叠顺序断言 —— 抓屏不可靠时，用结构把它钉死。

Tk 的层叠顺序就是**创建顺序**，没有 z-index 可查（Qt 那边靠绘制调用顺序，Tk 这边
全靠 create_* 的先后）。这种"看不见的约定"极容易在改动中被破坏 —— 之前就出过
"位图柴堆建在火焰之后，两版的柴/火层次正好相反"的事故。

所以这里不截图，直接问 canvas：这几个画素项的前后关系对不对。

    .pyenv\\Scripts\\python.exe _tk_layer_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from heatcore import load_config  # noqa: E402

OK = 0
BAD = 0


def ok(name, cond, detail=""):
    global OK, BAD
    if cond:
        OK += 1
        print("  [PASS] %s  %s" % (name, detail))
    else:
        BAD += 1
        print("  [FAIL] %s  %s" % (name, detail))


def _rgb(spec):
    """Tk 的填充色可能是 '#rrggbb' 也可能带名字，这里只认前者。"""
    s = spec.strip()
    if s.startswith("#") and len(s) == 7:
        return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))
    if s.startswith("#") and len(s) == 13:      # Tk 偶尔给 4 位/通道
        return (int(s[1:3], 16), int(s[5:7], 16), int(s[9:11], 16))
    return (-1, -1, -1)


class FakeService:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"
        self.snap = {"heat": 50.0, "kpm": 150, "kpm_keys": 150, "kpm_mouse": 0,
                     "peak": 214.0, "state": "typing", "idle_seconds": 1.0,
                     "total_keys": 100}

    def snapshot(self):
        return dict(self.snap)

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def main():
    from overlay_tk import HeatDialTk

    dlg = HeatDialTk(FakeService())
    try:
        dlg._render()
        c = dlg.canvas
        allitems = list(c.find_all())

        def idx(item):
            return allitems.index(item) if item in allitems else -1

        print("Tk 画素项层叠顺序（数字越小越靠下）")
        order = [("后景柴堆 i_log_img", dlg.i_log_img),
                 ("底火层 i_floor", dlg.i_floor),
                 ("主火第 1 层", dlg.i_flames[0]),
                 ("主火第 3 层", dlg.i_flames[-1]),
                 ("前景柴堆 i_log_front", dlg.i_log_front),
                 ("火星第 1 颗", dlg.i_sparks[0])]
        for name, item in order:
            print("   %-18s idx=%d" % (name, idx(item)))

        ok("后景柴堆在底火层之下", idx(dlg.i_log_img) < idx(dlg.i_floor))
        ok("底火层在主火之下", idx(dlg.i_floor) < idx(dlg.i_flames[0]))
        ok("主火三层自下而上仍是 LAYERS 顺序",
           idx(dlg.i_flames[0]) < idx(dlg.i_flames[-1]))
        ok("前景柴堆压在主火之上（盖掉火焰下半段）",
           idx(dlg.i_flames[-1]) < idx(dlg.i_log_front))
        ok("前景柴堆在火星之下", idx(dlg.i_log_front) < idx(dlg.i_sparks[0]))

        # ---- 环外沿描边（用户要求把边沿的设计套到进度条边框上，见 overlay.py
        # THEMES.track_edge）。Tk 没有 z-index，全靠创建顺序：它必须先于 i_track，
        # 后建的轨道才会盖住它的内半边；半径还必须比轨道大，否则线条落在环带里，
        # 会变成"轨道上多一条线"而不是"外沿描边"。
        bx_e = c.coords(dlg.i_edge)
        bx_t = c.coords(dlg.i_track)
        ok("环外沿描边建在轨道之前（后建的轨道压在上面）",
           idx(dlg.i_edge) < idx(dlg.i_track),
           "edge=%d track=%d" % (idx(dlg.i_edge), idx(dlg.i_track)))
        ok("环外沿描边建在底盘之后（不被底盘盖住）",
           idx(dlg.i_plate) < idx(dlg.i_edge))
        ok("环外沿描边的半径比轨道大（真的在外沿，没落在环带里）",
           (bx_e[2] - bx_e[0]) > (bx_t[2] - bx_t[0]),
           "描边直径 %.1f > 轨道直径 %.1f" % (bx_e[2] - bx_e[0], bx_t[2] - bx_t[0]))
        ok("环外沿描边宽 ≥ 2px",
           float(c.itemcget(dlg.i_edge, "width")) >= 2.0,
           c.itemcget(dlg.i_edge, "width"))
        eq_rgb = _rgb(c.itemcget(dlg.i_edge, "outline"))
        # Tk 的 canvas item 没有逐元素 alpha，`_edge_colors` 把线色按
        # keep = flame.track_edge_alpha(cfg 的底盘不透明度) 混向身下的颜色来等价模拟。
        # 这里用**独立算一遍**的期望值去对（不直接调 `dlg._edge_colors()`，否则是同义反复）。
        import flame as _flame
        from overlay_tk import CAMP_PIT_RGB

        keep = _flame.track_edge_alpha(dlg.cfg_alpha)
        plate_t = _rgb(dlg.theme["plate"])
        edge_t = _rgb(dlg.theme["track_edge"])

        def mirror(a, b, k):
            """overlay_tk._mixc 的独立副本：k=0 → a，k=1 → b。"""
            return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))

        want_out = mirror(plate_t, edge_t, keep)
        ok("环外沿描边的颜色 = 线色按 %.2f 混向底盘色（反相透明度）" % keep,
           eq_rgb == want_out and eq_rgb != (-1, -1, -1),
           "%s vs %s（cfg_alpha=%.2f）" % (eq_rgb, want_out, dlg.cfg_alpha))
        under_in = CAMP_PIT_RGB if dlg._campfire else plate_t
        want_in = mirror(under_in, edge_t, keep)
        eq_in = _rgb(c.itemcget(dlg.i_edge_in, "outline"))
        ok("环内沿描边的颜色 = 线色混向它身下的色（灶膛/底盘）",
           eq_in == want_in, "%s vs %s" % (eq_in, want_in))
        # 两个端点必须逐位落在用户指定的位置上（`_sync_edge_colors` 是真在用的那条路径）
        saved = dlg.cfg_alpha
        try:
            dlg.cfg_alpha = 0.0
            dlg._sync_edge_colors()
            ok("底盘全透明（α=0）→ 线画满 = 主题的 track_edge",
               _rgb(c.itemcget(dlg.i_edge, "outline")) == edge_t,
               c.itemcget(dlg.i_edge, "outline"))
            dlg.cfg_alpha = 1.0
            dlg._sync_edge_colors()
            ok("底盘全不透明（α=1）→ 线消失 = 底盘色（等效不可见）",
               _rgb(c.itemcget(dlg.i_edge, "outline")) == plate_t,
               c.itemcget(dlg.i_edge, "outline"))
        finally:
            dlg.cfg_alpha = saved
            dlg._sync_edge_colors()
        ok("还原后线的颜色回到配置档",
           _rgb(c.itemcget(dlg.i_edge, "outline")) == want_out)

        # ---- 整圈轮廓（用户第 6 轮报"只有外圈有，内圈和转角也应该有"）。
        # 内弧和两个端头半圆同样必须先于 i_track 创建；灶膛（i_pit）还要更早 ——
        # 它和轮廓内弧只差 1.5px，晚建就会把内弧切掉半条
        # （实测可见宽度 2.1px → 1.5px，一个纯色像素都挤不出来）。
        bx_i = c.coords(dlg.i_edge_in)
        ok("环内沿描边建在轨道之前（后建的轨道压在上面）",
           idx(dlg.i_edge_in) < idx(dlg.i_track),
           "in=%d track=%d" % (idx(dlg.i_edge_in), idx(dlg.i_track)))
        ok("环内沿描边的半径比轨道小（真的在内沿，没落在环带里）",
           (bx_i[2] - bx_i[0]) < (bx_t[2] - bx_t[0]),
           "内弧直径 %.1f < 轨道直径 %.1f" % (bx_i[2] - bx_i[0], bx_t[2] - bx_t[0]))
        ok("灶膛（i_pit）建在环内沿描边之前（否则会切掉内弧半条）",
           idx(dlg.i_pit) < idx(dlg.i_edge_in),
           "pit=%d in=%d" % (idx(dlg.i_pit), idx(dlg.i_edge_in)))
        ok("端头半圆是两个（起点 220° + 末端 −40°）",
           len(dlg.i_edge_caps) == 2, len(dlg.i_edge_caps))
        ok("两个端头半圆都建在轨道之前",
           all(idx(it) < idx(dlg.i_track) for it in dlg.i_edge_caps),
           "caps=%s track=%d" % ([idx(it) for it in dlg.i_edge_caps],
                                 idx(dlg.i_track)))
        cap_w = [float(c.itemcget(it, "width")) for it in dlg.i_edge_caps]
        ok("端头半圆的线宽和其余轮廓一致",
           all(abs(x - float(c.itemcget(dlg.i_edge, "width"))) <= 1.0
               for x in cap_w), cap_w)

        # 贴图槽位生效时，代码画的柴塔必须整组藏起来（否则会和贴图叠在一起）
        c.itemconfig(dlg.i_log_front, state="normal")
        dlg._render()
        hidden_front = all(c.itemcget(it, "state") == "hidden"
                           for it in dlg.i_front_logs + dlg.i_fore_logs)
        ok("有前景贴图时，代码画的前对/端向柴整组隐藏", hidden_front)
        if dlg._log_photo is not None:
            hidden_back = all(c.itemcget(it, "state") == "hidden"
                              for it in dlg.i_logs + dlg.i_mid_logs)
            ok("有后景贴图时，代码画的后对/中对柴整组隐藏", hidden_back)

        # ---- 焰芯配色也要盯住：Tk 那条路径是**另一份**配色代码（实色混白），
        # Qt 修完不会自动跟过来。冷态焰芯曾经是灰白的，锚点抬到炭化点后完全暴露。
        #
        # ⚠ 这一段必须在**篝火模式**下量：数字仪表盘模式下火根本不画，`i_flames`
        # 的 fill 还是建时的空值，`itemcget` 会回一个 "SystemButtonText"、解析成
        # (-1,-1,-1)，四条断言全红 —— 那是**配置**的问题，不是配色的问题。
        # 用户随时可能用热键切到数字模式并存进 config.json，所以这里显式切进篝火、
        # 量完还原：断言不许依赖用户当前的配置。
        print("\n焰芯（第 3 层）实色填充随热度")
        saved_camp = dlg._campfire
        dlg._campfire = True
        dlg._show_camp(True)
        try:
            fills = {}
            for heat in (0.0, 0.25, 1.0):
                dlg._boot_done = True             # 跳过开屏扫环
                dlg.snap = dict(dlg.snap)
                dlg.snap["heat"] = heat * 100.0
                dlg.snap["state"] = "typing" if heat > 0 else "idle"
                dlg._render()
                fills[heat] = c.itemcget(dlg.i_flames[-1], "fill")
                print("   heat %3.0f%%  %s" % (heat * 100, fills[heat]))
        finally:
            dlg._campfire = saved_camp
            dlg._show_camp(saved_camp)
        cold = _rgb(fills[0.0])
        hot = _rgb(fills[1.0])
        ok("冷态焰芯偏红（不发灰）", cold[0] - cold[2] >= 30, str(cold))
        # 本轮 Qt 侧的"白"调暖了（见 flame._CORE_TINT），Tk 这条路径随之跟过来 ——
        # 它原来往**纯白** (255,255,255) 混，跟 Qt 那个中性白犯同一个毛病：
        # 混出来 R−G 被稀释，在饱和橙黄中间被读成"灰/绿"。
        # 旧判据 `min(hot) > 170` 盯的是某个通道的绝对值 —— 调暖必然压低 B，
        # 它是"每轮都要改"的负资产。换成两条性质：
        #   ① 提白确实生效：B 通道被抬起来（R/G 早就贴着 255 封顶，只有 B 有余量）
        #   ② 焰芯是**暖**白：R−G 抬上去，不再是一块中性灰
        import flame
        _core_raw = flame.flame_colors(1.0)[2]
        ok("满热焰芯提白生效（B 被抬起来，不是被压暗）",
           hot[2] > _core_raw[2],
           "B %d > 焰芯底色 %d" % (hot[2], _core_raw[2]))
        ok("满热焰芯是暖白（R−G 抬上去，抗「灰/绿」）",
           hot[0] - hot[1] >= 15, "R−G %d" % (hot[0] - hot[1]))
        ok("焰芯随热度变亮", sum(hot) > sum(cold))

        print("\n结果：%s（%d 通过 / %d 失败）"
              % ("全部通过" if BAD == 0 else "有失败", OK, BAD))
    finally:
        try:
            dlg.root.destroy()
        except Exception:
            pass
    return 1 if BAD else 0


if __name__ == "__main__":
    raise SystemExit(main())
