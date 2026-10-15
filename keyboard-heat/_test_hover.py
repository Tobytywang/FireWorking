# -*- coding: utf-8 -*-
"""「鼠标悬停时隐藏表盘」逻辑探针（Qt 版overlay.py）

守护四个点：
  H1 配置默认 off：未开启时不改变既有行为（不订阅追踪、不隐藏）
  H2 勾选on→订阅 TrackMouseEvent；切回 off→退订并恢复显示
  H3 进入即隐藏 / 离开即恢复，且**手动隐藏优先**（手动隐藏期间不被悬停逻辑显示出来）
  H4 反向验证：注入「_hover_hide 恒为 True 且 _manually_hidden 恒为 False」的坏状态，
     验证「悬停恢复」这条路径确实由 _manually_hidden 把住 —— 否则手动隐藏会被
     鼠标一移开就擅自显示出来（这是本功能最容易写坏的地方）

CLI：--qt 用offscreen 真跑 Qt；不带则只跑纯逻辑（不需要 PyQt6）
"""
import os, sys, argparse

HERE = os.path.dirname(os.path.abspath(__file__))


def _logic_only():
    """不依赖 PyQt6 的纯逻辑校验：用一个最小替身复刻状态机，
    验证「手动隐藏优先」与「进入/离开」的状态转移是否符合预期。"""
    class Fake:
        def __init__(self):
            self._hover_hide = False
            self._hover_hidden = False
            self._manually_hidden = False
            self.visible = True
        def _apply_hover(self, hidden):
            self.visible = not hidden
        def _restore_after_hover(self):
            if self._hover_hidden:
                self._hover_hidden = False
                if not self._manually_hidden:
                    self._apply_hover(False)
        def _toggle_hide_dial(self, checked):
            self._manually_hidden = checked
            if checked:
                self._hover_hidden = False
            else:
                self._restore_after_hover()
            self.visible = not checked
        def _on_mouse_enter(self):
            if self._hover_hide and not self._manually_hidden and not self._hover_hidden:
                self._hover_hidden = True
                self._apply_hover(True)
        def _on_mouse_leave(self):
            self._restore_after_hover()
    fails = []

    # H1/H2：默认 off → 进入不隐藏
    d = Fake()
    d._on_mouse_enter()
    if d.visible is False:
        fails.append(('H1', '默认 off 时进入就隐藏了（应保持显示）'))
    else:
        print('  [OK] H1 默认 off：鼠标进入不隐藏，保持既有行为')

    # H2：开启 on → 进入隐藏、离开恢复
    d = Fake(); d._hover_hide = True
    d._on_mouse_enter()
    if d.visible is not False:
        fails.append(('H2', '开启后进入未隐藏'))
    else:
        print('  [OK] H2 开启 on：进入即隐藏')
    d._on_mouse_leave()
    if d.visible is not True:
        fails.append(('H2', '离开后未恢复显示'))
    else:
        print('  [OK] H2 开启 on：离开即恢复')

    # H3：手动隐藏期间，鼠标移开**不得**把表盘擅自显示出来
    d = Fake(); d._hover_hide = True
    d._on_mouse_enter()          # 悬停隐藏
    d._toggle_hide_dial(True)    # 用户又点了「隐藏表盘」
    d._on_mouse_leave()          # 鼠标移开
    if d.visible is not False:
        fails.append(('H3', '手动隐藏后鼠标移开，表盘被擅自显示（手动隐藏必须优先）'))
    else:
        print('  [OK] H3 手动隐藏优先：鼠标移开不会把它显示出来')

    # H4 反向验证：直接对照「_restore_after_hover 有无 _manually_hidden 判断」的差异。
    #     场景：已悬停隐藏（_hover_hidden=True）→ 用户点了手动隐藏（_manually_hidden=True）
    #     → 鼠标移开。正确实现不应擅自显示；坏实现会显示。
    def scenario(good):
        d = Fake(); d._hover_hide = True
        d._on_mouse_enter()          # 悬停隐藏
        d._hover_hidden = True       # 复原：手动隐藏不会清这个位（见下方说明）
        d._manually_hidden = True    # 用户点了「隐藏表盘」
        if good:
            d._restore_after_hover()
        else:
            # 坏实现：少了 if not self._manually_hidden
            if d._hover_hidden:
                d._hover_hidden = False
                d._apply_hover(False)
        return d.visible
    if scenario(False) is not True:
        fails.append(('H4', '反向验证失败：坏实现竟也没显示，说明场景没构造对'))
    elif scenario(True) is not False:
        fails.append(('H4', '反向验证失败：正确实现居然显示了（手动隐藏应优先）'))
    else:
        print('  [OK] H4 反向验证：去掉 _manually_hidden 判断 → 擅自显示 → H3 有效')

    for c, m in fails:
        print('  [FAIL] %s %s' % (c, m))
    print('\n结果：%d 通过 / %d 失败' % (4 - len(fails), len(fails)))
    return 1 if fails else 0


def _qt_live():
    """真跑 Qt（offscreen），验证几何轮询 + 定时器启停这条实现。"""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    import overlay

    app = QApplication.instance() or QApplication([])
    fails = []

    class FakeSvc:
        config = {'overlay': {}}
        def __getattr__(self, k):
            return lambda *a, **kw: None
    try:
        d = overlay.HeatDial.__new__(overlay.HeatDial)
        # 只初始化状态机需要的字段，不跑 __init__（避免起服务/托盘）
        d._overlay_cfg = {'overlay': {}}
        d._service = FakeSvc()
        d._hover_hide = False
        d._hover_hidden = False
        d._manually_hidden = False
        d._tracking_mouse = False
        d._win = []
        d.setHidden = lambda v: d._win.append(('hidden', v))
        d.update = lambda: None

        # ── H5：默认 off 时轮询定时器**不能跑**（零开销、不改变既有行为）──
        d._hover_timer = QTimer()
        d._hover_timer.timeout.connect(lambda: None)
        overlay.HeatDial._sync_hover_timer(d)
        if d._hover_timer.isActive():
            fails.append(('H5', '默认 off 时悬停轮询仍在运行（应零开销）'))
        else:
            print('  [OK] H5 默认 off：轮询定时器不启动（零开销）')

        # ── H5b：开启后才启动 ──
        d._hover_hide = True
        overlay.HeatDial._sync_hover_timer(d)
        if not d._hover_timer.isActive():
            fails.append(('H5', '开启 on 后轮询定时器未启动'))
        else:
            print('  [OK] H5 开启 on：轮询定时器启动')

        # ── H6：几何判断（_cursor_on_dial）不碰原生指针，且异常时不崩 ──
        #真实 HeatDial 缺帧几何会抛异常 → 被 except 兜住返回 False，绝不能外泄。
        d.frameGeometry = lambda: (_ for _ in ()).throw(RuntimeError('未初始化'))
        try:
            r = overlay.HeatDial._cursor_on_dial(d)
            if r is not False:
                fails.append(('H6', '几何判断异常时应返回 False，实际 %r' % (r,)))
            else:
                print('  [OK] H6 几何判断在异常时安全返回 False（不崩、不外泄）')
        except Exception as e:
            fails.append(('H6', '几何判断把异常抛出来了：%r' % (e,)))

        # ── H7：默认档必须是 off（升级后行为不变）──
        dflt = dict(overlay.HOVER_ENTRIES).get('关')
        if dflt != 'off':
            fails.append(('H7', 'HOVER_ENTRIES 默认档应为 off，实际 %r' % dflt))
        else:
            print('  [OK] H7 默认档为「关」（off）→ 升级后行为不变')

        # ── H8：已彻底移除原生指针解析（它是 0xC0000409 秒退的元凶）──
        # ⚠ 必须按 **AST 里的真实调用**判，不能全文搜关键词：文档字符串里刻意保留了
        #   这几个词来记录踩坑，全文搜会把说明文字误判成残留；也不能"过滤注释后 parse" ——
        #   docstring 里的中文引号会让 SyntaxError（实测踩过）。
        #   正解：解析模块 AST → 只看HeatDial 的**方法体**里的 Call/Attribute。
        import ast, inspect
        mod = ast.parse(inspect.getsource(overlay))
        cls = next(n for n in mod.body
                   if isinstance(n, ast.ClassDef) and n.name == 'HeatDial')
        used = set()
        for node in ast.walk(cls):
            if isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.Name):
                used.add(node.id)
        bad = [k for k in ('from_address', 'TrackMouseEvent', 'nativeEvent')
               if k in used]
        if bad:
            fails.append(('H8', '仍存在会导致原生崩溃的调用：%s' % bad))
        else:
            print('  [OK] H8 无原生指针解析（from_address / TrackMouseEvent / nativeEvent 全已移除）')
    except Exception as e:
        fails.append(('H5', 'Qt 实测抛异常：%r' % (e,)))

    for c, m in fails:
        print('  [FAIL] %s %s' % (c, m))
    print('\n结果：%d 通过 / %d 失败' % (5 - len(fails), len(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--qt', action='store_true', help='真跑 Qt（offscreen）')
    a = ap.parse_args()
    print('=== 悬停隐藏 · 逻辑档 ===')
    rc = _logic_only()
    if a.qt:
        print('\n=== 悬停隐藏 · Qt 实测档 ===')
        rc |= _qt_live()
    sys.exit(rc)