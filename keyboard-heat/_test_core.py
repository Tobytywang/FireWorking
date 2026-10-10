"""heatcore 自检。重点验证两件事：

1. 增量刷盘不会重复累加 —— 同一个分钟桶被反复 flush，库里必须只等于真实计数。
   这是整套存储里最容易出错的地方（写成累计值 UPSERT 就会成倍膨胀）。
2. 热度算法的收敛与冷却行为符合预期。
"""

import sqlite3
import time

from heatcore import HeatEngine, MinuteAggregator

out = []
ok = True


def check(name, cond, detail=""):
    global ok
    ok = ok and bool(cond)
    out.append(("  [PASS] " if cond else "  [FAIL] ") + name + (("  " + str(detail)) if detail else ""))


# ---------------- 1. 增量刷盘 ----------------
out.append("== MinuteAggregator 增量刷盘 ==")
db = r"D:\Workspace\HardWorking\keyboard-heat\data\_test.db"
_clean = sqlite3.connect(db)
_clean.execute("DROP TABLE IF EXISTS minutes")     # 用 SQL 清空，不删文件
_clean.commit()
_clean.close()

agg = MinuteAggregator(db, flush_interval=999)

for _ in range(100):
    agg.record("keystroke")
for _ in range(10):
    agg.record("backspace")
for _ in range(7):
    agg.record("modifier")

agg.flush()
agg.flush()
agg.flush()          # 重复刷盘不能重复累加

conn = sqlite3.connect(db)
row = conn.execute("SELECT SUM(keystrokes), SUM(backspaces), SUM(modifiers) FROM minutes").fetchone()
check("flush x3 后击键数 = 100", row[0] == 100, row)
check("flush x3 后退格数 = 10", row[1] == 10, row)
check("flush x3 后修饰键数 = 7", row[2] == 7, row)

for _ in range(50):
    agg.record("keystroke")
agg.flush()
row = conn.execute("SELECT SUM(keystrokes) FROM minutes").fetchone()
check("追加 50 次再 flush 后 = 150", row[0] == 150, row)

agg.flush()
row = conn.execute("SELECT SUM(keystrokes) FROM minutes").fetchone()
check("空 flush 不改变数值", row[0] == 150, row)
conn.close()

# ---------------- 2. 热度算法 ----------------
out.append("== HeatEngine 热度曲线 ==")

clock = [1000.0]
time.monotonic = lambda: clock[0]          # 换掉时钟，不用真等 60 秒

cfg = {
    "window_seconds": 60,
    "ema_alpha": 0.2,
    "full_kpm": 300,
    "idle_after_seconds": 30,
    "decay_per_second": 0.9,
}
eng = HeatEngine(cfg)

s = eng.sample()
check("初始热度 = 0", s["heat"] == 0.0, s)

# 60 秒窗口内注入 300 次击键 = 正好 300 KPM = 满热
for _ in range(300):
    eng.record()
clock[0] += 0.25
s = eng.sample()
check("满热输入下 KPM = 300", s["kpm"] == 300, s["kpm"])
check("首次采样热度仍较低（EMA 未收敛）", s["heat"] < 40, s["heat"])
check("状态 = typing", s["state"] == "typing", s["state"])

for _ in range(60):                        # 15 秒
    clock[0] += 0.25
    s = eng.sample()
check("15 秒后热度收敛到 90 以上", s["heat"] > 90, s["heat"])

# 停手 40 秒：进入 pause 区间（30s < idle < 120s）
clock[0] += 40
s = eng.sample()
check("停手 40 秒状态 = pause", s["state"] == "pause", s["state"])
check("停手后热度开始回落", s["heat"] < 96.7, s["heat"])

for _ in range(40):                        # 再 10 秒
    clock[0] += 0.25
    s = eng.sample()
check("衰减 10 秒后热度降到 60 以下", s["heat"] < 60, s["heat"])
check("冷却不会降到负数", s["heat"] >= 0, s["heat"])

clock[0] += 100                            # 累计停手 150 秒
s = eng.sample()
check("停手超过 2 分钟状态 = idle", s["state"] == "idle", s["state"])

for _ in range(80):                        # 再 20 秒
    clock[0] += 0.25
    s = eng.sample()
check("持续冷却后热度接近 0", s["heat"] < 5, s["heat"])

# 窗口滑出后 KPM 归零，热度最终**精确**归零（火要能完整回到空闲形态）。
# 循环长度按 _HEAT_FLOOR=0.05 校准：衰减是乘性的，heat 从 2.7 掉到 0.05 以下
# 需要 ~60 秒（0.9^60 ≈ 0.002）。下限越大这一步来得越快，但同样会让"从 0 起步"
# 出现台阶 —— 见 heatcore._HEAT_FLOOR 的推导。
for _ in range(240):                       # 再 60 秒
    clock[0] += 0.25
    s = eng.sample()
check("事件滑出 60 秒窗口后 KPM = 0", s["kpm"] == 0, s["kpm"])
check("长时间空闲热度归零", s["heat"] == 0.0, s["heat"])
check("峰值被记住", s["peak"] > 90, s["peak"])

# 慢速打字也必须让火起来。曾经有个**死区**：热度下限 `if heat < 0.5: heat = 0`
# 写在上升支上，而 EMA 每步都从 0 重来 —— 每步增量 target*weight 一次到不了 0.5
# 就永远卡在 0。篝火模式 80ms 刷新 → 阈值 ≈85 kpm：低于它的打字强度下热度恒为 0，
# 火焰对输入**完全没有反应**；一过阈值又"啪"地跳到 0.5 再开始长，看起来像突变。
# 这里用 80 kpm + 80ms 采样复现那个场景（旧代码此断言必失败）。
eng_slow = HeatEngine(cfg)
_prev = 0.0
_max_step = 0.0
s_slow = None
_step = 0.08
_acc = 0.0
for _ in range(int(180 / _step)):
    _acc += 80 / 60.0 * _step
    _n = int(_acc)
    _acc -= _n
    for _ in range(_n):
        eng_slow.record()
    clock[0] += _step
    s_slow = eng_slow.sample()
    _max_step = max(_max_step, s_slow["heat"] - _prev)
    _prev = s_slow["heat"]
check("80 kpm 慢速打字热度能起来（无死区）", s_slow["heat"] > 3.0, s_slow["heat"])
check("80 kpm 的热度落在 kpm/full_kpm 那一档（≈27）", 8 < s_slow["heat"] < 40,
      s_slow["heat"])
check("热度爬升没有单帧大跳（≤1.0）", _max_step <= 1.0, "单帧最大 %.2f" % _max_step)
check("热度量化到 0.01（冷端对热度极敏感，0.1 会有尺寸台阶）",
      abs(round(s_slow["heat"], 2) - s_slow["heat"]) < 1e-9, s_slow["heat"])

# 修饰键去重逻辑（KeyboardCollector 的分类表）
from heatcore import KeyboardCollector
check("退格被识别为擦除键", "backspace" in KeyboardCollector._ERASE)
check("Ctrl 被识别为修饰键", "ctrl_l" in KeyboardCollector._MODIFIER_NAMES and "ctrl" in KeyboardCollector._MODIFIER_NAMES)

out.append("")
out.append("结果：%s" % ("全部通过" if ok else "存在失败项"))

with open(r"D:\Workspace\HardWorking\keyboard-heat\_test.log", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
