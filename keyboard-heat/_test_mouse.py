"""鼠标链路测试：折算权重、pointing 状态、新列落库、老库迁移、pump 批量搬运。

时间同样用 patch time.monotonic 的方式推进（和 _test_core.py 一致），
否则要真等 60 秒才能验证窗口行为。
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from heatcore import (  # noqa: E402
    FIELDS,
    HeatEngine,
    MinuteAggregator,
    MouseCollector,
    ensure_schema,
)

DATA = HERE / "data"
DATA.mkdir(parents=True, exist_ok=True)

out: list[str] = []
ok = True


def check(name, cond, detail=""):
    global ok
    ok = ok and bool(cond)
    out.append("  [%s] %-34s %s" % ("PASS" if cond else "FAIL", name, detail))


def fresh_engine(**over):
    cfg = {
        "window_seconds": 60,
        "full_kpm": 300,
        "ema_alpha": 1.0,          # 直接跳到目标值，方便断言
        "idle_after_seconds": 30,
        "decay_per_second": 0.9,
        "w_move": 0.01,
        "w_click": 4.0,
        "w_scroll": 2.0,
    }
    cfg.update(over)
    return HeatEngine(cfg)


clock = [1000.0]
time.monotonic = lambda: clock[0]        # 换掉时钟，不用真等


class FakeButton:
    def __init__(self, name):
        self.name = name


# ---------------- 1. 折算权重 ----------------
out.append("== 折算权重 ==")

eng = fresh_engine()
eng.record(weight=1000 * 0.01, is_key=False)      # 1000 次移动 = 10 等效
clock[0] += 0.01
s = eng.sample()
check("1000 次移动 → 10 等效 KPM", s["kpm"] == 10, s["kpm"])
check("键盘部分为 0", s["kpm_keys"] == 0, s["kpm_keys"])
check("鼠标部分 = 10", s["kpm_mouse"] == 10, s["kpm_mouse"])

eng2 = fresh_engine()
eng2.record(weight=25 * 4.0, is_key=False)        # 25 次点击 = 100 等效
clock[0] += 0.01
s = eng2.sample()
check("25 次点击 → 100 等效 KPM", s["kpm"] == 100, s["kpm"])

eng3 = fresh_engine()
for _ in range(60):
    eng3.record()                                 # 60 击键
eng3.record(weight=4000 * 0.01, is_key=False)     # 40 等效鼠标
clock[0] += 0.01
s = eng3.sample()
check("混合总计 = 100", s["kpm"] == 100, s["kpm"])
check("其中键盘 = 60", s["kpm_keys"] == 60, s["kpm_keys"])
check("其中鼠标 = 40", s["kpm_mouse"] == 40, s["kpm_mouse"])

eng4 = fresh_engine()
eng4.record(weight=5 * 2.0, is_key=False)         # 5 格滚轮 = 10 等效
clock[0] += 0.01
check("5 格滚轮 → 10 等效 KPM", eng4.sample()["kpm"] == 10)

# ---------------- 2. 状态机 ----------------
out.append("== 状态机（含鼠标）==")

eng5 = fresh_engine()
eng5.record(weight=5.0, is_key=False)             # 只有鼠标
clock[0] += 0.5
s = eng5.sample()
check("只有鼠标活动 → pointing", s["state"] == "pointing", s["state"])

eng6 = fresh_engine()
eng6.record()                                     # 键盘
eng6.record(weight=1.0, is_key=False)             # 鼠标
clock[0] += 0.5
s = eng6.sample()
check("键鼠都有 → typing", s["state"] == "typing", s["state"])

eng7 = fresh_engine()
for _ in range(100):
    eng7.record()
clock[0] += 35                                    # 超过 idle_after=30
s = eng7.sample()
check("停 35 秒 → pause", s["state"] == "pause", s["state"])

eng7.record(weight=1.0, is_key=False)             # 只动一下鼠标
clock[0] += 0.5
s = eng7.sample()
check("鼠标活动把状态从 pause 拉回 pointing", s["state"] == "pointing", s["state"])

eng8 = fresh_engine()
eng8.record(weight=1.0, is_key=False)
clock[0] += 200                                   # 远超 idle_after*4
check("长时间无活动 → idle", eng8.sample()["state"] == "idle")

# ---------------- 3. 落库 ----------------
out.append("== 新列落库 ==")

db = str(DATA / "_mouse_test.db")
c = sqlite3.connect(db)
c.execute("DROP TABLE IF EXISTS minutes")         # 用 SQL 清空，不删文件
c.commit()
c.close()

agg = MinuteAggregator(db, flush_interval=999)
agg.record("keystroke", 3)
agg.record("mouse_move", 500)
agg.record("click", 12)
agg.record("scroll", 7)
agg.flush()
agg.flush()                                       # 重复刷盘不得翻倍
row = sqlite3.connect(db).execute(
    "SELECT SUM(keystrokes), SUM(mouse_moves), SUM(clicks), SUM(scrolls), COUNT(*) "
    "FROM minutes"
).fetchone()
check("鼠标三列落库且不重复累加", row[:4] == (3, 500, 12, 7), row)
check("合并到同一个分钟桶", row[4] == 1, row[4])

agg.record("mouse_move", 100)
agg.flush()
row = sqlite3.connect(db).execute("SELECT SUM(mouse_moves) FROM minutes").fetchone()
check("增量追加 = 600", row[0] == 600, row[0])

# ---------------- 4. 老库迁移 ----------------
out.append("== 老库（5 列）迁移 ==")

db2 = str(DATA / "_legacy_test.db")
c = sqlite3.connect(db2)
c.execute("DROP TABLE IF EXISTS minutes")
c.execute(
    "CREATE TABLE minutes ("
    "  minute_ts INTEGER PRIMARY KEY,"
    "  keystrokes INTEGER NOT NULL DEFAULT 0,"
    "  backspaces INTEGER NOT NULL DEFAULT 0,"
    "  modifiers  INTEGER NOT NULL DEFAULT 0,"
    "  active_secs INTEGER NOT NULL DEFAULT 0)"
)
c.execute("INSERT INTO minutes VALUES (1000000, 42, 3, 2, 30)")
c.commit()

ensure_schema(c)
cols = [r[1] for r in c.execute("PRAGMA table_info(minutes)")]
check("补出 3 个鼠标列", all(x in cols for x in ("mouse_moves", "clicks", "scrolls")), cols)
kept = c.execute(
    "SELECT keystrokes, backspaces, active_secs, mouse_moves FROM minutes "
    "WHERE minute_ts = 1000000"
).fetchone()
check("历史数据保留、新列默认 0", kept == (42, 3, 30, 0), kept)

ensure_schema(c)                                  # 幂等
cols2 = [r[1] for r in c.execute("PRAGMA table_info(minutes)")]
check("重复 ensure_schema 幂等", cols2 == cols, len(cols2))
c.close()

check("FIELDS 与 schema 列数一致", len(FIELDS) == 7, len(FIELDS))

# ---------------- 5. MouseCollector ----------------
out.append("== MouseCollector ==")

cfg = {"w_move": 0.01, "w_click": 4.0, "w_scroll": 2.0}

# 关掉时不挂钩子
mc_off = MouseCollector(agg, fresh_engine(), cfg, {"enabled": False})
mc_off.start()
check("enabled=false 不创建 listener", mc_off._listener is None)
mc_off.stop()

# 直接喂回调，不走真实钩子（钩子由 _test_e2e 覆盖）
eng9 = fresh_engine()
mc = MouseCollector(agg, eng9, cfg, {"enabled": False})
for _ in range(1000):
    mc._on_move(0, 0)
for _ in range(10):
    mc._on_click(0, 0, FakeButton("left"), True)
mc._on_click(0, 0, FakeButton("left"), False)     # 抬起不该计数
for _ in range(3):
    mc._on_click(0, 0, FakeButton("right"), True)
for _ in range(5):
    mc._on_scroll(0, 0, 0, -1)

mv, ck, sc = mc._pump_once()
check("pump 取走 1000 移动", mv == 1000, mv)
check("pump 取走 13 次点击（抬起不计）", ck == 13, ck)
check("pump 取走 5 格滚动", sc == 5, sc)
check("左键 10 / 右键 3", mc.clicks_by_button.get("left") == 10
      and mc.clicks_by_button.get("right") == 3, mc.clicks_by_button)

clock[0] += 0.01
s = eng9.sample()
# 1000*0.01 + 13*4 + 5*2 = 10 + 52 + 10 = 72
check("折算后等效 KPM = 72", s["kpm"] == 72, s["kpm"])
check("折算不进入键盘桶", s["kpm_keys"] == 0, s["kpm_keys"])

mv2, ck2, sc2 = mc._pump_once()
check("取走后再取为空（不重复计数）", (mv2, ck2, sc2) == (0, 0, 0), (mv2, ck2, sc2))

out.append("")
out.append("结果：%s" % ("全部通过" if ok else "存在失败项"))
text = "\n".join(out)
print(text)
(HERE / "_mouse_test.log").write_text(text, encoding="utf-8")
raise SystemExit(0 if ok else 1)
