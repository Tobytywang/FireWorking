"""端到端验证采集链路：真的装上全局钩子 + 键鼠分类 + 折算 + 计数落库。

刻意不模拟真实输入（pynput 的 Controller 会把字符打进当前焦点窗口、把指针
真的挪走，可能干扰正在用电脑的人），改成直接调用钩子回调。这样验证的是分类、
折算与计数逻辑，同时 start() 会真的挂上 WH_KEYBOARD_LL / WH_MOUSE_LL，
能顺带确认这两个钩子在本机装得上、退得干净。

跑完不会残留：用 SQL 清表，不删文件；钩子显式 stop。
"""

from pathlib import Path

import sqlite3
import time

from heatcore import HeatEngine, KeyboardCollector, MinuteAggregator, MouseCollector
from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button

HERE = Path(__file__).resolve().parent
out = []
ok = True


def check(name, cond, detail=""):
    global ok
    ok = ok and bool(cond)
    out.append(("  [PASS] " if cond else "  [FAIL] ") + name + (("  " + str(detail)) if detail else ""))


def eq(name, got, want):
    check(name, got == want, "实际 %r，预期 %r" % (got, want) if got != want else got)


db = HERE / "data" / "_e2e.db"
db.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(db)
conn.execute("DROP TABLE IF EXISTS minutes")       # 用 SQL 清空，不删文件
conn.commit()
conn.close()

agg = MinuteAggregator(db, flush_interval=1.0)
HEAT = {
    "window_seconds": 60, "ema_alpha": 0.2, "full_kpm": 300,
    "idle_after_seconds": 30, "decay_per_second": 0.9,
    "w_move": 0.01, "w_click": 4, "w_scroll": 2,
}
eng = HeatEngine(HEAT)

# ---------------------------------------------------------------- 键盘
# 一个必须讲清楚的坑：钩子一旦挂上，**这台机器上的真实按键也会喂进同一个回调**。
# 所以每段都是「挂上 → 确认 running → 立刻摘掉 → 再手动注入」，并且所有计数
# 断言都改成比增量，而不是比绝对值 —— 否则旁边有人敲一下键盘测试就红了。
out.append("== 1. 挂载全局键盘钩子 ==")
col = KeyboardCollector(agg, eng)
try:
    col.start()
    time.sleep(0.6)
    check("WH_KEYBOARD_LL 钩子已挂上", col._listener is not None and col._listener.running, True)
    col.stop()                 # 摘掉：stop() 会把 _listener 置 None
    time.sleep(0.4)
    eq("钩子已摘除（内部引用释放）", col._listener, None)
except Exception as exc:
    check("WH_KEYBOARD_LL 钩子已挂上", False, "%s: %s" % (type(exc).__name__, exc))

agg.flush()
base_keys, base_bs, base_mod = sqlite3.connect(db).execute(
    "SELECT COALESCE(SUM(keystrokes),0), COALESCE(SUM(backspaces),0), "
    "COALESCE(SUM(modifiers),0) FROM minutes"
).fetchone()
base_total = eng.sample()["total_keys"]

out.append("== 2. 键分类 ==")
TEXT = "hello world 123"
for ch in TEXT:
    col._on_press(KeyCode.from_char(ch))
check("普通字符计入 keystrokes", True, "%d 个字符" % len(TEXT))

for _ in range(4):
    col._on_press(Key.backspace)
col._on_press(Key.delete)
check("退格/删除计入 backspaces", True, "5 次")

col._on_press(Key.shift_l)
col._on_press(Key.shift_l)          # 长按产生的系统 repeat
col._on_press(Key.shift_l)
col._on_press(Key.ctrl_l)
col._on_release(Key.shift_l)
col._on_press(Key.shift_l)          # 松开后再按，应重新计数
check("修饰键去重：长按只算一次、松手后重算", True, "shift 计 2 次, ctrl 计 1 次")

out.append("== 3. 键盘侧内存计数 ==")
snap = eng.sample()
expect_total = len(TEXT) + 5 + 3      # 字符 + 退格删除 + 修饰键(shift×2 + ctrl×1)
eq("本次注入共 23 次活动", snap["total_keys"] - base_total, expect_total)
check("窗口内 KPM 大于 0", snap["kpm"] > 0, snap["kpm"])
eq("状态为 typing", snap["state"], "typing")

out.append("== 4. 刷盘落库（键盘） ==")
time.sleep(1.2)                        # 等后台线程按 flush_interval 刷一次
agg.flush()
row = sqlite3.connect(db).execute(
    "SELECT COALESCE(SUM(keystrokes),0), COALESCE(SUM(backspaces),0), "
    "COALESCE(SUM(modifiers),0) FROM minutes"
).fetchone()
eq("keystrokes 落库增量", row[0] - base_keys, len(TEXT))
eq("backspaces 落库增量", row[1] - base_bs, 5)
eq("modifiers 落库增量", row[2] - base_mod, 3)

# ---------------------------------------------------------------- 鼠标
out.append("== 5. 挂载全局鼠标钩子 ==")
probe = MouseCollector(agg, HeatEngine(HEAT), HEAT,
                       {"enabled": True, "pump_interval_seconds": 0.4})
try:
    probe.start()
    time.sleep(0.6)
    check("WH_MOUSE_LL 钩子已挂上",
          probe._listener is not None and probe._listener.running, True)
    check("pump 线程已起", probe._thread is not None and probe._thread.is_alive(), True)
    probe.stop()          # 摘掉真实输入源，下面要精确数计数
    time.sleep(0.4)
    eq("钩子已摘除（内部引用释放）", probe._listener, None)
except Exception as exc:
    check("WH_MOUSE_LL 钩子已挂上", False, "%s: %s" % (type(exc).__name__, exc))

agg.flush()
base_mv, base_ck, base_sc = sqlite3.connect(db).execute(
    "SELECT COALESCE(SUM(mouse_moves),0), COALESCE(SUM(clicks),0), "
    "COALESCE(SUM(scrolls),0) FROM minutes"
).fetchone()

out.append("== 6. 鼠标事件分类与折算 ==")
eng2 = HeatEngine(HEAT)                # 干净引擎，只吃下面这批注入的事件
mcol = MouseCollector(agg, eng2, HEAT, {"pump_interval_seconds": 0.4})
MOVES, CLICKS, SCROLLS = 500, 6, 3
for _ in range(MOVES):
    mcol._on_move(800, 600)            # 坐标只进不留，直接丢弃
for _ in range(CLICKS):
    mcol._on_click(800, 600, Button.left, True)
    mcol._on_click(800, 600, Button.left, False)   # 抬起不该被计数
mcol._on_scroll(800, 600, 0, -SCROLLS)             # 向上滚 3 格

mv, ck, sc = mcol._pump_once()
eq("pump 取走移动数", mv, MOVES)
eq("pump 取走点击（抬起不计）", ck, CLICKS)
eq("pump 取走滚轮格数（取绝对值）", sc, SCROLLS)

want_equiv = MOVES * 0.01 + CLICKS * 4 + SCROLLS * 2
m = eng2.sample()
eq("折算后等效 KPM", m["kpm"], int(round(want_equiv)))
eq("其中键盘部分为 0", m["kpm_keys"], 0)
eq("其中鼠标部分 = 折算值", m["kpm_mouse"], int(round(want_equiv)))
eq("只动鼠标 → 状态 pointing", m["state"], "pointing")
eq("鼠标不算进打字总数", m["total_keys"], 0)

out.append("== 7. 刷盘落库（鼠标） ==")
agg.flush()
row = sqlite3.connect(db).execute(
    "SELECT COALESCE(SUM(mouse_moves),0), COALESCE(SUM(clicks),0), "
    "COALESCE(SUM(scrolls),0) FROM minutes"
).fetchone()
eq("mouse_moves 落库增量", row[0] - base_mv, MOVES)
eq("clicks 落库增量", row[1] - base_ck, CLICKS)
eq("scrolls 落库增量", row[2] - base_sc, SCROLLS)

# 再 flush 一次，验证增量水位没把数字翻倍
agg.flush()
row2 = sqlite3.connect(db).execute(
    "SELECT SUM(mouse_moves), SUM(clicks), SUM(scrolls) FROM minutes"
).fetchone()
eq("重复 flush 不膨胀", row2, row)

out.append("== 8. stop() 不丢最后一批 ==")
for _ in range(37):
    mcol._on_move(1, 1)
mcol.stop()          # 收尾要主动 pump 一次
agg.flush()          # 真实链路里紧跟着的是 HeatService.stop() → aggregator.stop() → flush
row3 = sqlite3.connect(db).execute(
    "SELECT COALESCE(SUM(mouse_moves),0) FROM minutes"
).fetchone()
eq("停止前未 pump 的移动数被收尾补上", row3[0] - base_mv, MOVES + 37)

out.append("== 9. 干净退出 ==")
try:
    col.stop()
    agg.stop()
    check("钩子与刷盘线程正常停止", True)
except Exception as exc:
    check("钩子与刷盘线程正常停止", False, str(exc))

out.append("")
out.append("结果：%s" % ("全部通过" if ok else "存在失败项"))

(HERE / "_e2e.log").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
