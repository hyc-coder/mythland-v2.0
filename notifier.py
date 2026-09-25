"""
notifier.py - 被控端桌面通知弹窗（右下角向上滑入）

用途: 控制端「发送消息」时，在被控端屏幕右下角弹出通知。

设计要点:
  1. 独立线程: Tk 必须在自己的线程里创建和循环，不能从网络线程直接调。
     这里用【一个专用弹窗线程 + 队列】，主线程(网络线程)只负责往队列里丢消息。
  2. 窗口无边框(overrideredirect)，自绘标题栏和内容区。
  3. 动画: 从屏幕右下角【下方】滑入到目标位置，约 300ms；
     消失时反向滑出，再销毁。
  4. 堆叠: 多条消息从下往上依次排列，最多同屏 4 条，超出则移除最旧的。
  5. 自动消失: 默认 8 秒；鼠标悬停时暂停倒计时，移开继续。
  6. 最多同时存在 MAX_POPUPS 个，避免刷屏。

用法:
    from notifier import notify, notify_async
    notify("标题", "内容", sender="教师机")     # 阻塞式(内部会转交线程)
    notify_async("标题", "内容")                 # 推荐: 立即返回，不阻塞
"""

import queue
import platform
import threading
import time

try:
    import tkinter as tk
    HAS_TK = True
except Exception:
    tk = None
    HAS_TK = False

IS_WINDOWS = platform.system() == "Windows"

# ---------- 可调参数 ----------
POPUP_W = 320              # 弹窗宽度
POPUP_H_MIN = 96           # 最小高度（内容多会自动增高）
POPUP_MARGIN = 12          # 距屏幕边缘的间距
POPUP_GAP = 8              # 弹窗之间的间距
ANIM_STEP_MS = 12          # 动画每帧间隔
ANIM_DIST = 12             # 每帧移动像素（越大越快）
DEFAULT_TIMEOUT = 8.0      # 默认停留秒数（0 = 不自动消失）
MAX_POPUPS = 4             # 同屏最多几个

# 配色
C_TITLE_BG = "#1565c0"
C_TITLE_FG = "#ffffff"
C_BODY_BG = "#ffffff"
C_TEXT = "#37474f"
C_SENDER = "#78909c"
C_BORDER = "#90caf9"
C_CLOSE = "#e3f2fd"
C_CLOSE_FG = "#1565c0"

# 级别 → 标题栏颜色（info / warn / error）
LEVEL_COLORS = {
    "info": "#1565c0",
    "warn": "#ef6c00",
    "error": "#c62828",
}


class _Popup:
    """单个弹窗（含自己的动画状态）"""

    def __init__(self, master, title, text, sender="", timeout=DEFAULT_TIMEOUT,
                 level="info", index=0):
        self.master = master
        self.title = title
        self.text = text
        self.sender = sender
        self.timeout = float(timeout or 0)
        self.level = level if level in LEVEL_COLORS else "info"
        self.index = index

        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)          # 无边框
        self.win.attributes("-topmost", True)    # 置顶
        try:
            self.win.attributes("-alpha", 0.98)
        except Exception:
            pass

        # 估算高度：按内容行数
        n_lines = max(1, len(text) // 22 + text.count("\n") + 1)
        self.h = max(POPUP_H_MIN, 62 + n_lines * 18)
        self.w = POPUP_W

        self._build()
        self._place_offscreen()
        self._animating_in = True
        self._hover = False
        self._elapsed = 0.0
        self._last_tick = time.time()
        self._closed = False

    # ---- 构建界面 ----
    def _build(self):
        bg_title = LEVEL_COLORS[self.level]
        self.win.configure(bg=C_BORDER)

        # 标题栏
        bar = tk.Frame(self.win, bg=bg_title, height=28)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text=self.title or "消息", bg=bg_title, fg=C_TITLE_FG,
                 font=("Microsoft YaHei", 9, "bold"),
                 anchor="w").pack(side="left", padx=8)
        close = tk.Label(bar, text="✕", bg=bg_title, fg=C_TITLE_FG,
                         font=("Microsoft YaHei", 10), cursor="hand2")
        close.pack(side="right", padx=8)
        close.bind("<Button-1>", lambda e: self.close())

        # 内容区
        body = tk.Frame(self.win, bg=C_BODY_BG)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=self.text, bg=C_BODY_BG, fg=C_TEXT,
                 font=("Microsoft YaHei", 9), justify="left",
                 anchor="nw", wraplength=POPUP_W - 24).pack(
            fill="both", expand=True, padx=10, pady=(8, 2))

        if self.sender:
            tk.Label(body, text=f"来自: {self.sender}", bg=C_BODY_BG,
                     fg=C_SENDER, font=("Microsoft YaHei", 8),
                     anchor="e").pack(fill="x", padx=10, pady=(0, 6))

        # 鼠标悬停暂停倒计时
        for w in (self.win, bar, body):
            w.bind("<Enter>", lambda e: self._set_hover(True))
            w.bind("<Leave>", lambda e: self._set_hover(False))
        self.win.bind("<Button-1>", lambda e: self.close())

    def _set_hover(self, v):
        self._hover = v

    # ---- 位置 ----
    def target_xy(self):
        """目标位置：右下角，按 index 从下往上堆叠"""
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = sw - self.w - POPUP_MARGIN
        y = sh - POPUP_MARGIN - (self.index + 1) * (self.h + POPUP_GAP) + POPUP_GAP
        return x, max(POPUP_MARGIN, y)

    def _place_offscreen(self):
        """起始位置：屏幕下方外面（滑入动画的起点）"""
        x, y = self.target_xy()
        self.target_y = y
        self.win.geometry(f"{self.w}x{self.h}+{x}+{y + self.h + 40}")

    def slide_in(self):
        """每帧上移一点，直到到达目标位置"""
        try:
            x, _ = self.target_xy()
            cur_y = self.win.winfo_y()
            if cur_y <= self.target_y:
                self.win.geometry(f"{self.w}x{self.h}+{x}+{self.target_y}")
                self._animating_in = False
                return
            self.win.geometry(f"{self.w}x{self.h}+{x}+{cur_y - ANIM_DIST}")
            self.win.after(ANIM_STEP_MS, self.slide_in)
        except Exception:
            self._animating_in = False

    def slide_out(self):
        """滑出动画：向下移出屏幕后销毁"""
        try:
            x, _ = self.target_xy()
            cur_y = self.win.winfo_y()
            bottom = self.win.winfo_screenheight()
            if cur_y > bottom:
                self._destroy()
                return
            self.win.geometry(f"{self.w}x{self.h}+{x}+{cur_y + ANIM_DIST}")
            self.win.after(ANIM_STEP_MS, self.slide_out)
        except Exception:
            self._destroy()

    def close(self):
        """开始关闭（滑出）"""
        if self._closed:
            return
        self._closed = True
        try:
            self.slide_out()
        except Exception:
            self._destroy()

    def _destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass

    # ---- 倒计时 ----
    def tick(self):
        """由弹窗线程的主循环定期调用，返回 True 表示还活着"""
        if self._closed:
            return True                      # 正在播放滑出动画
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now

        if self.timeout > 0 and not self._hover and not self._animating_in:
            self._elapsed += dt
            if self._elapsed >= self.timeout:
                self.close()
        return True


class Notifier:
    """
    弹窗管理器：跑在一个专用线程里，持有 Tk 根窗口。

    外部只需调 notify_async() 往队列丢消息，不会阻塞网络线程。
    """

    def __init__(self):
        self._q = queue.Queue()
        self._popups = []
        self._root = None
        self._thread = None
        self._running = False
        self._started = False
        self._lock = threading.Lock()

    # ---- 对外接口 ----
    def notify(self, title, text, sender="", timeout=DEFAULT_TIMEOUT,
               level="info"):
        """丢一条消息进队列（立即返回，不阻塞）"""
        if not HAS_TK:
            print(f"[通知] (无 tkinter，无法显示弹窗) {title}: {text}")
            return False
        self._ensure_thread()
        self._q.put({
            "title": title, "text": text, "sender": sender,
            "timeout": timeout, "level": level,
        })
        return True

    # ---- 内部 ----
    def _ensure_thread(self):
        with self._lock:
            if self._started:
                return
            self._started = True
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        """弹窗线程主循环"""
        try:
            self._root = tk.Tk()
            self._root.withdraw()          # 隐藏根窗口，只用 Toplevel
        except Exception as e:
            print(f"[通知] 无法创建窗口: {e}")
            self._started = False
            return

        self._pump()
        try:
            self._root.mainloop()
        except Exception:
            pass

    def _pump(self):
        """每 100ms 处理一次：取出新消息 + 推进已有弹窗的倒计时"""
        try:
            # 1. 新消息
            while True:
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                self._spawn(item)

            # 2. 倒计时 + 清理已销毁的
            alive = []
            for p in self._popups:
                try:
                    if p.win.winfo_exists() and p.tick():
                        alive.append(p)
                except Exception:
                    pass
            self._popups = alive

            # 3. 重排（有弹窗消失后，其余的往下补位）
            for i, p in enumerate(self._popups):
                if p.index != i and not p._animating_in and not p._closed:
                    p.index = i
                    x, y = p.target_xy()
                    p.target_y = y
                    try:
                        p.win.geometry(f"{p.w}x{p.h}+{x}+{y}")
                    except Exception:
                        pass
        except Exception as e:
            print(f"[通知] 循环异常: {e}")

        if self._running:
            self._root.after(100, self._pump)

    def _spawn(self, item):
        # 超出上限：关掉最旧的
        while len(self._popups) >= MAX_POPUPS:
            old = self._popups.pop(0)
            try:
                old.close()
            except Exception:
                pass

        idx = len(self._popups)
        try:
            p = _Popup(self._root,
                       title=item.get("title", "消息"),
                       text=item.get("text", ""),
                       sender=item.get("sender", ""),
                       timeout=item.get("timeout", DEFAULT_TIMEOUT),
                       level=item.get("level", "info"),
                       index=idx)
        except Exception as e:
            print(f"[通知] 创建弹窗失败: {e}")
            return
        self._popups.append(p)
        p.slide_in()

    def shutdown(self):
        self._running = False
        try:
            if self._root:
                self._root.after(0, self._root.quit)
        except Exception:
            pass


# ---------- 全局单例 ----------
_notifier = None
_n_lock = threading.Lock()


def get_notifier() -> Notifier:
    global _notifier
    with _n_lock:
        if _notifier is None:
            _notifier = Notifier()
        return _notifier


def notify(title, text, sender="", timeout=DEFAULT_TIMEOUT, level="info") -> bool:
    """发一条桌面通知（立即返回）"""
    return get_notifier().notify(title, text, sender, timeout, level)


# 语义化别名
notify_async = notify


def notify_available() -> bool:
    """当前环境能否弹窗"""
    return HAS_TK
