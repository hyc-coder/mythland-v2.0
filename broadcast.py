"""
broadcast.py - 屏幕广播【主控端】(教师机)

方向: 主控端采集自己的屏幕 → 推给所有被控端显示（直播式）

用法:
    from broadcast import BroadcastServer, get_local_ip

    srv = BroadcastServer(port=0, fps=8, width=1280, title="教师机演示")
    port = srv.start()                       # 返回实际监听端口
    # 然后对每个目标 agent 发 make_bc_start_request(get_local_ip(), port, ...)
    srv.client_count()                       # 已连上的学生机数量
    srv.stop()                               # 结束广播（会通知所有客户端关闭窗口）

实现要点:
  1. 采集: mss 抓主显示器 → 等比缩放到指定宽度 → JPEG
     没装 mss/pillow 时降级为占位画面，保证流程仍能跑通
  2. 推流: 一帧编码一次，发给所有已连接的客户端（TCP 单播，可靠不花屏）
  3. 自适应节流: 本帧耗时已超时就不再 sleep，防止延迟累积
  4. 结束: 先给所有客户端发 bc_quit，让它们优雅关窗口，再断连接
"""

import io
import os
import platform
import socket
import threading
import time

from common import (
    encode, send_all,
    make_bc_frame, make_bc_quit,
    BC_DEFAULT_FPS, BC_DEFAULT_WIDTH, BC_DEFAULT_QUALITY, BC_MAX_CLIENTS,
)

IS_WINDOWS = platform.system() == "Windows"

try:
    import mss
    HAS_MSS = True
except Exception:
    mss = None
    HAS_MSS = False

try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    Image = None
    HAS_PIL = False


def get_local_ip(target: str = "8.8.8.8") -> str:
    """
    获取本机局域网 IP（不发包，只是借路由表判断出口网卡）。
    失败时回退 127.0.0.1。
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect((target, 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def capture_screen(max_width: int = BC_DEFAULT_WIDTH,
                   quality: int = BC_DEFAULT_QUALITY):
    """
    采集本机主显示器。
    返回 (jpeg_bytes, width, height)
    """
    # ---- 真实截图 ----
    if HAS_MSS and HAS_PIL:
        try:
            with mss.mss() as sct:
                # monitors[0] 是所有显示器合成，monitors[1] 是主显示器
                idx = 1 if len(sct.monitors) > 1 else 0
                raw = sct.grab(sct.monitors[idx])
                img = Image.frombytes("RGB", raw.size, raw.rgb)
            return _encode(img, max_width, quality)
        except Exception as e:
            print(f"[广播] 截图失败，降级占位: {type(e).__name__}: {e}")

    # ---- 降级：占位画面 ----
    return _placeholder(max_width), max_width, int(max_width * 9 / 16)


def _encode(img, max_width: int, quality: int):
    """等比缩放到宽度上限，再 JPEG 编码"""
    w, h = img.size
    if max_width and w > max_width:
        nh = max(1, int(h * max_width / w))
        img = img.resize((max_width, nh), Image.BILINEAR)
        w, h = max_width, nh
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=False)
    return buf.getvalue(), w, h


def _placeholder(width: int) -> bytes:
    """无截图能力时的占位画面（纯蓝底 + 提示条）"""
    if not HAS_PIL:
        # 连 PIL 都没有：返回最小合法 JPEG（1x1 灰点）
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01"
            b"\x00\x01\x00\x00\xff\xdb\x00C\x00" + b"\x08" * 64 +
            b"\xff\xd9"
        )
    h = int(width * 9 / 16)
    img = Image.new("RGB", (width, h), (21, 101, 192))
    try:
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        d.rectangle([0, h // 2 - 20, width, h // 2 + 20], fill=(255, 255, 255))
    except Exception:
        pass
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=50)
    return buf.getvalue()


class BroadcastServer:
    """主控端广播服务：采集本机屏幕并推给所有连上来的被控端"""

    def __init__(self, port: int = 0, fps: float = BC_DEFAULT_FPS,
                 width: int = BC_DEFAULT_WIDTH, quality: int = BC_DEFAULT_QUALITY,
                 title: str = "屏幕广播"):
        self.requested_port = int(port or 0)
        self.fps = max(1.0, min(float(fps or BC_DEFAULT_FPS), 30.0))
        self.width = int(width or BC_DEFAULT_WIDTH)
        self.quality = int(quality or BC_DEFAULT_QUALITY)
        self.title = title

        self.port = self.requested_port
        self.sock = None
        self.clients = []
        self._clients_lock = threading.Lock()
        self._running = False
        self._seq = 0
        self._threads = []

    # ---------- 生命周期 ----------

    def start(self) -> int:
        """启动监听 + 推流，返回实际监听端口"""
        if self._running:
            return self.port

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # 端口被占则自动顺延（和被控端一致的策略）
        port = self.requested_port or 9100
        for attempt in range(20):
            try:
                self.sock.bind(("", port + attempt))
                self.port = port + attempt
                break
            except OSError:
                continue
        else:
            self.sock.close()
            raise RuntimeError("找不到可用端口用于屏幕广播")

        self.sock.listen(64)
        self.sock.settimeout(0.5)
        self._running = True

        self._spawn(self._accept_loop, "广播-接入")
        self._spawn(self._capture_loop, "广播-采集")
        print(f"[广播] 服务已启动，端口 {self.port}，{self.fps:.0f}FPS")
        return self.port

    def _spawn(self, fn, name):
        t = threading.Thread(target=fn, daemon=True, name=name)
        t.start()
        self._threads.append(t)

    def stop(self):
        """结束广播：通知所有客户端关闭窗口，再断开"""
        if not self._running:
            return
        print(f"[广播] 正在结束，通知 {len(self.clients)} 个客户端")
        self._running = False

        # 1. 先发 quit，让客户端优雅关窗口
        with self._clients_lock:
            clients = list(self.clients)
        for c in clients:
            try:
                c.settimeout(2)
                send_all(c, encode(make_bc_quit()))
            except Exception:
                pass

        # 2. 断开
        for c in clients:
            try:
                c.close()
            except Exception:
                pass
        with self._clients_lock:
            self.clients.clear()

        # 3. 关监听
        try:
            self.sock.close()
        except Exception:
            pass
        print("[广播] 已结束")

    # ---------- 线程 ----------

    def _accept_loop(self):
        """接受被控端连接"""
        while self._running:
            try:
                conn, addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                break

            if not self._running:
                try:
                    conn.close()
                except Exception:
                    pass
                break

            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn.settimeout(5)
            with self._clients_lock:
                if len(self.clients) >= BC_MAX_CLIENTS:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    continue
                self.clients.append(conn)
            print(f"[广播] 客户端接入: {addr}（当前 {len(self.clients)} 台）")

    def _capture_loop(self):
        """采集 + 推流"""
        interval = 1.0 / self.fps
        while self._running:
            t0 = time.time()
            try:
                jpeg, w, h = capture_screen(self.width, self.quality)
                self._seq += 1
                self._push(jpeg, w, h)
            except Exception as e:
                print(f"[广播] 采集异常: {type(e).__name__}: {e}")

            elapsed = time.time() - t0
            remain = interval - elapsed
            if remain > 0:
                # 分片 sleep，便于快速响应 stop()
                step = min(remain, 0.1)
                end = time.time() + remain
                while self._running and time.time() < end:
                    time.sleep(step)

    def _push(self, jpeg: bytes, w: int, h: int):
        """把一帧发给所有客户端；发送失败的（学生机关了）移除"""
        import base64
        data_b64 = base64.b64encode(jpeg).decode("ascii")
        msg = encode(make_bc_frame(w, h, data_b64, self._seq))

        with self._clients_lock:
            clients = list(self.clients)

        dead = []
        for c in clients:
            try:
                send_all(c, msg)
            except Exception:
                dead.append(c)

        if dead:
            with self._clients_lock:
                for c in dead:
                    if c in self.clients:
                        self.clients.remove(c)
                for c in dead:
                    try:
                        c.close()
                    except Exception:
                        pass
            print(f"[广播] 移除 {len(dead)} 个断开的客户端，剩余 {len(self.clients)}")

    # ---------- 状态 ----------

    def client_count(self) -> int:
        with self._clients_lock:
            return len(self.clients)

    def info(self) -> str:
        return (f"{self.fps:.0f}FPS · 宽{self.width}px · "
                f"质量{self.quality} · 已接入 {self.client_count()} 台")
