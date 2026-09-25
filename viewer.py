"""
viewer.py - 屏幕广播【被控端】窗口（学生机）

要求:
  1. 接收主控端推来的画面并显示（直播式）
  2. 【可以调整窗口大小】（可拖动边框 / 最大化）
  3. 【不能关闭】—— 拦截右上角 ✕、Alt+F4、双击标题栏等一切关闭途径
     只能由主控端结束广播（收到 bc_quit 或主控端发 bc_stop_req）

用法:
    from viewer import get_viewer
    v = get_viewer()
    v.start(host="192.168.1.7", port=9100, title="教师机演示")   # 非阻塞
    v.stop()                                                     # 由主控端调用

线程模型:
  - Tk 必须在自己的线程里创建并跑 mainloop，不能从网络线程直接操作。
  - 这里: start() 起一个"UI 线程"建 Tk；UI 线程里再起"接收线程"收帧。
  - 接收线程只把帧放进 queue，UI 线程用 after() 取出来显示（Tk 线程安全）。
  - 只显示【最新一帧】，旧帧丢弃 —— 避免网络慢时画面堆积延迟。
"""

import base64
import io
import os
import queue
import socket
import threading
import time

from common import decode, recv_all, send_all, MSG_BC_FRAME, MSG_BC_QUIT

try:
    import tkinter as tk
    HAS_TK = True
except Exception:
    tk = None
    HAS_TK = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except Exception:
    Image = None
    ImageTk = None
    HAS_PIL = False


# 配色
C_BG = "#0d1b33"
C_BAR_BG = "#1565c0"
C_BAR_FG = "#ffffff"
C_TIP_FG = "#bbdefb"
C_ERR_FG = "#ef9a9a"


class BroadcastViewer:
    """被控端广播窗口（同时只允许一个）"""

    def __init__(self):
        self._thread = None
        self._root = None
        self._stop_flag = threading.Event()
        self._started = threading.Event()
        self._lock = threading.Lock()
        self._frames = None
        self._conn = None
        self._alive = False
        self._last_error = ""

    # ---------- 对外接口 ----------

    def start(self, host: str, port: int, title: str = "屏幕广播") -> bool:
        """
        打开广播窗口（立即返回，不阻塞）。
        返回 False 表示环境不支持（无 tkinter）。
        """
        if not HAS_TK:
            self._last_error = "无 tkinter，无法显示广播窗口"
            print(f"[广播窗口] {self._last_error}")
            return False

        # 已有窗口 → 先关掉，再开新的（避免叠加）
        if self._alive:
            self.stop()
            time.sleep(0.3)

        self._stop_flag.clear()
        self._started.clear()
        self._thread = threading.Thread(
            target=self._run, args=(host, port, title),
            daemon=True, name="广播窗口")
        self._thread.start()
        # 等窗口真正建起来（最多 3 秒），便于调用方判断成败
        self._started.wait(timeout=3.0)
        return self._alive

    def stop(self):
        """由主控端结束广播时调用：关闭窗口、断开连接"""
        self._stop_flag.set()
        # 断开 socket，让阻塞中的 recv 立刻返回
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass
        # 让 Tk 线程自己销毁窗口（Tk 只能在自己的线程操作）
        try:
            if self._root:
                self._root.after(0, self._destroy)
        except Exception:
            pass

    def _destroy(self):
        try:
            self._root.quit()
        except Exception:
            pass
        try:
            self._root.destroy()
        except Exception:
            pass

    def is_alive(self) -> bool:
        return self._alive

    def last_error(self) -> str:
        return self._last_error

    # ---------- 内部：UI 线程 ----------

    def _run(self, host, port, title):
        try:
            self._root = tk.Tk()
        except Exception as e:
            self._last_error = f"创建窗口失败: {e}"
            print(f"[广播窗口] {self._last_error}")
            self._alive = False
            self._started.set()
            return

        root = self._root
        root.title(f"屏幕广播 - {title}")
        root.configure(bg=C_BG)
        root.resizable(True, True)          # ← 允许调整大小
        try:
            root.attributes("-topmost", True)   # 广播置顶，学生在看
        except Exception:
            pass

        # ===== 关键: 禁止关闭 =====
        root.protocol("WM_DELETE_WINDOW", self._on_close_attempt)
        root.bind("<Alt-F4>", lambda e: "break")
        root.bind("<Escape>", lambda e: "break")
        root.bind("<Control-w>", lambda e: "break")
        root.bind("<Control-W>", lambda e: "break")

        # ---- 顶部蓝色标题栏 ----
        bar = tk.Frame(root, bg=C_BAR_BG, height=34)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        tk.Label(bar, text=f"📺  {title}", bg=C_BAR_BG, fg=C_BAR_FG,
                 font=("Microsoft YaHei", 10, "bold"),
                 anchor="w").pack(side="left", padx=10)
        tk.Label(bar, text="由主控端控制 · 无法自行关闭",
                 bg=C_BAR_BG, fg=C_TIP_FG,
                 font=("Microsoft YaHei", 8)).pack(side="right", padx=10)

        # ---- 画面区 ----
        self.canvas = tk.Canvas(root, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._tip_id = self.canvas.create_text(
            10, 10, anchor="nw", text="正在连接广播…",
            fill=C_TIP_FG, font=("Microsoft YaHei", 10))

        # ---- 底部状态栏 ----
        self.status = tk.Label(
            root,
            text="拖动窗口边框可调整大小   ·   此窗口只能由主控端结束",
            bg=C_BAR_BG, fg=C_TIP_FG,
            font=("Microsoft YaHei", 8), anchor="w")
        self.status.pack(fill="x", side="bottom")

        # 初始尺寸：先给个默认值，收到首帧后按画面比例调整
        root.geometry("900x560")

        self._frames = queue.Queue(maxsize=2)   # 只保留最新帧
        self._alive = True
        self._started.set()
        self._frame_count = 0
        self._last_fps_t = time.time()
        self._fps = 0.0

        # 起接收线程
        threading.Thread(target=self._recv_loop, args=(host, port),
                         daemon=True, name="广播接收").start()

        # UI 刷新循环（每 33ms 取一次最新帧）
        root.after(33, self._pump)
        try:
            root.mainloop()
        except Exception:
            pass
        self._alive = False

    def _on_close_attempt(self):
        """学生试图关闭：不关，只提示"""
        try:
            self.status.config(
                text="⚠ 广播窗口无法自行关闭，需由主控端结束广播",
                fg="#ffcc80")
            # 2 秒后恢复提示
            self._root.after(2000, lambda: self.status.config(
                text="拖动窗口边框可调整大小   ·   此窗口只能由主控端结束",
                fg=C_TIP_FG))
        except Exception:
            pass

    # ---------- 接收线程 ----------

    def _recv_loop(self, host, port):
        try:
            conn = socket.create_connection((host, int(port)), timeout=8)
            conn.settimeout(8)
            self._conn = conn
        except Exception as e:
            self._last_error = f"连接广播服务失败: {e}"
            print(f"[广播窗口] {self._last_error}")
            self._post_error(self._last_error)
            return

        print(f"[广播窗口] 已连接 {host}:{port}")
        while not self._stop_flag.is_set():
            try:
                data = recv_all(conn, timeout=8)
            except Exception:
                break
            if not data:
                break
            try:
                msg = decode(data)
            except Exception:
                continue

            mtype = msg.get("type")
            if mtype == MSG_BC_QUIT:
                print("[广播窗口] 收到结束指令，关闭")
                self._stop_flag.set()
                break
            if mtype == MSG_BC_FRAME:
                # 只保留最新帧：队列满了就丢掉最旧的
                try:
                    if self._frames.full():
                        try:
                            self._frames.get_nowait()
                        except Exception:
                            pass
                    self._frames.put_nowait(msg)
                except Exception:
                    pass

        try:
            conn.close()
        except Exception:
            pass

        # 连接断了且不是主控端主动结束 → 也关掉窗口
        if not self._stop_flag.is_set():
            print("[广播窗口] 广播连接已断开")
            self._stop_flag.set()
        try:
            if self._root:
                self._root.after(0, self._destroy)
        except Exception:
            pass

    # ---------- UI 刷新 ----------

    def _pump(self):
        """从队列取最新帧显示（主线程/Tk线程执行）"""
        try:
            if self._stop_flag.is_set():
                self._destroy()
                return

            msg = None
            while True:
                try:
                    msg = self._frames.get_nowait()
                except queue.Empty:
                    break

            if msg is not None:
                self._show(msg)

            self._root.after(33, self._pump)
        except Exception:
            pass

    def _show(self, msg):
        if not HAS_PIL:
            self._post_error("缺少 Pillow，无法解码画面")
            return

        try:
            raw = base64.b64decode(msg.get("data", ""))
            img = Image.open(io.BytesIO(raw))
            img.load()
        except Exception as e:
            self._post_error(f"画面解码失败: {e}")
            return

        self._frame_count += 1
        now = time.time()
        if now - self._last_fps_t >= 1.0:
            self._fps = self._frame_count / (now - self._last_fps_t)
            self._frame_count = 0
            self._last_fps_t = now

        try:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw < 10 or ch < 10:
                cw, ch = 900, 500

            # 等比缩放居中显示（保持画面比例，两侧留黑边）
            iw, ih = img.size
            scale = min(cw / iw, ch / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            if (nw, nh) != (iw, ih):
                img = img.resize((nw, nh), Image.BILINEAR)

            tk_img = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(cw // 2, ch // 2,
                                     anchor="center", image=tk_img)
            self._tk_img = tk_img      # 强引用，防 GC 后画面消失

            # 首帧：按画面比例调整窗口（不超过屏幕 80%）
            if not getattr(self, "_sized", False):
                self._sized = True
                self._fit_window(iw, ih)

            self.status.config(
                text=f"{iw}×{ih}   ·   {self._fps:.0f} FPS   ·   "
                     f"拖动边框可调整大小   ·   只能由主控端结束",
                fg=C_TIP_FG)
        except Exception as e:
            self._post_error(f"显示失败: {e}")

    def _fit_window(self, iw, ih):
        """首帧时按画面比例设置窗口大小（不超过屏幕 80%）"""
        try:
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            w, h = iw, ih
            max_w, max_h = int(sw * 0.8), int(sh * 0.8)
            if w > max_w or h > max_h:
                s = min(max_w / w, max_h / h)
                w, h = int(w * s), int(h * s)
            self._root.geometry(f"{w}x{h+70}")   # +70 给标题栏和状态栏
        except Exception:
            pass

    def _post_error(self, text):
        try:
            self.canvas.delete("all")
            self.canvas.create_text(
                10, 10, anchor="nw", text=text,
                fill=C_ERR_FG, font=("Microsoft YaHei", 10))
            self.status.config(text=text, fg=C_ERR_FG)
        except Exception:
            pass


# ---------- 全局单例（同时只有一个广播窗口） ----------
_viewer = None
_v_lock = threading.Lock()


def get_viewer() -> BroadcastViewer:
    global _viewer
    with _v_lock:
        if _viewer is None:
            _viewer = BroadcastViewer()
        return _viewer
