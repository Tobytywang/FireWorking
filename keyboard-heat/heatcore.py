"""键盘 + 鼠标热度核心引擎 —— 采集 / 热度计算 / 分钟级持久化。

两条硬约束决定了整个实现形态：

1. 钩子回调必须在微秒级返回。WH_KEYBOARD_LL / WH_MOUSE_LL 的回调都是串在系统
   输入队列上的，回调里做任何 I/O 都会让全机输入变卡。所以键盘侧的回调只做
   整数加法和 deque.append，鼠标侧更极端 —— 回调只做整数自增，折算与落库由
   一个 2 秒一轮的 pump 线程批量搬运（鼠标事件频率比键盘高一个数量级）。
2. 隐私边界写死。落库只有 7 列 —— 分钟时间戳、击键数、退格数、修饰键数、
   活跃秒数、鼠标移动次数、点击次数、滚轮格数。不记录键值、窗口标题、进程名，
   鼠标坐标只作为回调参数出现随即丢弃。代码里不留开关。
"""

from __future__ import annotations

import ctypes
import json
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS minutes (
    minute_ts   INTEGER PRIMARY KEY,   -- epoch 秒，对齐到整分钟
    keystrokes  INTEGER NOT NULL DEFAULT 0,
    backspaces  INTEGER NOT NULL DEFAULT 0,
    modifiers   INTEGER NOT NULL DEFAULT 0,
    active_secs INTEGER NOT NULL DEFAULT 0,
    mouse_moves INTEGER NOT NULL DEFAULT 0,
    clicks      INTEGER NOT NULL DEFAULT 0,
    scrolls     INTEGER NOT NULL DEFAULT 0
);

-- 每次「倒计时开始」记一行，用于报告里的「每天按类型计数」。
-- minutes 是时长（分钟），source 是触发来源：
--   menu         托盘菜单「倒计时」子菜单里选的档位
--   single_click 左键单击托盘图标配置的「快速开始」（快捷入口之一）
--   double_click 左键双击托盘图标配置的「快速开始」（快捷入口之一）
--   hotkey       Tk 版 Ctrl+Alt+T 热键循环
CREATE TABLE IF NOT EXISTS countdown_log (
    ts      INTEGER NOT NULL,          -- epoch 秒，倒计时开始的时刻
    minutes INTEGER NOT NULL,          -- 时长（分钟）：5 / 10 / 25
    source  TEXT    NOT NULL DEFAULT 'menu'
);
"""

# 老库只有 5 列，升级时要补列。放在模块级而不是塞进累加器里，是因为只跑报告
# 的场景同样要能打开老库 —— report.py 直接连库，也得先补列。
MIGRATIONS = (
    ("mouse_moves", "ALTER TABLE minutes ADD COLUMN mouse_moves INTEGER NOT NULL DEFAULT 0"),
    ("clicks",      "ALTER TABLE minutes ADD COLUMN clicks INTEGER NOT NULL DEFAULT 0"),
    ("scrolls",     "ALTER TABLE minutes ADD COLUMN scrolls INTEGER NOT NULL DEFAULT 0"),
)

# minute 行的字段顺序。全项目只此一份：内存累加、增量差值、SQL 参数、报告读取
# 都按它走，以后再加字段不会漏掉某一处。
FIELDS = ("keystrokes", "backspaces", "modifiers", "active_secs",
          "mouse_moves", "clicks", "scrolls")
N_FIELDS = len(FIELDS)
ACTIVE_IDX = 3          # active_secs 的下标 —— 它是秒数，不是计数


def ensure_schema(conn):
    """建表 + 给老库补列，历史数据原样保留。"""
    conn.executescript(SCHEMA)
    have = {r[1] for r in conn.execute("PRAGMA table_info(minutes)")}
    for name, ddl in MIGRATIONS:
        if name not in have:
            conn.execute(ddl)


def log_countdown(minutes, source="menu", db_path=None):
    """记一次「倒计时开始」。

    只在 minutes>0 时落库（`关闭` 那一项是清状态，不算一次使用）。
    db_path 不传就按 config 默认位置找库。单独开一个短连接、写完即关 ——
    倒计时开始是极低频事件，不值得复用采集线程的锁，也不会和分钟级刷盘抢连接。
    """
    if not minutes or minutes <= 0:
        return
    if db_path is None:
        cfg = {}
        try:
            cfg = load_config()
        except FileNotFoundError:
            pass
        db_path = PROJECT_DIR / cfg_get(cfg.get("storage", {}), "db_path", "data/heat.db")
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(db_path) as conn:
            ensure_schema(conn)
            conn.execute(
                "INSERT INTO countdown_log (ts, minutes, source) VALUES (?, ?, ?)",
                (int(time.time()), int(minutes), source),
            )
    except sqlite3.Error:
        # 记统计不该影响倒计时本身，落库失败就静默放过。
        pass


# ---------------- 单实例保护 ----------------

_MUTEX_NAME = r"Local\KeyboardHeatDial.SingleInstance"
_mutex_handle = None          # 必须一直持有，进程退出时才释放


def claim_single_instance():
    """尝试独占单实例锁；已有实例在跑时返回 False。

    重复启动绝不能静默退出 —— 用户肯再双击一次，动机往往正是"我看不到，
    再点一次试试"。静默退出只会加深"这东西没用"的错觉。
    """
    global _mutex_handle
    if _mutex_handle:
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    handle = kernel32.CreateMutexW(None, 0, _MUTEX_NAME)
    already = ctypes.get_last_error() == 183        # ERROR_ALREADY_EXISTS
    _mutex_handle = handle
    return not already


def notify_already_running():
    """给重复启动的用户一个置顶提示，顺手把排查动作说清楚。"""
    MB_ICONINFORMATION = 0x00000040
    MB_TOPMOST = 0x00040000
    MB_SETFOREGROUND = 0x00010000
    ctypes.windll.user32.MessageBoxW(
        None,
        "键盘热度显示器已经在运行了。\n\n"
        "悬浮窗固定在屏幕右下角，是一个半透明的圆形表盘；\n"
        "启动后的 1.4 秒里它会扫一圈亮个相。\n\n"
        "如果觉得看不清：\n"
        "  · 打开 config.json，把 overlay.theme 改成 \"light\"\n"
        "    （浅色底盘在深色桌面 / 终端上对比度最强）\n"
        "  · 或者把 overlay.bg_alpha 调到 0.9 以上\n\n"
        "要退出正在运行的实例：Ctrl + Alt + Q",
        "键盘热度 · 已在运行",
        MB_ICONINFORMATION | MB_TOPMOST | MB_SETFOREGROUND,
    )


# 热度色阶：冷蓝 → 青绿 → 草绿 → 琥珀 → 橙 → 红。
# 界面上用「弧长 + 弧色」两个通道冗余表达同一个热度值，扫一眼就能读，
# 不用盯着数字。两个界面实现（PyQt6 / Tkinter）共用这一份，保证观感一致。
HEAT_STOPS = (
    (0.00, (0x4A, 0x9E, 0xE8)),
    (0.22, (0x37, 0xB5, 0xA8)),
    (0.45, (0x7C, 0xB3, 0x42)),
    (0.65, (0xE0, 0xB0, 0x2C)),
    (0.82, (0xE3, 0x7B, 0x2A)),
    (1.00, (0xDE, 0x3B, 0x3B)),
)


def heat_rgb(frac):
    """热度 0~1 → (r, g, b)。"""
    frac = max(0.0, min(1.0, float(frac)))
    for i in range(len(HEAT_STOPS) - 1):
        f0, c0 = HEAT_STOPS[i]
        f1, c1 = HEAT_STOPS[i + 1]
        if frac <= f1:
            t = 0.0 if f1 == f0 else (frac - f0) / (f1 - f0)
            return (
                round(c0[0] + (c1[0] - c0[0]) * t),
                round(c0[1] + (c1[1] - c0[1]) * t),
                round(c0[2] + (c1[2] - c0[2]) * t),
            )
    return HEAT_STOPS[-1][1]


def heat_hex(frac):
    """热度 0~1 → '#RRGGBB'。Tkinter 只认颜色字符串。"""
    r, g, b = heat_rgb(frac)
    return "#%02X%02X%02X" % (r, g, b)


def load_config(path=None):
    path = Path(path or DEFAULT_CONFIG_PATH)
    if not path.exists():
        raise FileNotFoundError("配置文件不存在：%s" % path)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def cfg_get(cfg, key, default=None):
    """读一个配置项，同时认 "key" 和 "*key" 两种写法。

    config.json 里给常用项加 * 前缀（"*bg_alpha"），目的是让人在几十行 JSON 里
    一眼找到"该调哪几个"，"_key" 则用来放中文说明。但读配置的代码不该知道这个
    排版约定 —— 统一在这里兜住。

    （真实踩过的坑：配置里写着 "*size": 190，代码读 cfg.get("size", 176)，
    结果永远拿到 176 —— 用户改了配置却毫无反应，且没有任何报错。）
    """
    if key in cfg:
        return cfg[key]
    star = "*" + key
    if star in cfg:
        return cfg[star]
    return default


def cfg_set(cfg, key, value):
    """写回配置项，带星号的别名一起更新，避免出现两份互相矛盾的取值。"""
    cfg[key] = value
    star = "*" + key
    if star in cfg:
        cfg[star] = value
    return value


def save_config(cfg, path=None):
    """回写配置。托盘里改的位置/透明度要能跨重启保留。"""
    path = Path(path or DEFAULT_CONFIG_PATH)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


class MinuteAggregator:
    """分钟级累加器 + 增量刷盘。

    为什么刷"增量"而不是直接 UPSERT 累计值：同一个分钟桶会被反复刷盘，
    如果每次都把累计值 UPSERT 上去，数字会成倍膨胀。所以只写相对上次
    已落库部分的差值，用 _synced 记录水位。
    """

    def __init__(self, db_path, flush_interval=5.0):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.flush_interval = float(flush_interval)

        self._lock = threading.Lock()
        self._totals = {}          # minute_ts -> [keys, bs, mods, active_secs(float)]
        self._synced = {}          # minute_ts -> 已落库水位，同结构
        self._last_seen = 0.0
        self._stop = threading.Event()
        self._thread = None

        with sqlite3.connect(self.db_path) as conn:
            ensure_schema(conn)

    # 事件种类 → _totals 行里的下标。active_secs 不在表内：它由时间差累加，
    # 不是一个"事件"。
    _COL = {
        "keystroke": 0,
        "backspace": 1,
        "modifier": 2,
        "mouse_move": 4,
        "click": 5,
        "scroll": 6,
    }
    _EMPTY = (0, 0, 0, 0.0) + (0,) * (N_FIELDS - 4)

    # ---------- 采集侧：钩子线程调用，必须是 O(1) 纯内存操作 ----------
    def record(self, kind, n=1):
        col = self._COL.get(kind)
        if col is None:
            return
        now = time.time()
        minute = int(now // 60) * 60
        with self._lock:
            row = self._totals.get(minute)
            if row is None:
                row = list(self._EMPTY)
                self._totals[minute] = row
            row[col] += n
            gap = now - self._last_seen
            if 0.0 < gap < 3.0:        # 间隔超过 3 秒视为停顿，不计入活跃时长
                row[ACTIVE_IDX] += gap
            self._last_seen = now

    # ---------- 刷盘侧：后台线程 ----------
    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="heat-flush", daemon=True)
            self._thread.start()
        return self

    def _loop(self):
        while not self._stop.wait(self.flush_interval):
            try:
                self.flush()
            except Exception:
                pass                    # 刷盘失败不影响采集，下一轮重试

    def flush(self):
        with self._lock:
            deltas = {}
            for minute, total in self._totals.items():
                done = self._synced.get(minute, self._EMPTY)
                diff = tuple(total[i] - done[i] for i in range(N_FIELDS))
                if any(v > 0 for v in diff):
                    deltas[minute] = diff
                    self._synced[minute] = tuple(total)

            cutoff = int(time.time() // 60) * 60 - 1800      # 内存里只留最近 30 分钟
            for m in [m for m in self._synced if m < cutoff]:
                del self._synced[m]
            for m in [m for m in self._totals if m < cutoff]:
                del self._totals[m]

        if not deltas:
            return 0

        rows = [
            (m,) + tuple(
                int(round(d[i])) if i == ACTIVE_IDX else int(d[i])
                for i in range(N_FIELDS)
            )
            for m, d in deltas.items()
        ]
        # SQL 跟着 FIELDS 动态拼，以后加列只改 FIELDS 一处
        cols = ", ".join(("minute_ts",) + FIELDS)
        marks = ", ".join("?" * (N_FIELDS + 1))
        updates = ", ".join("%s = %s + excluded.%s" % (f, f, f) for f in FIELDS)
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "INSERT INTO minutes(%s) VALUES(%s) "
                "ON CONFLICT(minute_ts) DO UPDATE SET %s" % (cols, marks, updates),
                rows,
            )
        return len(rows)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        try:
            self.flush()
        except Exception:
            pass


# 热度低于它就当作 0 —— **只在空闲衰减那一支生效**。
#
# 这个下限曾经写在上升支上（每帧算完都 `if heat < 0.5: heat = 0`），后果是：
# EMA 从 0 出发时，每步增量是 `target * weight`，而每步都从 0 重来 —— 增量一次
# 到不了 0.5 就永远到不了。篝火模式 80ms 刷新 → weight = 0.0177 → 打字强度低于
# `full_kpm × 0.5/0.0177 ≈ 85 kpm` 时**热度永远卡在 0，火一点反应都没有**；
# 一过 85 kpm，火又"啪"地跳到 0.5 然后开始长 —— 看起来就是个凭空出现的突变。
# 实测：60/80/84 kpm 打满 120 秒火焰纹丝不动，90 kpm 要等 56.6 秒才起跳，
# 起跳那一帧火苗尺寸一步 +5.4px（见 _smooth_probe.py）。
#
# 0.05 是"低于显示精度"的值：快照把热度量化到 0.01，衰减到 0.05 以下抹零，
# 火焰尺寸上只剩 ~1.5px 的差 —— 反向（灭火）那一下也不会看出台阶。
_HEAT_FLOOR = 0.05


class HeatEngine:
    """实时热度：60 秒滑动窗口 → EMA 平滑 → 空闲指数衰减。

    三层处理缺一不可：
      - 滑动窗口把瞬时抖动摊平，"每分钟击键数"这个指标才有意义
      - EMA 让 UI 上的数字不会每秒乱跳（alpha=0.2 约等于 5 秒时间常数）
      - 空闲衰减让停手后热度平滑回落，而不是硬切到 0
    """

    def __init__(self, cfg):
        self.window = float(cfg_get(cfg, "window_seconds", 60))
        self.alpha = float(cfg_get(cfg, "ema_alpha", 0.2))
        self.full_kpm = float(cfg_get(cfg, "full_kpm", 300))
        self.idle_after = float(cfg_get(cfg, "idle_after_seconds", 30))
        self.decay = float(cfg_get(cfg, "decay_per_second", 0.9))
        # 鼠标折算系数：把鼠标活动换算成"等效击键数"，才能和键盘并进同一个热度
        self.w_move = float(cfg_get(cfg, "w_move", 0.01))
        self.w_click = float(cfg_get(cfg, "w_click", 4.0))
        self.w_scroll = float(cfg_get(cfg, "w_scroll", 2.0))

        self._lock = threading.Lock()
        # 秒级桶 [(sec, weight), ...]，而不是逐事件的 deque。
        # 鼠标移动每秒能产生几百个事件，逐条 append + 每帧 popleft 会把采集线程
        # 和 UI 线程一起拖住；按秒归并后桶数恒定为 ≤ 61 个。
        self._buckets = deque()
        self._kb_buckets = deque()      # 只装键盘，用于界面上的键/鼠分解
        self._heat = 0.0
        self._last_active = 0.0
        self._last_key = 0.0
        self._last_tick = time.monotonic()
        self._peak = 0.0
        self._total = 0

    @staticmethod
    def _bump(buckets, sec, weight):
        if buckets and buckets[-1][0] == sec:
            buckets[-1][1] += weight
        else:
            buckets.append([sec, weight])

    @staticmethod
    def _prune_sum(buckets, window_start):
        while buckets and buckets[0][0] < window_start:
            buckets.popleft()
        return sum(b[1] for b in buckets)

    def record(self, weight=1.0, is_key=True):
        """记一次活动。weight 是折算后的等效击键数。"""
        now = time.monotonic()
        sec = int(now)
        with self._lock:
            self._bump(self._buckets, sec, weight)
            if is_key:
                self._bump(self._kb_buckets, sec, 1.0)
                self._total += 1
                self._last_key = now
            self._last_active = now

    def sample(self):
        """UI 每次刷新调用一次，返回状态快照。"""
        now = time.monotonic()
        with self._lock:
            window_start = now - self.window
            kpm = self._prune_sum(self._buckets, window_start) * 60.0 / self.window
            kpm_keys = self._prune_sum(self._kb_buckets, window_start) * 60.0 / self.window

            dt = min(max(now - self._last_tick, 0.0), 2.0)
            self._last_tick = now

            idle = (now - self._last_active) if self._last_active else 1e9
            if self._last_active and idle > self.idle_after:
                self._heat *= self.decay ** dt
                # 只在**衰减**这一支把趋近 0 的尾巴抹掉（免得长时间没动还挂着
                # "热度 0.3"）。这个下限绝不能放在上升那一支 —— 见下面 _FLOOR 的注释。
                if self._heat < _HEAT_FLOOR:
                    self._heat = 0.0
            else:
                target = min(kpm / self.full_kpm, 1.0) * 100.0
                # 把"每秒 alpha"折算到本次 dt，刷新率变了效果也不变
                weight = 1.0 - (1.0 - self.alpha) ** dt
                self._heat += (target - self._heat) * weight
            self._heat = min(max(self._heat, 0.0), 100.0)
            self._peak = max(self._peak, self._heat)

            key_idle = (now - self._last_key) if self._last_key else 1e9
            if not self._last_active or idle > self.idle_after * 4:
                state = "idle"
            elif idle > self.idle_after:
                state = "pause"
            elif key_idle <= self.idle_after:
                state = "typing"
            else:
                state = "pointing"      # 一直在动鼠标但没打字

            return {
                # 两位小数而不是一位：火焰在冷端对热度极敏感（跨度 ∝ 热度^0.54），
                # 量化到 0.1 时"刚起步"那一步就有 2.4px 的尺寸台阶。见 _HEAT_FLOOR。
                "heat": round(self._heat, 2),
                "kpm": int(round(kpm)),
                "kpm_keys": int(round(kpm_keys)),
                "kpm_mouse": int(round(max(0.0, kpm - kpm_keys))),
                "peak": round(self._peak, 1),
                "idle_seconds": float(idle),
                "state": state,
                "total_keys": self._total,
            }


class KeyboardCollector:
    """pynput 低层钩子的薄封装。

    分类规则：
      - 退格 / 删除  → backspace。单列是因为"疯狂退格"和"顺畅输出"是完全
                       不同的工作状态，混在一起会把信号抹掉。
      - 修饰键       → modifier。长按 Shift 会产生系统 repeat 事件，靠 _held
                       集合去重，否则按住 Shift 一秒能把热度刷满。
      - 其余         → keystroke。
    """

    _ERASE = frozenset({
        "backspace", "delete",
    })
    _MODIFIER_NAMES = frozenset({
        "ctrl", "ctrl_l", "ctrl_r",
        "shift", "shift_l", "shift_r",
        "alt", "alt_l", "alt_r", "alt_gr",
        "cmd", "cmd_l", "cmd_r",
    })

    def __init__(self, aggregator, engine):
        self._agg = aggregator
        self._engine = engine
        self._held = set()
        self._listener = None

    @staticmethod
    def _name(key):
        """把 pynput 的 Key / KeyCode 归一成可比较的字符串。

        直接用 Key 对象做集合查找也能work，但 pynput 在不同后端下同一个键
        可能产出不同对象，转成字符串更稳。
        """
        name = getattr(key, "name", None)
        if name:
            return name
        return "char"          # KeyCode（字母数字符号键）

    def _on_press(self, key):
        name = self._name(key)
        if name in self._ERASE:
            self._agg.record("backspace")
            self._engine.record()
            return
        if name in self._MODIFIER_NAMES:
            if name in self._held:
                return          # 系统按键重复，忽略
            self._held.add(name)
            self._agg.record("modifier")
            self._engine.record()
            return
        self._agg.record("keystroke")
        self._engine.record()

    def _on_release(self, key):
        self._held.discard(self._name(key))

    def start(self):
        from pynput import keyboard
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False,
        )
        self._listener.daemon = True
        self._listener.start()
        return self

    def stop(self):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


class MouseCollector:
    """鼠标活动的薄封装。

    和键盘那条链路有一处刻意不同：**钩子回调里只做整数自增**，折算和落库全部
    交给一个低频 pump 线程。原因是 WH_MOUSE_LL 的回调频率比键盘高一个数量级
    （指针每移动一个像素就触发一次），若每次都在回调里排队抢锁、算权重，
    指针会明显发涩。批量搬运把锁竞争从每秒数百次压到每 2 秒一次。

    隐私：坐标只作为回调参数出现，随即丢弃 —— 既不落库，也不进任何持久结构。
    统计到的只有"移动了多少次 / 点了几下 / 滚了几格"。
    """

    def __init__(self, aggregator, engine, heat_cfg, mouse_cfg=None):
        self._agg = aggregator
        self._engine = engine
        mouse_cfg = mouse_cfg or {}
        self._enabled = bool(cfg_get(mouse_cfg, "enabled", True))
        self._pump_interval = float(cfg_get(mouse_cfg, "pump_interval_seconds", 2.0))

        self.w_move = float(cfg_get(heat_cfg, "w_move", 0.01))
        self.w_click = float(cfg_get(heat_cfg, "w_click", 4.0))
        self.w_scroll = float(cfg_get(heat_cfg, "w_scroll", 2.0))

        self._lock = threading.Lock()
        self._mv = 0
        self._ck = 0
        self._sc = 0
        self._by_button = {}

        self._listener = None
        self._thread = None
        self._stop = threading.Event()

    # ---------- 钩子回调：路径要尽可能短 ----------
    def _on_move(self, x, y):
        with self._lock:
            self._mv += 1

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return                  # 只记按下，否则一次点击会被算成两下
        name = getattr(button, "name", "other")
        with self._lock:
            self._ck += 1
            self._by_button[name] = self._by_button.get(name, 0) + 1

    def _on_scroll(self, x, y, dx, dy):
        with self._lock:
            self._sc += abs(int(dy))

    # ---------- pump：把累计值折算后交给聚合器与引擎 ----------
    def _take(self):
        with self._lock:
            mv, ck, sc = self._mv, self._ck, self._sc
            self._mv = self._ck = self._sc = 0
            return mv, ck, sc

    def _pump_once(self):
        mv, ck, sc = self._take()
        if mv:
            self._agg.record("mouse_move", mv)
            self._engine.record(weight=mv * self.w_move, is_key=False)
        if ck:
            self._agg.record("click", ck)
            self._engine.record(weight=ck * self.w_click, is_key=False)
        if sc:
            self._agg.record("scroll", sc)
            self._engine.record(weight=sc * self.w_scroll, is_key=False)
        return mv, ck, sc

    def _loop(self):
        while not self._stop.wait(self._pump_interval):
            try:
                self._pump_once()
            except Exception:
                pass                # 折算失败不影响采集，下一轮再来

    @property
    def clicks_by_button(self):
        with self._lock:
            return dict(self._by_button)

    def start(self):
        if not self._enabled:
            return self
        from pynput import mouse
        self._listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._listener.daemon = True
        self._listener.start()

        self._thread = threading.Thread(target=self._loop, name="heat-mouse", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        try:
            self._pump_once()       # 收尾：把最后一批计数交出去，别丢
        except Exception:
            pass


class HeatService:
    """门面：把配置、采集、聚合、热度计算打包，UI 只跟它打交道。"""

    def __init__(self, config_path=None):
        self.config = load_config(config_path)
        base = PROJECT_DIR

        storage = self.config.get("storage", {})
        db_path = Path(cfg_get(storage, "db_path", "data/heat.db"))
        if not db_path.is_absolute():
            db_path = base / db_path
        self.db_path = db_path

        self.heat_cfg = self.config.get("heat", {})
        self.aggregator = MinuteAggregator(
            db_path, cfg_get(storage, "flush_interval_seconds", 5)
        )
        self.engine = HeatEngine(self.heat_cfg)
        self.collector = KeyboardCollector(self.aggregator, self.engine)
        self.mouse = MouseCollector(
            self.aggregator, self.engine, self.heat_cfg, self.config.get("mouse", {})
        )
        self._paused = False

    def start(self):
        self.aggregator.start()
        self.collector.start()
        self.mouse.start()
        return self

    def stop(self):
        self.collector.stop()
        self.mouse.stop()
        self.aggregator.stop()

    def toggle_pause(self):
        """暂停/恢复采集。注意是丢弃事件而非停止钩子 —— 频繁停启钩子容易触发杀软。"""
        self._paused = not self._paused
        return self._paused

    @property
    def paused(self):
        return self._paused

    def snapshot(self):
        if self._paused:
            snap = dict(self.engine.sample())
            snap["heat"] = 0.0
            snap["kpm"] = 0
            snap["kpm_keys"] = 0
            snap["kpm_mouse"] = 0
            snap["state"] = "paused"
            return snap
        return self.engine.sample()
