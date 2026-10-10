"""配置读取回归测试。

起因是一个真 bug：config.json 里用 "*size" / "*bg_alpha" 标记常用项（JSON 没有
注释，就用 * 前缀当"这条该改"的视觉标记），而代码读的是 cfg.get("size", 176)，
于是配置写了 190 却永远拿到默认值 176 —— 用户改了配置毫无反应，也不报错。

这组测试保证：带星 / 不带星两种写法都能读到，且真实 config.json 里的值真的
进得去 HeatEngine / overlay。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from heatcore import (  # noqa: E402
    HeatEngine,
    HeatService,
    MouseCollector,
    cfg_get,
    cfg_set,
    load_config,
)

OK = 0
BAD = 0


def check(name, got, want):
    global OK, BAD
    if got == want:
        OK += 1
        print("  [PASS] %-44s %s" % (name, got))
    else:
        BAD += 1
        print("  [FAIL] %-44s got=%r want=%r" % (name, got, want))


def main():
    print("== cfg_get / cfg_set 基本行为 ==")
    check("普通键", cfg_get({"a": 1}, "a", 9), 1)
    check("带星键", cfg_get({"*a": 2}, "a", 9), 2)
    check("都没有 → 默认值", cfg_get({}, "a", 9), 9)
    check("两个都在 → 普通键优先", cfg_get({"a": 1, "*a": 2}, "a", 9), 1)

    d = {"*a": 2}
    cfg_set(d, "a", 5)
    check("cfg_set 同步带星别名", d, {"*a": 5, "a": 5})
    d2 = {"a": 1}
    cfg_set(d2, "a", 7)
    check("cfg_set 不凭空造带星键", d2, {"a": 7})

    print("\n== 真实 config.json 的值真的进得来 ==")
    cfg = load_config()
    overlay = cfg["overlay"]
    heat = cfg["heat"]
    mouse = cfg["mouse"]

    # 判据是"配置里写了什么就读到什么"，不是"必须不等于代码默认值" —— 前者才是
    # 这组测试真正要防的回归（配置写了但读不到）。后者会在用户把值调回默认值时
    # 误报，而且 config.json 里 bg_alpha 本来就可能恰好等于默认值。
    # 带星/不带星两种写法都要认：程序运行时 cfg_set 会同时写 "k" 和 "*k"，
    # 所以两个键并存是正常状态（见上面「cfg_set 同步带星别名」那条）。
    def written(key, fallback):
        if key in overlay:
            return overlay[key]
        return overlay.get("*" + key, fallback)

    real_size = cfg_get(overlay, "size", 176)
    real_alpha = cfg_get(overlay, "bg_alpha", 0.72)
    print("  （config.json 里写的是 size=%s / bg_alpha=%s）"
          % (overlay.get("*size"), overlay.get("*bg_alpha")))
    check("overlay.size 读到的就是配置里的值", real_size, written("size", 176))
    check("overlay.bg_alpha 读到的就是配置里的值",
          real_alpha, written("bg_alpha", 0.72))

    eng = HeatEngine(heat)
    check("HeatEngine.full_kpm", eng.full_kpm, float(cfg_get(heat, "full_kpm", 300)))
    check("HeatEngine.alpha", eng.alpha, float(cfg_get(heat, "ema_alpha", 0.2)))
    check("HeatEngine.w_click", eng.w_click, float(cfg_get(heat, "w_click", 4)))
    check("HeatEngine.w_move", eng.w_move, float(cfg_get(heat, "w_move", 0.01)))
    check("HeatEngine.w_scroll", eng.w_scroll, float(cfg_get(heat, "w_scroll", 2)))

    mc = MouseCollector(None, None, heat, mouse)
    check("MouseCollector.enabled", mc._enabled, bool(cfg_get(mouse, "enabled", True)))
    check("MouseCollector.pump 间隔", mc._pump_interval,
          float(cfg_get(mouse, "pump_interval_seconds", 2.0)))

    print("\n== HeatService 用的是 config 里的库路径 ==")
    tmp = Path(tempfile.mkdtemp(prefix="heat-cfg-"))
    staged = json.loads(json.dumps(cfg))          # 深拷贝
    staged["storage"]["db_path"] = str(tmp / "t.db")
    staged["storage"]["flush_interval_seconds"] = 3
    cfg_file = tmp / "config.json"
    cfg_file.write_text(json.dumps(staged, ensure_ascii=False), encoding="utf-8")

    svc = HeatService(str(cfg_file))
    check("db_path 来自配置", svc.db_path.name, "t.db")
    check("flush 间隔来自配置", svc.aggregator.flush_interval, 3.0)
    check("库文件已建好", svc.db_path.exists(), True)
    check("热配置已传给引擎", svc.engine.w_click, float(cfg_get(heat, "w_click", 4)))
    check("鼠标采集器已接线", isinstance(svc.mouse, MouseCollector), True)

    print("\n结果：%s（%d 通过 / %d 失败）" % ("全部通过" if not BAD else "有失败", OK, BAD))
    return 1 if BAD else 0


if __name__ == "__main__":
    raise SystemExit(main())
