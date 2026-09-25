"""
controller.py - 控制端（安装在教师/主控机）
功能 (v2 - 极域风格预览墙):
  1. 监听局域网UDP广播，自动发现上线的Agent
  2. 界面以「网格预览墙」排列所有机器卡片（极域电子教室风格）:
       每张卡片 = 屏幕缩略图 + 名称 + IP + 状态指示灯
       自适应窗口宽度排列列数，支持选中高亮、实时刷新缩略图
  3. 顶部工具栏: 刷新 / 自动轮询缩略图 / 控制选中
  4. 支持选中某台机器、双击进入控制
用法:
  python controller.py [--port 9000] [--cols 4] [--thumb-w 160] [--thumb-h 100]
"""

import socket
import threading
import time
import argparse
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import tkinter as tk
from tkinter import ttk, messagebox

from common import (
    encode, decode,
    MSG_HELLO, MSG_HEARTBEAT, MSG_LIST_REQUEST, MSG_LIST_RESPONSE, MSG_BYE,
    MSG_THUMB_REQUEST, MSG_THUMB_RESPONSE, MSG_WHO_IS_THERE,
    MSG_LOG_REQUEST, MSG_LOG_RESPONSE,
    make_heartbeat, make_list_request, make_thumb_request, make_who_is_there,
    make_log_request, make_log_response,
    make_bc_start_request, make_bc_stop_request,
    BC_DEFAULT_FPS, BC_DEFAULT_WIDTH,
    send_all, recv_all,
    b64_decode,
    MULTICAST_GROUP, MULTICAST_PORT, guess_broadcast_addrs,
    setup_headless_logging,
)
import struct
from screen import ScreenCapturer  # 用于把收到的 JPEG 渲染到卡片

# ============ 配置 ============
DEFAULT_PORT = 9000
OFFLINE_TIMEOUT = 15       # 秒，超过此时间没收到心跳则标记为离线
POLL_INTERVAL = 1          # 秒，缩略图刷新间隔 = 1 秒 → 1 FPS
SCAN_PORTS = [9000, 9001, 9002, 9003, 9004, 9005]  # 主动扫描时尝试的端口
SCAN_TIMEOUT = 0.6         # 单个探测连接超时(秒)
SCAN_WORKERS = 100         # 扫描并发线程数
THUMB_W = 176
THUMB_H = 110
CARD_W = THUMB_W + 12      # 188
CARD_H = THUMB_H + 62      # 172（标题18 + 图110 + 信息栏44）
DRAG_THRESHOLD = 8         # 像素，超过此距离才判定为拖拽(否则算点击)
PROBE_INTERVAL = 3         # 秒，控制端主动喊话间隔（零配置发现）

# ============ 蓝色主题配色 ============
C_TITLEBAR     = "#1565c0"   # 标题栏 / 卡片顶部条：主蓝
C_TITLEBAR_FG  = "#e3f2fd"   # 标题栏文字
C_BG           = "#0d47a1"   # 预览墙背景：深蓝
C_APP_BG       = "#f5f9ff"   # 应用整体背景：淡蓝白
C_CARD         = "#1976d2"   # 卡片背景：中蓝
C_CARD_BORDER  = "#0d47a1"   # 卡片边框：深蓝
C_ACCENT       = "#42a5f5"   # 选中高亮：亮蓝
C_DRAG         = "#ffb300"   # 拖拽中：琥珀色（醒目）
C_TEXT         = "#ffffff"   # 卡片文字：白
C_LED_ON       = "#69f0ae"   # 在线指示灯：青绿
C_LED_OFF      = "#78909c"   # 离线指示灯：灰
C_BTN_BG       = "#1565c0"   # 按钮：主蓝
C_BTN_FG       = "#ffffff"   # 按钮文字：白
C_STATUS_BG    = "#e3f2fd"   # 状态栏背景：淡蓝


class Machine:
    """单台机器的状态（v2: 含缩略图二进制 + 版本号驱动刷新）"""

    def __init__(self, mid: str, name: str, os_info: str, ip: str, port: int):
        self.id = mid
        self.name = name
        self.os = os_info
        self.ip = ip
        self.port = port
        self.status = "online"           # online / offline
        self.last_seen = time.time()
        self.thumb: bytes = b""          # 最新缩略图 JPEG
        self.thumb_version = 0           # 每次更新缩略图 +1，UI 据此重绘
        self._thumb_lock = threading.Lock()

    def update_seen(self):
        self.last_seen = time.time()
        if self.status != "online":
            self.status = "online"
            return True  # 状态变化，需要刷新
        return False

    def set_offline(self):
        if self.status != "offline":
            self.status = "offline"
            return True
        return False

    def set_thumb(self, jpeg: bytes):
        with self._thumb_lock:
            self.thumb = jpeg
            self.thumb_version += 1


class PreviewWall:
    """
    极域风格网格预览墙 v4 —— 纯 Canvas 实现（彻底消除抖动）

    为什么重写成纯 Canvas:
      旧版用 Frame + grid 嵌套布局，_relayout() 内部调 update_idletasks()
      会改变子控件尺寸 → 触发 <Configure> → 又调 _relayout() → 无限循环；
      再叠加 1FPS 缩略图刷新，表现为卡片持续抖动、拖不动、来不及渲染。

      纯 Canvas 方案: 每张卡片只是若干 Canvas item。
        - 刷新缩略图 → itemconfig(image=...)   只换像素，不改尺寸
        - 移动/重排卡片 → coords()              只改坐标，不改 Canvas 尺寸
      两者都不会触发 <Configure> → 从根上杜绝抖动。

    特性:
      - 蓝色主题
      - 卡片可拖拽排序（跟手移动 + 琥珀色高亮）
      - 自适应列数
      - 单击选中(亮蓝边框)、双击进入控制
    """

    GAP = 10   # 卡片间距

    def __init__(self, master: tk.Tk, controller: "Controller"):
        self.master = master
        self.controller = controller
        self.selected_id: str | None = None
        self.order: list[str] = []          # 自定义排列顺序
        self.cards: dict[str, dict] = {}    # mid -> item id 集合（保持旧字段名兼容）
        self._rects: dict[str, tuple] = {}  # mid -> (x1, y1, x2, y2)
        self._photos: dict[str, object] = {}  # mid -> PhotoImage（防 GC，关键）
        self._placeholder = self._make_placeholder()

        # 拖拽状态
        self._drag_mid = None
        self._drag_start = (0, 0)
        self._dragging = False
        self._drag_dx = 0
        self._drag_dy = 0
        # 自由定位: mid -> (x, y)。被拖过的卡片记在这里，之后就固定在该坐标，
        # 不再参与网格自动排列（实现"任意拖动"，而非仅排序）。
        self._free_pos: dict[str, tuple] = {}
        # 画布逻辑尺寸（拖到远处时自动扩大，配合滚动条可达）
        self._canvas_w = 0
        self._canvas_h = 0

        # Canvas（唯一的容器，不再有嵌套 Frame）
        self.canvas = tk.Canvas(master, highlightthickness=0, bg=C_BG)
        self.scrollbar = ttk.Scrollbar(master, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        # 只监听窗口尺寸变化（改 item 坐标不会触发它，故无循环）
        self.canvas.bind("<Configure>", lambda e: self.layout())
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-1>", self._on_double)

    # ---------- 占位图 ----------

    def _make_placeholder(self) -> bytes:
        try:
            cap = ScreenCapturer("无信号")
            return cap.capture_jpeg(THUMB_W, THUMB_H)
        except Exception:
            return b""

    # ---------- 对外接口 ----------

    def full_redraw(self, machines: list[Machine]):
        """整体重绘：同步 order、创建/销毁卡片、刷新内容、重排"""
        current_ids = {m.id for m in machines}

        # 清理已消失的
        for mid in list(self.cards.keys()):
            if mid not in current_ids:
                self._destroy_card(mid)
        self.order = [mid for mid in self.order if mid in current_ids]

        # 新增的（追加到 order 末尾）
        for m in machines:
            if m.id not in self.cards:
                self._create_card(m)
            if m.id not in self.order:
                self.order.append(m.id)

        for m in machines:
            self._update_card(m)
        self.layout()

    def update_one(self, mid: str):
        """
        1FPS 缩略图刷新：只 itemconfig 换图片，绝不动布局。
        这是"不再抖动"的关键路径。
        """
        with self.controller.lock:
            m = self.controller.machines.get(mid)
        if not m:
            return
        if mid not in self.cards:
            self._create_card(m)
            if mid not in self.order:
                self.order.append(mid)
            self._update_card(m)
            self.layout()
            return
        self._update_card(m)   # 只换图 + 状态，不 layout

    # ---------- 卡片创建/销毁 ----------

    def _create_card(self, m: Machine):
        c = self.canvas
        items = {}
        # 边框（最底）
        items["border"] = c.create_rectangle(0, 0, 0, 0, fill=C_CARD,
                                             outline=C_CARD_BORDER, width=2)
        # 标题条（拖拽把手）
        items["title"] = c.create_rectangle(0, 0, 0, 0, fill=C_TITLEBAR, outline="")
        items["grip"] = c.create_text(0, 0, text="⋮⋮", fill=C_TITLEBAR_FG,
                                      font=("Microsoft YaHei", 7), anchor="w")
        # 缩略图
        items["img"] = c.create_image(0, 0, anchor="nw")
        # 状态指示灯
        items["dot"] = c.create_oval(0, 0, 0, 0, fill=C_LED_ON, outline="")
        # 名称 / IP
        items["name"] = c.create_text(0, 0, text=m.name, fill=C_TEXT,
                                      font=("Microsoft YaHei", 8, "bold"), anchor="nw")
        items["ip"] = c.create_text(0, 0, text=m.ip, fill="#bbdefb",
                                    font=("Microsoft YaHei", 7), anchor="nw")
        self.cards[m.id] = items

    def _destroy_card(self, mid: str):
        items = self.cards.pop(mid, None)
        if items:
            for iid in items.values():
                try:
                    self.canvas.delete(iid)
                except Exception:
                    pass
        self._rects.pop(mid, None)
        self._photos.pop(mid, None)
        if mid in self.order:
            self.order.remove(mid)
        if self.selected_id == mid:
            self.selected_id = None

    # ---------- 内容更新 ----------

    def _update_card(self, m: Machine):
        items = self.cards.get(m.id)
        if not items:
            return
        c = self.canvas
        # 缩略图（1FPS 走这里：只 itemconfig，不动布局）
        jpeg = m.thumb or self._placeholder
        if jpeg:
            self._set_thumb(m.id, items, jpeg)
        # 文本
        c.itemconfig(items["name"], text=m.name)
        c.itemconfig(items["ip"], text=m.ip)
        # 指示灯
        c.itemconfig(items["dot"], fill=C_LED_ON if m.status == "online" else C_LED_OFF)
        # 边框颜色：拖拽中 > 选中 > 普通
        if self._dragging and self._drag_mid == m.id:
            bc, bw = C_DRAG, 4
        elif self.selected_id == m.id:
            bc, bw = C_ACCENT, 3
        else:
            bc, bw = C_CARD_BORDER, 2
        c.itemconfig(items["border"], outline=bc, width=bw)

    def _set_thumb(self, mid: str, items: dict, jpeg: bytes):
        try:
            from PIL import Image, ImageTk
            import io as _io
            img = Image.open(_io.BytesIO(jpeg))
            if img.size != (THUMB_W, THUMB_H):
                img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.canvas.itemconfig(items["img"], image=photo)
            self._photos[mid] = photo        # 防 GC（关键！）
            if not getattr(self, "_ok_logged", False):
                self._ok_logged = True
                print(f"[预览墙] 缩略图渲染成功: {img.size}")
        except Exception as e:
            if not getattr(self, "_err_logged", False):
                self._err_logged = True
                print(f"[预览墙] 缩略图渲染失败: {type(e).__name__}: {e}")
                print("          需要 Pillow，请执行: python -m pip install pillow")

    # ---------- 布局（只改坐标，不触发 Configure） ----------

    def layout(self):
        # 防重入: configure(scrollregion=...) 本身可能触发 canvas 的 <Configure>，
        # 若不加保护会形成 layout -> Configure -> layout 的循环（表现为抖动）。
        if getattr(self, "_layouting", False):
            return
        self._layouting = True
        try:
            self._do_layout()
        finally:
            self._layouting = False

    def _do_layout(self):
        c = self.canvas
        cw = c.winfo_width()
        if cw <= 1:
            cw = 900
        cols = max(1, (cw - self.GAP) // (CARD_W + self.GAP))
        used = cols * CARD_W + (cols - 1) * self.GAP
        offset_x = max(self.GAP, (cw - used) // 2)

        # 未被拖动的卡片按 order 依次占用网格槽位
        grid_slots = [mid for mid in self.order if mid not in self._free_pos]
        slot_of = {mid: i for i, mid in enumerate(grid_slots)}

        max_x, max_y = cw, c.winfo_height() or 600

        for mid in self.order:
            items = self.cards.get(mid)
            if not items:
                continue
            if mid in self._free_pos:
                # 自由定位：用用户拖到的绝对坐标
                x, y = self._free_pos[mid]
            else:
                idx = slot_of[mid]
                r, col = idx // cols, idx % cols
                x = offset_x + col * (CARD_W + self.GAP)
                y = self.GAP + r * (CARD_H + self.GAP)
            self._place_items(mid, items, x, y)
            max_x = max(max_x, x + CARD_W + self.GAP)
            max_y = max(max_y, y + CARD_H + self.GAP)

        # 滚动区域：需覆盖所有卡片（含被拖到远处的），否则拖出去就滚不到
        new_sr = (0, 0, max(cw, max_x), max(c.winfo_height() or 600, max_y))
        if getattr(self, "_last_sr", None) != new_sr:
            self._last_sr = new_sr
            c.configure(scrollregion=new_sr)

    def _place_items(self, mid: str, items: dict, x: int, y: int):
        """把一张卡片的所有 item 摆到 (x, y)"""
        c = self.canvas
        c.coords(items["border"], x, y, x + CARD_W, y + CARD_H)
        c.coords(items["title"], x + 2, y + 2, x + CARD_W - 2, y + 20)
        c.coords(items["grip"], x + 7, y + 11)
        c.coords(items["img"], x + (CARD_W - THUMB_W) // 2, y + 26)
        dy = y + 26 + THUMB_H + 10
        c.coords(items["dot"], x + 10, dy, x + 20, dy + 10)
        c.coords(items["name"], x + 26, dy - 2)
        c.coords(items["ip"], x + 26, dy + 13)
        # 层级：border 是【填充】矩形，必须在最底层，否则会盖住图片 → 显示成纯色方块
        c.tag_lower(items["border"])
        c.tag_raise(items["img"])
        c.tag_raise(items["dot"])
        c.tag_raise(items["name"])
        c.tag_raise(items["ip"])
        c.tag_raise(items["title"])
        c.tag_raise(items["grip"])
        self._rects[mid] = (x, y, x + CARD_W, y + CARD_H)

    # ---------- 交互：选中 / 双击 ----------

    def _hit_test(self, cx: int, cy: int) -> str | None:
        """判断画布坐标落在哪张卡片上"""
        for mid, (x1, y1, x2, y2) in self._rects.items():
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                return mid
        return None

    def _on_press(self, event):
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        mid = self._hit_test(cx, cy)
        if not mid:
            return
        self._drag_mid = mid
        self._dragging = False
        self._drag_start = (event.x_root, event.y_root)
        x1, y1, _, _ = self._rects[mid]
        self._drag_dx = cx - x1      # 抓取点相对卡片左上角
        self._drag_dy = cy - y1
        self._select(mid)

    def _on_motion(self, event):
        if not self._drag_mid:
            return
        dx = event.x_root - self._drag_start[0]
        dy = event.y_root - self._drag_start[1]
        if not self._dragging:
            if abs(dx) <= DRAG_THRESHOLD and abs(dy) <= DRAG_THRESHOLD:
                return
            self._dragging = True
            # 拖拽中：琥珀色高亮 + 置顶
            items = self.cards[self._drag_mid]
            self.canvas.itemconfig(items["border"], outline=C_DRAG, width=4)
            for iid in items.values():
                self.canvas.tag_raise(iid)

        # 跟手移动
        cx = self.canvas.canvasx(event.x) - self._drag_dx
        cy = self.canvas.canvasy(event.y) - self._drag_dy
        items = self.cards[self._drag_mid]
        self._place_items(self._drag_mid, items, cx, cy)

    def _on_release(self, event):
        mid = self._drag_mid
        if not mid:
            return
        try:
            if self._dragging:
                # 自由定位：卡片就停在当前拖到的绝对坐标，不吸附、不交换
                cx = self.canvas.canvasx(event.x) - self._drag_dx
                cy = self.canvas.canvasy(event.y) - self._drag_dy
                cx = max(0, cx)      # 不允许拖到负坐标（否则滚不到）
                cy = max(0, cy)
                self._free_pos[mid] = (cx, cy)
                print(f"[预览墙] {mid[:8]} 自由定位于 ({int(cx)}, {int(cy)})")
        except Exception as e:
            print(f"[预览墙] 拖拽异常: {e}")
        finally:
            self._dragging = False
            self._drag_mid = None
            self._last_sr = None     # 强制重算滚动区域（卡片可能到了新边界）
            self.layout()

    def arrange_grid(self):
        """整理排列：清除所有自由位置，卡片回到自动网格"""
        n = len(self._free_pos)
        self._free_pos.clear()
        self._last_sr = None
        self.layout()
        print(f"[预览墙] 已整理排列（{n} 张卡片回到网格）")
        return n

    def _on_double(self, event):
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        mid = self._hit_test(cx, cy)
        if mid:
            self.controller.control_selected(mid)

    def _select(self, mid: str):
        if self.selected_id == mid:
            return
        old = self.selected_id
        self.selected_id = mid
        for cid in (old, mid):
            if cid:
                m = self.controller.machines.get(cid)
                if m:
                    self._update_card(m)
        self.controller.on_selection_changed(mid)

    def get_selected(self) -> str | None:
        return self.selected_id


def get_local_ip() -> str:
    """获取本机在局域网中的 IP（用于推算网段）"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def probe_host(ip: str, port: int, timeout: float = SCAN_TIMEOUT) -> dict | None:
    """
    TCP 直连探测: 连上后发 list_req 取回机器信息(含缩略图)。
    这是不依赖 UDP 广播的主动发现方式，可绕过防火墙对广播的拦截。
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        sock.sendall(encode(make_list_request()))
        header = sock.recv(4)
        if not header:
            sock.close()
            return None
        length = int.from_bytes(header, "big")
        payload = b""
        while len(payload) < length:
            chunk = sock.recv(length - len(payload))
            if not chunk:
                break
            payload += chunk
        sock.close()
        resp = decode(header + payload)
        if resp.get("type") == MSG_LIST_RESPONSE and resp.get("machines"):
            info = dict(resp["machines"][0])
            info["_ip"] = ip
            info["_port"] = port
            return info
    except Exception:
        pass
    return None


class Controller:
    def __init__(self, port: int, root: tk.Tk, cols: int = 0):
        self.port = port
        self.root = root
        self.machines: dict[str, Machine] = {}  # id -> Machine
        self.lock = threading.Lock()
        self.running = True
        self.polling = True  # 是否自动轮询缩略图
        self._fetching = set()  # 正在拉取缩略图的机器 id（并发保护）
        # 零配置: 主动喊话的目标地址（组播 + 网段广播 + 受限广播）
        self.probe_targets = guess_broadcast_addrs()

        # UDP 监听socket（接收Agent通告，含组播）
        # 关键: 必须绑定【发现端口 MULTICAST_PORT=9086】，与 agent 的广播目标端口一致。
        # 若绑成 self.port(9000) 就收不到 agent 发到 9086 的 hello。
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.udp_socket.bind(("", MULTICAST_PORT))
        except Exception:
            try:
                self.udp_socket.bind(("0.0.0.0", MULTICAST_PORT))
            except Exception:
                self.udp_socket.bind(("", port))
        # 加入组播组，接收 agent 的组播通告
        try:
            mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
            self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except Exception:
            pass

        self._build_ui()
        threading.Thread(target=self.listen_broadcast, daemon=True).start()
        threading.Thread(target=self.check_offline_loop, daemon=True).start()
        threading.Thread(target=self.discovery_probe_loop, daemon=True).start()
        threading.Thread(target=self.thumb_poll_loop, daemon=True).start()
        threading.Thread(target=self.reconcile_loop, daemon=True).start()  # 自愈保险

    # ---------- UI ----------
    def _build_ui(self):
        self.root.title("局域网远控 - 控制端 (预览墙)")
        self.root.geometry("1120x700")
        self.root.configure(bg=C_TITLEBAR)

        # ===== 蓝色标题栏 =====
        title_bar = tk.Frame(self.root, bg=C_TITLEBAR, height=40)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="🖥️  局域网远控 · 控制端",
                 bg=C_TITLEBAR, fg=C_TITLEBAR_FG,
                 font=("Microsoft YaHei", 13, "bold")).pack(side="left", padx=14)
        # 标题栏右侧提示
        tk.Label(title_bar, text="卡片可拖拽排序 · 1 FPS 实时画面",
                 bg=C_TITLEBAR, fg="#bbdefb",
                 font=("Microsoft YaHei", 8)).pack(side="right", padx=14)

        # ===== 工具栏（浅蓝底 + 蓝色按钮） =====
        toolbar = tk.Frame(self.root, bg=C_APP_BG, height=44)
        toolbar.pack(fill="x", padx=0, pady=0)
        toolbar.pack_propagate(False)

        def blue_btn(parent, text, cmd):
            b = tk.Button(parent, text=text, command=cmd,
                          bg=C_BTN_BG, fg=C_BTN_FG,
                          activebackground=C_ACCENT, activeforeground=C_BTN_FG,
                          relief="flat", bd=0, padx=12, pady=5,
                          font=("Microsoft YaHei", 9), cursor="hand2")
            return b

        blue_btn(toolbar, "刷新列表", self.refresh_list).pack(side="left", padx=(10, 4), pady=8)
        self.scan_btn = blue_btn(toolbar, "扫描网段", self.scan_network)
        self.scan_btn.pack(side="left", padx=4, pady=8)
        self.poll_btn = blue_btn(toolbar, "停止轮询", self.toggle_poll)
        self.poll_btn.pack(side="left", padx=4, pady=8)
        blue_btn(toolbar, "整理排列", self.arrange_wall).pack(side="left", padx=4, pady=8)
        blue_btn(toolbar, "控制选中", lambda: self.control_selected()).pack(side="left", padx=4, pady=8)
        self.bc_btn = blue_btn(toolbar, "屏幕广播", self.toggle_broadcast)
        self.bc_btn.pack(side="left", padx=4, pady=8)
        blue_btn(toolbar, "一键部署", self.open_deploy).pack(
            side="left", padx=4, pady=8)
        blue_btn(toolbar, "关于软件", self.open_about).pack(
            side="left", padx=4, pady=8)

        # 状态标签（右侧，淡蓝底）
        self.status_label = tk.Label(toolbar, text="等待发现机器...",
                                     bg=C_STATUS_BG, fg=C_TITLEBAR,
                                     font=("Microsoft YaHei", 9, "bold"),
                                     padx=10, pady=3)
        self.status_label.pack(side="right", padx=10)

        # ===== 预览墙 =====
        self.wall = PreviewWall(self.root, self)

        self._refresh_ui()

    def _refresh_ui(self):
        with self.lock:
            items = list(self.machines.values())
        self.wall.full_redraw(items)
        online_count = sum(1 for m in items if m.status == "online")
        self.status_label.config(text=f"在线 {online_count} / {len(items)}")

    # ---------- 网络：接收广播 ----------
    def listen_broadcast(self):
        print(f"[Controller] 开始监听发现端口 {MULTICAST_PORT} (收 agent 上线通告)")
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(65535)
                msg = decode(data)
                if msg.get("type") == "hello":
                    self.add_or_update_machine(msg, addr)
            except Exception as e:
                if self.running:
                    print(f"[Controller] 接收广播异常: {e}")

    def discovery_probe_loop(self):
        """
        零配置核心：控制端主动"喊话"。
        即使 agent 的通告被防火墙拦掉，控制端主动问一句，
        agent 收到 who_is_there 会立即回 hello，从而被发现。
        """
        time.sleep(0.5)  # 等 UI 起来
        while self.running:
            try:
                self._shout()
            except Exception:
                pass
            time.sleep(PROBE_INTERVAL)

    def _shout(self):
        """
        向所有候选地址喊一嗓子：谁在线？
        发往【独立发现端口 MULTICAST_PORT】，与 agent 的监听端口分离，
        避免单机演示时端口冲突。
        """
        data = encode(make_who_is_there())
        for tgt in self.probe_targets:
            try:
                self.udp_socket.sendto(data, (tgt, MULTICAST_PORT))
            except Exception:
                pass

    def add_or_update_machine(self, msg: dict, addr):
        """发现新机器或更新已有机器（v2: 解析缩略图）"""
        mid = msg.get("id") or f"{addr[0]}:{msg.get('port', self.port)}"
        name = msg.get("name", "未知")
        os_info = msg.get("os", "未知")
        ip = addr[0]
        port = msg.get("port", self.port)
        thumb_b64 = msg.get("thumb", "")

        with self.lock:
            is_new = mid not in self.machines
            machine = self.machines.setdefault(mid, Machine(mid, name, os_info, ip, port))
            machine.name = name
            machine.os = os_info
            machine.ip = ip
            machine.port = port
            machine.update_seen()
            if thumb_b64:
                try:
                    machine.set_thumb(b64_decode(thumb_b64))
                except Exception:
                    pass

        if is_new:
            print(f"[Controller] 发现新机器: {name} @ {ip}")
            # 新机器: 整表重绘(保证创建卡片 + 更新计数 + 正确排序)
            # 必须用 lambda 默认参数绑定 mid，避免闭包陷阱
            self.root.after(0, lambda mid=mid: self._refresh_ui_and_scroll(mid))
            # 立即拉一帧缩略图，不等 poll 循环（首帧秒出，不必等 1 秒）
            threading.Thread(target=self._fetch_thumb, args=(machine,), daemon=True).start()
        else:
            # 已有机器: 增量刷新缩略图即可
            self.root.after(0, lambda mid=mid: self.wall.update_one(mid))
            self.root.after(0, self._update_status_count)

    def _refresh_ui_and_scroll(self, mid: str):
        """整表重绘后，确保新卡片可见（更新滚动区域）"""
        self._refresh_ui()
        self.wall.update_one(mid)

    def arrange_wall(self):
        """「整理排列」按钮：把自由拖动的卡片收回自动网格"""
        n = self.wall.arrange_grid()
        if n:
            self.status_label.config(text=f"已整理 {n} 张卡片回网格")
            self.root.after(1500, self._update_status_count)
        else:
            messagebox.showinfo("整理排列", "卡片都在网格中，无需整理")

    def _update_status_count(self):
        """只更新右上角'在线 x / y'计数，不重绘整表"""
        with self.lock:
            items = list(self.machines.values())
        online_count = sum(1 for m in items if m.status == "online")
        self.status_label.config(text=f"在线 {online_count} / {len(items)}")

    # ---------- 操作：刷新 / 轮询 / 控制 ----------

    def scan_network(self):
        """
        主动 TCP 扫描网段发现被控端。
        不依赖 UDP 广播 —— 当防火墙拦截广播导致"在线 0/0"时，用它兜底。
        """
        local_ip = get_local_ip()
        base = ".".join(local_ip.split(".")[:3]) + "."
        self.scan_btn.config(state="disabled", text="扫描中...")
        self.status_label.config(text=f"扫描 {base}1~254 ...")

        def worker():
            targets = [(f"{base}{i}", p) for i in range(1, 255) for p in SCAN_PORTS]
            found = []

            def probe(t):
                return probe_host(t[0], t[1])

            try:
                with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
                    for r in ex.map(probe, targets):
                        if r:
                            found.append(r)
            except Exception as e:
                print(f"[Controller] 扫描异常: {e}")

            # 合并进 machines
            added = 0
            for info in found:
                mid = info.get("id") or f"{info['_ip']}:{info['_port']}"
                with self.lock:
                    m = self.machines.setdefault(
                        mid, Machine(mid, info.get("name", "未知"),
                                     info.get("os", "未知"),
                                     info["_ip"], info["_port"])
                    )
                    m.name = info.get("name", m.name)
                    m.os = info.get("os", m.os)
                    m.ip = info["_ip"]
                    m.port = info["_port"]
                    m.update_seen()
                    if info.get("thumb"):
                        try:
                            m.set_thumb(b64_decode(info["thumb"]))
                        except Exception:
                            pass
                    added += 1

            def done():
                self.scan_btn.config(state="normal", text="扫描网段")
                self._refresh_ui()
                if added:
                    messagebox.showinfo("扫描完成", f"发现 {added} 台被控端")
                else:
                    messagebox.showwarning(
                        "扫描完成",
                        f"未发现被控端\n"
                        f"(扫描了 {base}1~254 的端口 {SCAN_PORTS[0]}~{SCAN_PORTS[-1]})\n\n"
                        f"确认:\n1. agent.py 是否在运行\n"
                        f"2. 防火墙是否允许 Python 入站连接"
                    )

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def refresh_list(self):
        self.ping_all()
        messagebox.showinfo("刷新", "已向所有机器发送状态查询")

    def toggle_poll(self):
        self.polling = not self.polling
        self.poll_btn.config(text="停止轮询" if self.polling else "开始轮询")

    def ping_all(self):
        with self.lock:
            targets = list(self.machines.values())
        for m in targets:
            threading.Thread(target=self._ping_one, args=(m,), daemon=True).start()

    def _ping_one(self, machine: Machine):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((machine.ip, machine.port))
            sock.sendall(encode(make_heartbeat()))
            header = self._recv_exact(sock, 4)
            if header:
                length = int.from_bytes(header, "big")
                self._recv_exact(sock, length)
                with self.lock:
                    changed = machine.update_seen()
                if changed:
                    self.root.after(0, self._refresh_ui)
            sock.close()
        except Exception:
            pass

    def thumb_poll_loop(self):
        """周期性向所有在线机器请求最新缩略图，驱动预览墙 1FPS 刷新"""
        while self.running:
            if self.polling:
                with self.lock:
                    targets = [m for m in self.machines.values() if m.status == "online"]
                for m in targets:
                    # 并发保护: 该机器上一帧还没回来就跳过，避免线程堆积
                    if m.id in self._fetching:
                        continue
                    self._fetching.add(m.id)
                    threading.Thread(target=self._fetch_thumb, args=(m,), daemon=True).start()
            time.sleep(POLL_INTERVAL)

    def fetch_agent_log(self, machine: Machine, lines: int = 200) -> str:
        """
        远程读取被控端的 agent.log（末尾 N 行）。
        控制端「查看日志」调用。失败时返回带原因的文本，不抛异常。
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((machine.ip, machine.port))
            sock.sendall(encode(make_log_request(lines)))
            header = self._recv_exact(sock, 4)
            if not header:
                sock.close()
                return "(被控端无响应)"
            length = int.from_bytes(header, "big")
            payload = self._recv_all(sock, length)
            sock.close()
            resp = decode(header + payload)
            if resp.get("type") == MSG_LOG_RESPONSE:
                content = resp.get("log", "")
                path = resp.get("path", "")
                return content or f"(被控端日志为空)\n路径: {path}"
            return f"(未知响应: {resp.get('type')})"
        except Exception as e:
            return f"(读取失败: {type(e).__name__}: {e})\n" \
                   f"目标: {machine.ip}:{machine.port}"

    def _fetch_thumb(self, machine: Machine):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((machine.ip, machine.port))
            sock.sendall(encode(make_thumb_request(THUMB_W, THUMB_H)))
            header = self._recv_exact(sock, 4)
            if not header:
                sock.close()
                return
            length = int.from_bytes(header, "big")
            payload = self._recv_all(sock, length)
            sock.close()
            resp = decode(header + payload)
            if resp.get("type") == MSG_THUMB_RESPONSE and resp.get("thumb"):
                jpeg = b64_decode(resp["thumb"])
                machine.set_thumb(jpeg)
                self.root.after(0, lambda mid=machine.id: self.wall.update_one(mid))
                if not getattr(self, "_thumb_rx_logged", False):
                    self._thumb_rx_logged = True
                    print(f"[Controller] 已收到首帧缩略图: {machine.name} ({len(jpeg)} bytes)")
        except Exception as e:
            # 只在第一次报错时提示，避免刷屏
            key = f"_thumb_rx_err_{machine.id}"
            if not getattr(self, key, False):
                setattr(self, key, True)
                print(f"[Controller] 拉取 {machine.name} 缩略图失败: {type(e).__name__}: {e}")
                print(f"          目标 {machine.ip}:{machine.port}")
        finally:
            self._fetching.discard(machine.id)

    def reconcile_loop(self):
        """
        对账循环(自愈保险): 每 4 秒检查 machines 与 cards 是否一致。
        只要发现"有机器但没卡片"，就整表重绘。
        这样即使某条更新路径出意外，卡片也最多延迟几秒出现，
        绝不会出现"日志说发现了、界面却空白"。
        """
        while self.running:
            time.sleep(4)
            try:
                with self.lock:
                    machine_ids = set(self.machines.keys())
                card_ids = set(self.wall.cards.keys())
                if machine_ids != card_ids:
                    missing = machine_ids - card_ids
                    print(f"[Controller] 对账: 补齐 {len(missing)} 张缺失卡片")
                    self.root.after(0, self._refresh_ui)
                else:
                    # 一致时也刷新一下右上角计数
                    self.root.after(0, self._update_status_count)
            except Exception as e:
                print(f"[Controller] 对账异常: {e}")

    def check_offline_loop(self):
        """定期检查超时机器，标记为离线"""
        while self.running:
            time.sleep(3)
            changed = False
            with self.lock:
                for m in self.machines.values():
                    if m.status == "online" and (time.time() - m.last_seen) > OFFLINE_TIMEOUT:
                        if m.set_offline():
                            changed = True
            if changed:
                self.root.after(0, self._refresh_ui)

    # ---------- 关于软件 ----------

    def open_about(self):
        """「关于软件」按钮：免责声明 + 作者"""
        try:
            from about import open_about_dialog
            open_about_dialog(self.root)
        except Exception as e:
            messagebox.showerror("关于软件", f"无法打开窗口: {e}",
                                 parent=self.root)

    # ---------- 一键部署 ----------

    def open_deploy(self):
        """「一键部署」按钮：把被控端 exe 批量装到指定 IP 的电脑"""
        try:
            from deploy_ui import open_deploy_dialog
            open_deploy_dialog(self.root)
        except Exception as e:
            messagebox.showerror("一键部署", f"无法打开部署窗口: {e}",
                                 parent=self.root)

    # ---------- 屏幕广播（主控端 → 所有被控端，直播式） ----------

    def _send_req(self, m, msg, timeout: float = 8.0):
        """给一台机器发消息并等响应；失败抛异常"""
        s = socket.create_connection((m.ip, m.port), timeout=timeout)
        s.settimeout(timeout)
        try:
            send_all(s, encode(msg))
            data = recv_all(s, timeout=timeout)
        finally:
            try:
                s.close()
            except Exception:
                pass
        return decode(data) if data else None

    def toggle_broadcast(self):
        """「屏幕广播」按钮：未广播 → 弹配置启动；广播中 → 结束"""
        if getattr(self, "bc_server", None) is not None:
            self.stop_broadcast()
        else:
            self.broadcast_dialog()

    def broadcast_dialog(self):
        """配置并启动屏幕广播"""
        with self.lock:
            online = [m for m in self.machines.values() if m.status == "online"]
        if not online:
            messagebox.showinfo("屏幕广播", "当前没有在线的被控端。",
                                parent=self.root)
            return

        sel = self.wall.get_selected() if hasattr(self, "wall") else None
        sel_machine = self.machines.get(sel) if sel else None

        dlg = tk.Toplevel(self.root)
        dlg.title("屏幕广播（把本机屏幕直播给被控端）")
        dlg.configure(bg=C_APP_BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        try:
            self.root.update_idletasks()
            px = self.root.winfo_x() + (self.root.winfo_width() - 460) // 2
            py = self.root.winfo_y() + (self.root.winfo_height() - 330) // 2
            dlg.geometry(f"460x330+{max(0, px)}+{max(0, py)}")
        except Exception:
            dlg.geometry("460x330")

        tk.Label(dlg, text="把本机的屏幕广播给被控端", bg=C_APP_BG,
                 fg=C_TITLEBAR, font=("Microsoft YaHei", 10, "bold")).pack(
            pady=(12, 8))

        # 标题
        r1 = tk.Frame(dlg, bg=C_APP_BG)
        r1.pack(fill="x", padx=16, pady=4)
        tk.Label(r1, text="标题:", bg=C_APP_BG, fg=C_TITLEBAR,
                 font=("Microsoft YaHei", 9), width=7,
                 anchor="w").pack(side="left")
        title_var = tk.StringVar(value="教师机演示")
        tk.Entry(r1, textvariable=title_var,
                 font=("Microsoft YaHei", 9), relief="solid",
                 bd=1).pack(side="left", fill="x", expand=True)

        # 帧率
        r2 = tk.Frame(dlg, bg=C_APP_BG)
        r2.pack(fill="x", padx=16, pady=4)
        tk.Label(r2, text="帧率:", bg=C_APP_BG, fg=C_TITLEBAR,
                 font=("Microsoft YaHei", 9), width=7,
                 anchor="w").pack(side="left")
        fps_var = tk.StringVar(value=str(int(BC_DEFAULT_FPS)))
        tk.Spinbox(r2, from_=1, to=30, width=6, textvariable=fps_var,
                   font=("Microsoft YaHei", 9)).pack(side="left")
        tk.Label(r2, text="FPS（教学演示 6~10 就够，越高越吃带宽）",
                 bg=C_APP_BG, fg="#90a4ae",
                 font=("Microsoft YaHei", 8)).pack(side="left", padx=6)

        # 画面宽度
        r3 = tk.Frame(dlg, bg=C_APP_BG)
        r3.pack(fill="x", padx=16, pady=4)
        tk.Label(r3, text="画面宽:", bg=C_APP_BG, fg=C_TITLEBAR,
                 font=("Microsoft YaHei", 9), width=7,
                 anchor="w").pack(side="left")
        w_var = tk.StringVar(value=str(BC_DEFAULT_WIDTH))
        tk.Spinbox(r3, from_=640, to=1920, width=6, textvariable=w_var,
                   font=("Microsoft YaHei", 9)).pack(side="left")
        tk.Label(r3, text="px（等比缩放，越小越省带宽）", bg=C_APP_BG,
                 fg="#90a4ae", font=("Microsoft YaHei", 8)).pack(
            side="left", padx=6)

        # 广播范围
        r4 = tk.Frame(dlg, bg=C_APP_BG)
        r4.pack(fill="x", padx=16, pady=(8, 2))
        tk.Label(r4, text="范围:", bg=C_APP_BG, fg=C_TITLEBAR,
                 font=("Microsoft YaHei", 9), width=7,
                 anchor="w").pack(side="left")
        scope_var = tk.StringVar(value="all")
        tk.Radiobutton(r4, text=f"全部在线（{len(online)} 台）",
                       variable=scope_var, value="all", bg=C_APP_BG,
                       font=("Microsoft YaHei", 9),
                       activebackground=C_APP_BG,
                       selectcolor=C_APP_BG).pack(side="left")
        sel_label = (f"仅选中（{sel_machine.name}）" if sel_machine
                     else "仅选中（未选机器）")
        rb_sel = tk.Radiobutton(r4, text=sel_label, variable=scope_var,
                                value="sel", bg=C_APP_BG,
                                font=("Microsoft YaHei", 9),
                                activebackground=C_APP_BG,
                                selectcolor=C_APP_BG)
        rb_sel.pack(side="left", padx=(8, 0))
        if not sel_machine:
            rb_sel.config(state="disabled")

        # 说明
        tk.Label(dlg,
                 text="被控端会弹出广播窗口：可调整大小，但无法自行关闭，\n"
                      "只能由主控端点「结束广播」关闭。",
                 bg=C_APP_BG, fg="#90a4ae", font=("Microsoft YaHei", 8),
                 justify="left").pack(pady=(10, 4))

        # 按钮
        br = tk.Frame(dlg, bg=C_APP_BG)
        br.pack(pady=10)
        result = {"go": False}

        def _ok():
            result["go"] = True
            dlg.destroy()

        def _cancel():
            result["go"] = False
            dlg.destroy()

        tk.Button(br, text="开始广播", command=_ok, bg=C_TITLEBAR, fg="white",
                  relief="flat", bd=0, padx=22, pady=5,
                  font=("Microsoft YaHei", 9),
                  cursor="hand2").pack(side="left", padx=6)
        tk.Button(br, text="取消", command=_cancel, bg="#e3f2fd", fg=C_TITLEBAR,
                  relief="flat", bd=0, padx=22, pady=5,
                  font=("Microsoft YaHei", 9),
                  cursor="hand2").pack(side="left", padx=6)

        dlg.wait_window()
        if not result["go"]:
            return

        # 收集目标
        if scope_var.get() == "sel" and sel_machine:
            targets = [sel_machine]
        else:
            targets = online

        try:
            fps = float(fps_var.get())
            width = int(w_var.get())
        except Exception:
            fps, width = BC_DEFAULT_FPS, BC_DEFAULT_WIDTH

        self._launch_broadcast(title_var.get().strip() or "屏幕广播",
                               fps, width, targets)

    def _launch_broadcast(self, title, fps, width, targets):
        """启动广播服务并通知所有目标被控端"""
        try:
            from broadcast import BroadcastServer, get_local_ip
        except Exception as e:
            messagebox.showerror("屏幕广播",
                                 f"无法加载广播模块: {e}", parent=self.root)
            return

        try:
            srv = BroadcastServer(fps=fps, width=width, title=title)
            port = srv.start()
        except Exception as e:
            messagebox.showerror("屏幕广播", f"启动失败: {e}", parent=self.root)
            return

        host = get_local_ip()
        print(f"[广播] 服务地址 {host}:{port}，目标 {len(targets)} 台")

        ok_ids, fail = [], []

        def notify(m):
            try:
                r = self._send_req(
                    m, make_bc_start_request(host, port, title, fps, width),
                    timeout=10)
                if r and r.get("ok"):
                    return m.id, True, ""
                return m.id, False, (r or {}).get("message", "无响应")
            except Exception as e:
                return m.id, False, f"{type(e).__name__}: {e}"

        try:
            with ThreadPoolExecutor(max_workers=16) as ex:
                for mid, ok, msg in ex.map(notify, targets):
                    (ok_ids if ok else fail).append((mid, msg))
        except Exception as e:
            print(f"[广播] 通知异常: {e}")

        self.bc_server = srv
        self.bc_target_ids = [m.id for m in targets]
        self.bc_ok_ids = [mid for mid, _ in ok_ids]

        # 按钮切成"结束广播"，并实时显示接入台数
        self.bc_btn.config(text="结束广播", bg="#c62828", fg="white")
        self._bc_tick()

        summary = f"广播已启动（{host}:{port}）\n\n成功: {len(ok_ids)} 台"
        if fail:
            summary += f"\n失败: {len(fail)} 台"
            for mid, msg in fail[:5]:
                m = self.machines.get(mid)
                summary += f"\n  · {m.name if m else mid}: {msg}"
        messagebox.showinfo("屏幕广播", summary, parent=self.root)

    def _bc_tick(self):
        """广播中：每秒刷新按钮上的接入台数"""
        if getattr(self, "bc_server", None) is None:
            return
        try:
            n = self.bc_server.client_count()
            self.bc_btn.config(text=f"结束广播 ({n})")
        except Exception:
            pass
        self.root.after(1000, self._bc_tick)

    def stop_broadcast(self):
        """结束广播：通知所有被控端关窗口 + 停服务"""
        srv = getattr(self, "bc_server", None)
        if srv is None:
            return

        # 1. 先停推流服务（会给所有客户端发 bc_quit）
        try:
            srv.stop()
        except Exception as e:
            print(f"[广播] 停止服务异常: {e}")

        # 2. 再给每台补发 stop 指令（双保险：断线/没连上的也能关掉窗口）
        ids = list(getattr(self, "bc_target_ids", []))
        targets = [self.machines.get(i) for i in ids]
        targets = [m for m in targets if m]

        def notify(m):
            try:
                self._send_req(m, make_bc_stop_request(), timeout=5)
            except Exception:
                pass

        try:
            with ThreadPoolExecutor(max_workers=16) as ex:
                list(ex.map(notify, targets))
        except Exception:
            pass

        self.bc_server = None
        self.bc_target_ids = []
        self.bc_ok_ids = []
        self.bc_btn.config(text="屏幕广播", bg=C_BTN_BG, fg=C_BTN_FG)
        print("[广播] 已结束")
        try:
            messagebox.showinfo("屏幕广播", "广播已结束，被控端窗口已关闭。",
                                parent=self.root)
        except Exception:
            pass

    def control_selected(self, mid: str | None = None):
        """打开「设备详情」控制会话窗口（双击卡片 / 点「控制选中」）"""
        target = mid or self.wall.get_selected()
        if not target:
            messagebox.showwarning("提示", "请先在预览墙中选择一台机器")
            return
        with self.lock:
            machine = self.machines.get(target)
        if not machine:
            return
        if machine.status != "online":
            messagebox.showwarning("提示", f"{machine.name} 当前离线")
            return

        # 同一台机器只开一个窗口，避免重复弹出
        if not hasattr(self, "_sessions"):
            self._sessions = {}
        old = self._sessions.get(target)
        if old is not None:
            try:
                old.win.lift()
                old.win.focus_force()
                return
            except Exception:
                self._sessions.pop(target, None)

        try:
            from session import open_session
            win = open_session(self.root, machine, controller=self)
            self._sessions[target] = win
            # 窗口关闭时清理引用
            win.win.bind("<Destroy>", lambda e, m=target: self._sessions.pop(m, None))
            print(f"[Controller] 打开设备详情: {machine.name}")
        except Exception as e:
            print(f"[Controller] 打开会话窗口失败: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("错误", f"无法打开会话窗口:\n{e}")

    def on_selection_changed(self, mid: str):
        pass  # 预留：选中变化时的回调（如底部详情面板）

    # ---------- 工具 ----------
    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return b""
            buf += chunk
        return buf

    def _recv_all(self, sock: socket.socket, n: int) -> bytes:
        return self._recv_exact(sock, n)

    def shutdown(self):
        self.running = False
        try:
            self.udp_socket.close()
        except Exception:
            pass


def cli_main(port: int, duration: int = 30):
    """
    纯命令行模式: 不启动 GUI，直接在终端列出发现在线的被控端。
    用途: 当图形窗口看不到时，用它 100% 确认"网络链路是通的"。
    """
    print("=" * 60)
    print(f"  CLI 探测模式 - 监听 UDP {port}，持续 {duration} 秒")
    print("  (不启动界面，仅验证能否收到被控端广播)")
    print("=" * 60)

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        udp.bind(("0.0.0.0", port))
    except Exception as e:
        print(f"[错误] 无法绑定端口 {port}: {e}")
        print("       可能已被占用，换一个: --port 9100")
        return

    udp.settimeout(1.0)
    found = {}
    end = time.time() + duration

    print("\n等待被控端广播... (Ctrl+C 提前结束)\n")
    try:
        while time.time() < end:
            try:
                data, addr = udp.recvfrom(65535)
                msg = decode(data)
                if msg.get("type") == MSG_HELLO:
                    mid = msg.get("id", "?")
                    name = msg.get("name", "未知")
                    thumb = "有缩略图" if msg.get("thumb") else "无缩略图"
                    if mid not in found:
                        found[mid] = {"name": name, "ip": addr[0],
                                      "port": msg.get("port", port), "thumb": thumb}
                        print(f"  [发现] {name:12s} @ {addr[0]}:{msg.get('port', port)}  ({thumb})")
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        print("\n(已手动中断)")

    udp.close()

    print("\n" + "=" * 60)
    if found:
        print(f"  ✅ 共发现 {len(found)} 台被控端 —— 网络链路正常！")
        print("     若图形界面看不到卡片，那是窗口显示问题，不是通信问题。")
        print("     解决: 看任务栏 / Alt+Tab / 在独立 PowerShell 窗口里重跑")
    else:
        print("  ❌ 一台都没发现 —— 说明被控端没广播过来")
        print("     检查: 1) agent.py 是否在运行")
        print("           2) --broadcast-ip 是否填的 127.0.0.1 (单机测试)")
        print("           3) 防火墙是否拦截 UDP")
    print("=" * 60)


def cli_scan(port_list=None, base_ip=None):
    """
    纯命令行扫描模式: TCP 主动探测网段，不依赖 UDP 广播、不启动 GUI。
    用于确认"被控端到底在不在、防火墙是否拦了 TCP"。
    """
    local_ip = get_local_ip()
    base = base_ip or (".".join(local_ip.split(".")[:3]) + ".")
    ports = port_list or SCAN_PORTS

    print("=" * 60)
    print("  CLI 扫描模式 (TCP 主动探测)")
    print(f"  本机 IP: {local_ip}")
    print(f"  扫描网段: {base}1~254   端口: {ports}")
    print("=" * 60)
    print("\n扫描中，请稍候(约10-20秒)...\n")

    targets = [(f"{base}{i}", p) for i in range(1, 255) for p in ports]
    found = []

    def probe(t):
        return probe_host(t[0], t[1])

    try:
        with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
            for r in ex.map(probe, targets):
                if r:
                    found.append(r)
                    print(f"  [发现] {r.get('name','?'):12s} @ {r['_ip']}:{r['_port']}  "
                          f"({'有缩略图' if r.get('thumb') else '无缩略图'})")
    except Exception as e:
        print(f"扫描异常: {e}")

    print("\n" + "=" * 60)
    if found:
        print(f"  ✅ 共发现 {len(found)} 台被控端 (TCP 链路正常)")
        print("     -> 防火墙没拦 TCP，只是拦了 UDP 广播")
        print("     -> 用 GUI 的「扫描网段」按钮即可加入这些机器")
    else:
        print("  ❌ 未发现被控端")
        print("     检查: 1) agent.py 是否在运行")
        print("           2) 防火墙是否拦截了 Python 入站连接(需允许)")
    print("=" * 60)


def parse_args():
    parser = argparse.ArgumentParser(description="远控软件 - 控制端 Controller (v2 预览墙)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口")
    parser.add_argument("--cols", type=int, default=0, help="固定列数(0=自适应)")
    parser.add_argument("--cli", action="store_true",
                        help="纯命令行探测模式: 不启动界面，只列出发现在线的被控端")
    parser.add_argument("--cli-time", type=int, default=30, help="CLI 模式探测时长(秒)")
    parser.add_argument("--scan", action="store_true",
                        help="CLI 扫描模式: TCP 主动探测网段(不依赖广播,不启动界面)")
    parser.add_argument("--scan-base", default=None,
                        help="扫描网段前缀, 如 192.168.1. (默认自动推算)")
    return parser.parse_args()


def check_pil_and_warn(root: tk.Tk = None):
    """
    启动时检查 Pillow。
    预览墙显示 JPEG 必须靠 Pillow 解码；VSCode 调试时若用了另一个 Python，
    常出现"pip 装了但代码里 import 不到"，这里直接给出该解释器的确切安装命令。
    """
    try:
        import PIL  # noqa
        return True
    except Exception:
        exe = sys.executable or "python"
        msg = (
            "缺少 Pillow，卡片无法显示画面。\n\n"
            f"当前 Python:\n  {exe}\n\n"
            "请复制下面这行到终端执行：\n"
            f'  "{exe}" -m pip install pillow\n\n'
            "（VSCode 里请在终端直接粘贴，确保用的是同一个解释器）"
        )
        print("=" * 60)
        print("  [严重] 未检测到 Pillow，预览墙将无法显示画面！")
        print(f"  当前解释器: {exe}")
        print(f'  修复命令:   "{exe}" -m pip install pillow')
        print("=" * 60)
        try:
            if root is not None:
                root.withdraw()
            import tkinter.messagebox as mb
            mb.showerror("缺少依赖 Pillow", msg)
            if root is not None:
                root.deiconify()
        except Exception:
            pass
        return False


def bring_to_front(root: tk.Tk):
    """
    强制把窗口拉到最前并居中。
    Windows 下 tkinter 窗口常在 VS Code / 终端窗口后面，导致"程序在跑但看不见"。
    """
    try:
        root.update_idletasks()
        # 居中
        w = root.winfo_width() or 1024
        h = root.winfo_height() or 640
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 2)
        root.geometry(f"{w}x{h}+{x}+{y}")
        # 置顶 + 抢焦点
        root.lift()
        root.attributes("-topmost", True)
        root.focus_force()
        # 300ms 后取消置顶，避免一直压住别的窗口
        root.after(300, lambda: root.attributes("-topmost", False))
    except Exception as e:
        print(f"[Controller] 置顶失败(不影响运行): {e}")


if __name__ == "__main__":
    # 打包成 --windowed 后 sys.stdout 为 None，print 会崩，必须先重定向
    setup_headless_logging("controller.log")

    args = parse_args()

    # CLI 探测模式: 不启动界面（收听 UDP 广播）
    if args.cli:
        cli_main(args.port, args.cli_time)
        sys.exit(0)

    # CLI 扫描模式: TCP 主动探测网段（不依赖广播）
    if args.scan:
        cli_scan(base_ip=args.scan_base)
        sys.exit(0)

    print("=" * 56)
    print("  控制端启动中...")
    print(f"  监听端口: {args.port}")
    print("  若看不到窗口: 看任务栏 / 按 Alt+Tab")
    print("=" * 56)

    root = tk.Tk()
    app = Controller(args.port, root, args.cols)

    # 关键: 窗口创建后立刻拉到最前，解决"程序在跑但看不见"
    root.after(200, lambda: bring_to_front(root))
    # Pillow 缺失会直接导致卡片黑屏，启动即检测并给出确切修复命令
    root.after(300, lambda: check_pil_and_warn(root))

    print("[Controller] 窗口已创建，开始主循环 (Ctrl+C 或关窗口退出)")
    print("[Controller] 等待被控端上线... 被控端上线后卡片会自动出现")

    try:
        root.mainloop()
    finally:
        app.shutdown()
        print("[Controller] 已退出")
