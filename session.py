"""
session.py - 控制会话窗口（设备详情）

双击预览墙卡片、或选中后点「控制选中」时打开。
当前阶段: 只做「壳」——界面完整，按钮/标签页齐全，但不含实际远端功能。
后续接入时，只需替换各 TODO 处的空实现即可。

布局（对齐目标效果图）:
  ┌────────────────────────────────────────────┐
  │ 设备详情 - <机器名>                          │  ← 蓝色标题栏
  ├────────────────────────────────────────────┤
  │ 设备操作                                     │
  │ [发送命令][发送消息][文件列表][上传文件]      │
  │ [进程列表][开始监控][停止监控][查看日志][打开网址]│
  ├────────────────────────────────────────────┤
  │ 控制台 | 文件浏览 | 进程列表 | 屏幕监控       │  ← 标签页
  │                                            │
  │        （各页内容区）                        │
  │                                            │
  │                              [执行]         │  ← 底部按钮
  └────────────────────────────────────────────┘
"""

import base64
import io
import os
import platform
import socket
import threading
import time

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# 复用主界面的蓝色主题
from controller import (
    C_TITLEBAR, C_TITLEBAR_FG, C_APP_BG, C_ACCENT, C_TEXT,
)
from common import (
    encode, decode, recv_all, send_all,
    make_screen_request, make_input_event,
    make_proc_list_request, make_proc_kill_request,
    CHUNK_SIZE,
    make_file_list_request, make_download_request,
    make_upload_begin, make_upload_chunk, make_upload_end,
    make_mkdir_request, make_delete_request,
    make_command_request,
    make_open_url_request,
    make_message_request, make_runcmd_request,
    CMD_TIMEOUT, CMD_MAX_TIMEOUT,
    EVT_MOUSE_MOVE, EVT_MOUSE_DOWN, EVT_MOUSE_UP, EVT_MOUSE_CLICK,
    EVT_MOUSE_WHEEL, EVT_KEY_DOWN, EVT_KEY_UP, EVT_KEY_PRESS,
)

FONT = "Microsoft YaHei"


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# 控制端自身系统（只用于选"常用命令"预设，被控端可能是别的系统）
_IS_WIN = platform.system() == "Windows"

# ============ 屏幕监控参数 ============
TARGET_FPS = 30            # 目标帧率
FRAME_QUALITY = 55         # JPEG 质量(1-95)，越高越清但越占带宽
SOCKET_TIMEOUT = 5.0       # 单帧收发超时(秒)

# 浅色圆角按钮（对标效果图的设备操作按钮）
BTN_BG = "#e8f1fb"
BTN_FG = "#1565c0"
BTN_ACTIVE = "#bbdefb"


class SessionWindow:
    """
    单个被控端的详情/控制窗口。

    用法:
        SessionWindow(parent_root, machine_dict)
        machine_dict 至少含: id / name / ip / port / os
    """

    def __init__(self, master: tk.Misc, machine, controller=None):
        self.master = master
        self.machine = machine            # Machine 对象或等价 dict
        self.controller_ref = controller  # Controller 引用（用于拉取日志等）
        self.name = machine.get("name") if isinstance(machine, dict) else machine.name
        self.ip = machine.get("ip") if isinstance(machine, dict) else machine.ip
        self.port = machine.get("port") if isinstance(machine, dict) else machine.port
        self.os = machine.get("os", "未知") if isinstance(machine, dict) else getattr(machine, "os", "未知")

        self.win = tk.Toplevel(master)
        self.win.title(f"设备详情 - {self.name}")
        self.win.geometry("1000x680")
        self.win.configure(bg=C_APP_BG)
        self.win.transient(master)        # 跟随主窗口
        self.win.lift()
        try:
            self.win.attributes("-topmost", True)
            self.win.after(400, lambda: self.win.attributes("-topmost", False))
        except Exception:
            pass

        self._build_titlebar()
        self._build_toolbar()
        self._build_notebook()
        self._build_bottom()

        self.win.protocol("WM_DELETE_WINDOW", self.close)

    # ---------- 标题栏 ----------

    def _build_titlebar(self):
        bar = tk.Frame(self.win, bg=C_TITLEBAR, height=38)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        tk.Label(bar, text=f"🖥️  设备详情 - {self.name}",
                 bg=C_TITLEBAR, fg=C_TITLEBAR_FG,
                 font=(FONT, 12, "bold")).pack(side="left", padx=14)
        tk.Label(bar, text=f"{self.ip}:{self.port}   ·   {self.os}",
                 bg=C_TITLEBAR, fg="#bbdefb",
                 font=(FONT, 9)).pack(side="right", padx=14)

    # ---------- 设备操作按钮区 ----------

    def _build_toolbar(self):
        outer = tk.LabelFrame(self.win, text=" 设备操作 ", bg=C_APP_BG, fg="#1565c0",
                              font=(FONT, 10, "bold"), padx=8, pady=6,
                              highlightbackground=C_ACCENT, highlightthickness=1)
        outer.pack(fill="x", padx=10, pady=(8, 4))

        # 按钮定义: (文字, 回调)
        # 注: 「开始/停止监控」已移除 —— 改为切换到「屏幕监控」页自动开始，
        #     切走自动停止（见 _on_tab_changed）。
        actions = [
            ("发送命令", self.act_send_command),
            ("发送消息", self.act_send_message),
            ("上传文件", self.act_upload_file),
            ("进程管理", self.act_process_manage),
            ("查看日志", self.act_view_log),
            ("打开网址", self.act_open_url),
        ]
        # 单行 + 水平居中
        row1 = tk.Frame(outer, bg=C_APP_BG)
        row1.pack(fill="x")
        # 用居中容器包裹，按钮整体居中
        center = tk.Frame(row1, bg=C_APP_BG)
        center.pack(anchor="center")

        for text, cmd in actions:
            b = tk.Button(center, text=text, command=cmd,
                          bg=BTN_BG, fg=BTN_FG,
                          activebackground=BTN_ACTIVE, activeforeground=BTN_FG,
                          relief="flat", bd=0, padx=16, pady=6,
                          font=(FONT, 9), cursor="hand2")
            b.pack(side="left", padx=5)

        # 命令输入框（给「执行」按钮用）
        cmdrow = tk.Frame(outer, bg=C_APP_BG)
        cmdrow.pack(fill="x", pady=(8, 0))
        tk.Label(cmdrow, text="命令:", bg=C_APP_BG, fg="#1565c0",
                 font=(FONT, 9)).pack(side="left", padx=(4, 6))
        self.cmd_var = tk.StringVar()
        self.cmd_entry = tk.Entry(cmdrow, textvariable=self.cmd_var,
                                  font=(FONT, 9), relief="solid", bd=1)
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # 回车 = 执行；↑/↓ = 翻命令历史
        self.cmd_entry.bind("<Return>", lambda e: self.act_execute())
        self.cmd_entry.bind("<Up>", self._cmd_history_up)
        self.cmd_entry.bind("<Down>", self._cmd_history_down)
        self._cmd_history = []
        self._cmd_hist_idx = -1

    # ---------- 标签页 ----------

    def _build_notebook(self):
        style = ttk.Style()
        try:
            style.configure("Session.TNotebook", background=C_APP_BG)
            style.configure("Session.TNotebook.Tab", font=(FONT, 9), padding=(12, 5))
        except Exception:
            pass

        self.nb = ttk.Notebook(self.win, style="Session.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=10, pady=6)

        self.page_console = self._build_console_page()
        self.page_files = self._build_files_page()
        self.page_process = self._build_process_page()
        self.page_screen = self._build_screen_page()

        # 自动监控: 切到「屏幕监控」自动开始，切走自动停止
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # ---------- 进程管理页 ----------

    def _build_process_page(self) -> tk.Frame:
        """
        进程列表页（真实功能）:
          - 顶部: 刷新 / 结束进程 / 强制结束 / 搜索 / 自动刷新
          - 表格: PID | 名称 | CPU% | 内存MB | 状态
          - 底部: 进程总数 + 采集方式
        """
        page = tk.Frame(self.nb, bg="white")
        self.nb.add(page, text="进程列表")

        # ---- 工具栏 ----
        bar = tk.Frame(page, bg="white")
        bar.pack(fill="x", padx=6, pady=(6, 4))

        tk.Button(bar, text="刷新", command=self.proc_refresh,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=12, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left", padx=(0, 4))
        tk.Button(bar, text="结束进程", command=lambda: self.proc_kill(force=False),
                  bg="#ffebee", fg="#c62828", relief="flat", bd=0,
                  padx=12, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left", padx=4)
        tk.Button(bar, text="强制结束", command=lambda: self.proc_kill(force=True),
                  bg="#c62828", fg="white", relief="flat", bd=0,
                  padx=12, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left", padx=4)

        # 搜索
        tk.Label(bar, text="搜索:", bg="white", fg="#1565c0",
                 font=(FONT, 8)).pack(side="left", padx=(14, 3))
        self.proc_filter = tk.StringVar()
        e = tk.Entry(bar, textvariable=self.proc_filter, width=16,
                     font=(FONT, 8), relief="solid", bd=1)
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self._proc_apply_filter())

        # 自动刷新
        self.proc_auto = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="自动刷新(3秒)", variable=self.proc_auto,
                       command=self._proc_toggle_auto,
                       bg="white", fg="#1565c0", activebackground="white",
                       selectcolor="#e3f2fd", font=(FONT, 8),
                       cursor="hand2").pack(side="left", padx=(12, 0))

        # ---- 表格 ----
        tbl_frame = tk.Frame(page, bg="white")
        tbl_frame.pack(fill="both", expand=True, padx=6, pady=(0, 2))

        cols = ("pid", "name", "cpu", "mem", "status")
        self.proc_tree = ttk.Treeview(tbl_frame, columns=cols,
                                      show="headings", height=18)
        headings = {
            "pid": ("PID", 80),
            "name": ("进程名称", 260),
            "cpu": ("CPU %", 80),
            "mem": ("内存 MB", 100),
            "status": ("状态", 90),
        }
        for c in cols:
            text, w = headings[c]
            self.proc_tree.heading(c, text=text)
            anchor = "center" if c in ("pid", "cpu", "mem", "status") else "w"
            self.proc_tree.column(c, width=w, anchor=anchor,
                                  stretch=(c == "name"))

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical",
                            command=self.proc_tree.yview)
        self.proc_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.proc_tree.pack(side="left", fill="both", expand=True)

        # 双击 = 结束进程
        self.proc_tree.bind("<Double-1>", lambda e: self.proc_kill(force=False))

        # ---- 底部状态 ----
        self.proc_status = tk.Label(page, text="点「刷新」载入进程列表",
                                    bg="white", fg="#607d8b",
                                    font=(FONT, 8), anchor="w")
        self.proc_status.pack(fill="x", padx=8, pady=(0, 6))

        self._proc_all = []          # 全量数据（搜索过滤用）
        self._proc_loading = False
        return page

    # ---- 数据获取 ----

    def proc_refresh(self):
        """拉取进程列表（后台线程，避免卡界面）"""
        if self._proc_loading:
            return
        self._proc_loading = True
        try:
            self.proc_status.config(text="正在读取进程列表…", fg="#1565c0")
        except Exception:
            pass
        threading.Thread(target=self._proc_fetch_worker, daemon=True).start()

    def _proc_fetch_worker(self):
        procs, backend, err = [], "", ""
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=8)
            sock.settimeout(8)
            send_all(sock, encode(make_proc_list_request()))
            data = recv_all(sock, timeout=8)
            sock.close()
            if data:
                resp = decode(data)
                procs = resp.get("procs", []) or []
                backend = resp.get("backend", "")
            else:
                err = "被控端无响应"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"

        # 回主线程更新 UI
        self.win.after(0, lambda: self._proc_render(procs, backend, err))

    def _proc_render(self, procs, backend, err=""):
        self._proc_loading = False
        self._proc_all = procs
        self._proc_apply_filter()

        be_text = {"psutil": "psutil（完整信息）",
                   "tasklist": "tasklist（Windows命令，无CPU）",
                   "ps": "ps（Linux命令）"}.get(backend, backend or "未知")
        if err:
            self.proc_status.config(text=f"读取失败: {err}", fg="#c62828")
        else:
            self.proc_status.config(
                text=f"共 {len(procs)} 个进程   ·   采集方式: {be_text}",
                fg="#607d8b")

        if self.proc_auto.get():
            self.win.after(3000, self.proc_refresh)

    def _proc_apply_filter(self):
        """按搜索关键字过滤显示"""
        kw = ""
        try:
            kw = (self.proc_filter.get() or "").strip().lower()
        except Exception:
            pass

        tree = self.proc_tree
        for item in tree.get_children():
            tree.delete(item)

        for p in self._proc_all:
            if kw and kw not in str(p.get("name", "")).lower() \
                    and kw not in str(p.get("pid", "")):
                continue
            tree.insert("", "end", values=(
                p.get("pid", ""),
                p.get("name", "?"),
                p.get("cpu", 0),
                p.get("mem", 0),
                p.get("status", ""),
            ))

    def _proc_toggle_auto(self):
        if self.proc_auto.get():
            self.proc_refresh()

    # ---- 结束进程 ----

    def proc_kill(self, force: bool = False):
        sel = self.proc_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选中一个进程", parent=self.win)
            return
        values = self.proc_tree.item(sel[0], "values")
        if not values:
            return
        pid, name = values[0], values[1]

        tip = ("强制结束" if force else "结束") + f"进程？\n\n{name}  (PID {pid})"
        if force:
            tip += "\n\n强制结束可能导致数据丢失，确定继续？"
        if not messagebox.askyesno("确认", tip, parent=self.win):
            return

        threading.Thread(target=self._proc_kill_worker,
                         args=(int(pid), force), daemon=True).start()

    def _proc_kill_worker(self, pid: int, force: bool):
        ok, msg = False, ""
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=8)
            sock.settimeout(8)
            send_all(sock, encode(make_proc_kill_request(pid, force)))
            data = recv_all(sock, timeout=8)
            sock.close()
            if data:
                resp = decode(data)
                ok = bool(resp.get("ok"))
                msg = resp.get("message", "")
            else:
                msg = "被控端无响应"
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"

        def _done():
            if ok:
                self.proc_status.config(text=f"✓ {msg}", fg="#2e7d32")
            else:
                messagebox.showerror("结束失败", f"{msg}", parent=self.win)
            self.proc_refresh()      # 刷新列表

        self.win.after(0, _done)

    # ---------- 文件浏览页 ----------

    def _build_files_page(self) -> tk.Frame:
        """文件浏览页（真实功能）: 列目录 / 上传 / 下载 / 新建文件夹 / 删除"""
        page = tk.Frame(self.nb, bg="white")
        self.nb.add(page, text="文件浏览")

        # ---- 路径栏 ----
        top = tk.Frame(page, bg="white")
        top.pack(fill="x", padx=6, pady=(6, 4))

        tk.Button(top, text="↑ 上级", command=self.file_go_parent,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=10, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left", padx=(0, 4))
        tk.Button(top, text="🏠 根目录", command=self.file_go_root,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=10, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left", padx=4)
        tk.Button(top, text="刷新", command=self.file_refresh,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=10, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left", padx=4)

        self.file_path_var = tk.StringVar(value="")
        tk.Entry(top, textvariable=self.file_path_var,
                 font=(FONT, 8), relief="solid", bd=1).pack(
            side="left", fill="x", expand=True, padx=(8, 4))
        tk.Button(top, text="转到", command=self.file_goto,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=10, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left")

        # 操作按钮
        bar = tk.Frame(page, bg="white")
        bar.pack(fill="x", padx=6, pady=(2, 4))

        tk.Button(bar, text="⬆ 上传文件", command=self.act_upload_file,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=12, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left", padx=(0, 4))
        tk.Button(bar, text="⬇ 下载", command=self.file_download,
                  bg="#e8f5e9", fg="#2e7d32", relief="flat", bd=0,
                  padx=12, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left", padx=4)
        tk.Button(bar, text="新建文件夹", command=self.file_mkdir,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=12, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left", padx=4)
        tk.Button(bar, text="删除", command=self.file_delete,
                  bg="#c62828", fg="white", relief="flat", bd=0,
                  padx=12, pady=4, font=(FONT, 8),
                  cursor="hand2").pack(side="left", padx=4)

        # 写保护状态提示
        tk.Label(bar,
                 text="🛡 C:\\Windows 已开启写保护（命令栏输入 SAFE_MODE_OFF 可临时关闭）",
                 bg="white", fg="#00897b", font=(FONT, 8)).pack(
            side="right", padx=(8, 4))

        # ---- 表格 ----
        tbl = tk.Frame(page, bg="white")
        tbl.pack(fill="both", expand=True, padx=6, pady=(0, 2))

        cols = ("name", "size", "mtime", "type")
        self.file_tree = ttk.Treeview(tbl, columns=cols, show="headings", height=16)
        for c, (text, w) in {
            "name": ("名称", 380),
            "size": ("大小", 110),
            "mtime": ("修改时间", 160),
            "type": ("类型", 100),
        }.items():
            self.file_tree.heading(c, text=text)
            anchor = "w" if c == "name" else "center"
            self.file_tree.column(c, width=w, anchor=anchor,
                                  stretch=(c == "name"))

        vsb = ttk.Scrollbar(tbl, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.file_tree.pack(side="left", fill="both", expand=True)

        # 双击进入目录
        self.file_tree.bind("<Double-1>", self._on_file_dblclick)

        # ---- 状态 ----
        self.file_status = tk.Label(page, text="点「刷新」载入文件列表",
                                    bg="white", fg="#607d8b",
                                    font=(FONT, 8), anchor="w")
        self.file_status.pack(fill="x", padx=8, pady=(0, 6))

        self._file_entries = []       # 当前目录条目
        self._file_loading = False
        return page

    # ---- 文件操作 ----

    def _file_set_status(self, text, color="#607d8b"):
        try:
            self.file_status.config(text=text, fg=color)
        except Exception:
            pass

    def file_refresh(self, path: str = None):
        if self._file_loading:
            return
        self._file_loading = True
        if path is not None:
            self.file_path_var.set(path)
        self._file_set_status("正在读取目录…", "#1565c0")
        threading.Thread(target=self._file_list_worker, daemon=True).start()

    def _file_list_worker(self):
        path = ""
        try:
            path = self.file_path_var.get()
        except Exception:
            pass

        entries, parent, err = [], "", ""
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=8)
            sock.settimeout(8)
            send_all(sock, encode(make_file_list_request(path)))
            data = recv_all(sock, timeout=8)
            sock.close()
            if data:
                resp = decode(data)
                if resp.get("ok", False):
                    entries = resp.get("entries", []) or []
                    parent = resp.get("parent", "")
                    path = resp.get("path", path)
                else:
                    err = resp.get("message", "未知错误")
            else:
                err = "被控端无响应"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"

        self.win.after(0, lambda: self._file_render(path, parent, entries, err))

    def _file_render(self, path, parent, entries, err=""):
        self._file_loading = False
        self._file_entries = entries
        self._file_parent = parent

        # 清空表格
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)

        if err:
            self._file_set_status(f"读取失败: {err}", "#c62828")
            return

        # 上级目录项
        if parent:
            self.file_tree.insert("", "end", iid="__parent__", values=(
                "..", "", "", "上级目录"))

        for e in entries:
            is_dir = e.get("is_dir")
            size = "" if is_dir else self._fmt_size(e.get("size", 0))
            self.file_tree.insert("", "end", iid=e.get("path", e.get("name")),
                                  values=(e.get("name", "?"), size,
                                          e.get("mtime", ""),
                                          "文件夹" if is_dir else "文件"))

        try:
            self.file_path_var.set(path)
        except Exception:
            pass
        self._file_set_status(f"共 {len(entries)} 项   ·   {path}", "#607d8b")

    @staticmethod
    def _fmt_size(n) -> str:
        try:
            n = float(n)
        except Exception:
            return ""
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return ""

    def _on_file_dblclick(self, event):
        sel = self.file_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "__parent__":
            self.file_go_parent()
            return
        # 判断是不是目录
        for e in self._file_entries:
            if e.get("path") == iid and e.get("is_dir"):
                self.file_refresh(iid)
                return
        # 是文件 → 下载
        self.file_download()

    def file_go_parent(self):
        p = getattr(self, "_file_parent", "") or ""
        if p:
            self.file_refresh(p)

    def file_go_root(self):
        self.file_refresh("")

    def file_goto(self):
        try:
            p = self.file_path_var.get()
        except Exception:
            return
        self.file_refresh(p)

    # ---- 下载 ----

    def file_download(self):
        """下载选中的文件到本地"""
        sel = self.file_tree.selection()
        if not sel or sel[0] == "__parent__":
            messagebox.showwarning("提示", "请先选中一个文件", parent=self.win)
            return
        remote_path = sel[0]
        # 目录不能下载
        for e in self._file_entries:
            if e.get("path") == remote_path and e.get("is_dir"):
                messagebox.showwarning("提示", "这是文件夹，请选中文件下载",
                                       parent=self.win)
                return

        name = os.path.basename(remote_path) or "download"
        local = filedialog.asksaveasfilename(
            title="保存到本地", initialfile=name, parent=self.win)
        if not local:
            return

        self._file_set_status(f"正在下载 {name} …", "#1565c0")
        threading.Thread(target=self._file_dl_worker,
                         args=(remote_path, local), daemon=True).start()

    def _file_dl_worker(self, remote_path: str, local_path: str):
        """分块下载"""
        try:
            total = 0
            got = 0
            with open(local_path, "wb") as out:
                while True:
                    sock = socket.create_connection((self.ip, self.port), timeout=10)
                    sock.settimeout(10)
                    send_all(sock, encode(make_download_request(
                        remote_path, got, CHUNK_SIZE)))
                    data = recv_all(sock, timeout=10)
                    sock.close()
                    if not data:
                        raise RuntimeError("被控端无响应")
                    resp = decode(data)
                    if not resp.get("ok", False):
                        raise RuntimeError(resp.get("message", "下载失败"))
                    chunk = base64.b64decode(resp.get("data", ""))
                    total = resp.get("total", 0)
                    if chunk:
                        out.write(chunk)
                        got += len(chunk)
                    if resp.get("eof", True):
                        break
                    if not chunk:
                        break
            msg = f"✓ 下载完成: {os.path.basename(local_path)} ({self._fmt_size(got)})"
            self.win.after(0, lambda: self._file_set_status(msg, "#2e7d32"))
        except Exception as e:
            err = str(e)
            self.win.after(0, lambda: (
                self._file_set_status(f"下载失败: {err}", "#c62828"),
                messagebox.showerror("下载失败", err, parent=self.win)))

    # ---- 上传 ----

    def act_upload_file(self):
        """「上传文件」按钮：选本地文件传到远端当前目录"""
        self.nb.select(self.page_files)
        local = filedialog.askopenfilename(title="选择要上传的文件",
                                           parent=self.win)
        if not local:
            return
        remote_dir = ""
        try:
            remote_dir = self.file_path_var.get() or ""
        except Exception:
            pass
        if not remote_dir:
            # 根目录（盘符列表）时不能上传，先让用户进到具体目录
            messagebox.showwarning(
                "提示", "请先进入一个具体目录（双击文件夹）再上传", parent=self.win)
            return

        name = os.path.basename(local)
        size = os.path.getsize(local)
        self._file_set_status(f"正在上传 {name} ({self._fmt_size(size)})…", "#1565c0")
        threading.Thread(target=self._file_up_worker,
                         args=(local, remote_dir, name), daemon=True).start()

    def _file_up_worker(self, local_path: str, remote_dir: str, name: str):
        """分块上传（一条连接完成 begin→chunks→end）"""
        try:
            size = os.path.getsize(local_path)
            sock = socket.create_connection((self.ip, self.port), timeout=15)
            sock.settimeout(30)

            # 1. begin
            send_all(sock, encode(make_upload_begin(remote_dir, name, size)))
            resp = decode(recv_all(sock, timeout=15))
            if not resp.get("ok", False):
                raise RuntimeError(resp.get("message", "无法开始上传"))

            # 2. chunks
            sent = 0
            with open(local_path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    send_all(sock, encode(make_upload_chunk(b64encode(chunk))))
                    r = decode(recv_all(sock, timeout=20))
                    if not r.get("ok", False):
                        raise RuntimeError(r.get("message", "写入失败"))
                    sent += len(chunk)

            # 3. end
            send_all(sock, encode(make_upload_end()))
            resp = decode(recv_all(sock, timeout=15))
            sock.close()

            if resp.get("ok", False):
                msg = f"✓ 上传完成: {name} ({self._fmt_size(sent)})"
                self.win.after(0, lambda: (
                    self._file_set_status(msg, "#2e7d32"),
                    self.file_refresh()))
            else:
                raise RuntimeError(resp.get("message", "上传失败"))
        except Exception as e:
            err = str(e)
            self.win.after(0, lambda: (
                self._file_set_status(f"上传失败: {err}", "#c62828"),
                messagebox.showerror("上传失败", err, parent=self.win)))

    # ---- 新建文件夹 / 删除 ----

    def file_mkdir(self):
        from tkinter import simpledialog
        cur = ""
        try:
            cur = self.file_path_var.get() or ""
        except Exception:
            pass
        if not cur:
            messagebox.showwarning("提示", "请先进入一个目录", parent=self.win)
            return
        name = simpledialog.askstring("新建文件夹", "文件夹名称:", parent=self.win)
        if not name:
            return
        path = os.path.join(cur, name)
        threading.Thread(target=self._file_simple_worker,
                         args=("mkdir", path, name), daemon=True).start()

    def file_delete(self):
        sel = self.file_tree.selection()
        if not sel or sel[0] == "__parent__":
            messagebox.showwarning("提示", "请先选中要删除的项", parent=self.win)
            return
        path = sel[0]
        name = os.path.basename(path) or path
        if not messagebox.askyesno("确认删除",
                                   f"确定删除？\n\n{name}\n\n此操作不可撤销",
                                   parent=self.win):
            return
        threading.Thread(target=self._file_simple_worker,
                         args=("delete", path, name), daemon=True).start()

    def _file_simple_worker(self, kind: str, path: str, name: str):
        ok, msg = False, ""
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=10)
            sock.settimeout(10)
            if kind == "mkdir":
                send_all(sock, encode(make_mkdir_request(path)))
                resp = decode(recv_all(sock, timeout=10))
                ok, msg = resp.get("ok", False), resp.get("message", "")
            else:
                send_all(sock, encode(make_delete_request(path)))
                resp = decode(recv_all(sock, timeout=10))
                ok, msg = resp.get("ok", False), resp.get("message", "")
            sock.close()
        except Exception as e:
            ok, msg = False, f"{type(e).__name__}: {e}"

        def _done():
            if ok:
                self._file_set_status(f"✓ {msg}", "#2e7d32")
                self.file_refresh()
            else:
                messagebox.showerror("操作失败", msg, parent=self.win)

        self.win.after(0, _done)

    def _make_placeholder_page(self, title: str, tip: str) -> tk.Frame:
        page = tk.Frame(self.nb, bg="white")
        tk.Label(page, text=tip, bg="white", fg="#607d8b",
                 font=(FONT, 10), justify="center").pack(expand=True)
        self.nb.add(page, text=title)
        return page

    def _build_screen_page(self) -> tk.Frame:
        """屏幕监控页：预留画布，后续接实时帧"""
        page = tk.Frame(self.nb, bg="white")
        self.nb.add(page, text="屏幕监控")

        # ---- 控制条：勾选框（在画布上方） ----
        ctrlbar = tk.Frame(page, bg="white")
        ctrlbar.pack(fill="x", padx=6, pady=(6, 0))

        self.control_var = tk.BooleanVar(value=False)
        self.control_cb = tk.Checkbutton(
            ctrlbar,
            text="🖱️ 控制鼠标键盘（勾选后可直接操作对方桌面）",
            variable=self.control_var,
            command=self._on_control_toggled,
            bg="white", fg="#1565c0",
            activebackground="white", activeforeground="#1565c0",
            selectcolor="#e3f2fd",
            font=(FONT, 9), cursor="hand2", anchor="w")
        self.control_cb.pack(side="left")

        # 状态提示（是否已连接、能否控制）
        self.ctrl_status = tk.Label(ctrlbar, text="未启用",
                                    bg="white", fg="#90a4ae", font=(FONT, 8))
        self.ctrl_status.pack(side="right", padx=8)

        # 画布：显示远端画面
        self.screen_canvas = tk.Canvas(page, bg="#0d1b33", highlightthickness=0)
        self.screen_canvas.pack(fill="both", expand=True, padx=6, pady=6)

        # 绑定键鼠事件（是否真的转发，由勾选框决定）
        self._bind_input_events()

        # 占位提示
        self.screen_hint = tk.Label(
            self.screen_canvas,
            text="正在连接…",
            bg="#0d1b33", fg="#90a4ae", font=(FONT, 11), justify="center")
        self.screen_hint_id = self.screen_canvas.create_window(
            0, 0, window=self.screen_hint, anchor="center")

        # 让提示始终居中
        def recenter(event=None):
            w = self.screen_canvas.winfo_width()
            h = self.screen_canvas.winfo_height()
            self.screen_canvas.coords(self.screen_hint, w // 2, h // 2)
        self.screen_canvas.bind("<Configure>", recenter)
        self.win.after(100, recenter)

        self._monitoring = False
        return page

    # ---------- 键鼠远程控制 ----------

    def _on_control_toggled(self):
        """勾选框切换：建立 / 断开独立的控制连接"""
        if self.control_var.get():
            self._control_connect()
        else:
            self._control_disconnect()

    def _control_connect(self):
        """建立专用控制连接（独立于拉帧连接，互不干扰）"""
        if getattr(self, "_ctrl_sock", None):
            return
        try:
            s = socket.create_connection((self.ip, self.port), timeout=5)
            s.settimeout(5)
            self._ctrl_sock = s
            self.ctrl_status.config(text="● 控制已启用", fg="#2e7d32")
            # 让画布拿到键盘焦点（否则按键收不到）
            try:
                self.screen_canvas.focus_set()
            except Exception:
                pass
            print(f"[会话] 已建立控制连接 -> {self.ip}:{self.port}")
        except Exception as e:
            self.control_var.set(False)
            self.ctrl_status.config(text=f"连接失败", fg="#c62828")
            print(f"[会话] 控制连接失败: {e}")
            messagebox.showerror("控制连接失败",
                                 f"无法连接到 {self.ip}:{self.port}\n\n{e}",
                                 parent=self.win)

    def _control_disconnect(self):
        """断开控制连接"""
        s = getattr(self, "_ctrl_sock", None)
        if s:
            try:
                s.close()
            except Exception:
                pass
        self._ctrl_sock = None
        try:
            self.ctrl_status.config(text="未启用", fg="#90a4ae")
        except Exception:
            pass
        print("[会话] 已断开控制连接")

    def _bind_input_events(self):
        """给画布绑定鼠标 / 键盘事件"""
        c = self.screen_canvas
        # 鼠标
        c.bind("<Motion>", self._on_mouse_move)
        c.bind("<Button-1>", lambda e: self._on_mouse_down(e, "left"))
        c.bind("<Button-3>", lambda e: self._on_mouse_down(e, "right"))
        c.bind("<Button-2>", lambda e: self._on_mouse_down(e, "middle"))
        c.bind("<ButtonRelease-1>", lambda e: self._on_mouse_up(e, "left"))
        c.bind("<ButtonRelease-3>", lambda e: self._on_mouse_up(e, "right"))
        c.bind("<ButtonRelease-2>", lambda e: self._on_mouse_up(e, "middle"))
        c.bind("<MouseWheel>", self._on_mouse_wheel)   # Windows
        c.bind("<Button-4>", lambda e: self._on_mouse_wheel_linux(e, 120))   # Linux 上滚
        c.bind("<Button-5>", lambda e: self._on_mouse_wheel_linux(e, -120))  # Linux 下滚
        # 键盘（画布需先获得焦点）
        c.bind("<KeyPress>", self._on_key_down)
        c.bind("<KeyRelease>", self._on_key_up)
        c.bind("<Enter>", lambda e: c.focus_set())     # 鼠标移入自动聚焦

    def _to_remote(self, cx: int, cy: int):
        """
        画布坐标 → 被控端原始分辨率坐标。
        画面是等比缩放并居中显示的，需要还原。
        """
        scale = getattr(self, "_scale", 0) or 0
        if scale <= 0:
            return None
        ox = getattr(self, "_offx", 0)
        oy = getattr(self, "_offy", 0)
        rx = (cx - ox) / scale
        ry = (cy - oy) / scale
        # 限制在被控端屏幕范围内，防止越界
        rw = getattr(self, "_remote_w", 0)
        rh = getattr(self, "_remote_h", 0)
        if rw > 0 and rh > 0:
            if not (0 <= rx <= rw and 0 <= ry <= rh):
                return None
        return (int(rx), int(ry))

    def _send_input(self, event_type: str, **kwargs):
        """发送一个输入事件（fire-and-forget，不等响应）"""
        if not self.control_var.get():
            return
        s = getattr(self, "_ctrl_sock", None)
        if not s or not getattr(self, "_monitoring", False):
            return
        try:
            send_all(s, encode(make_input_event(event_type, **kwargs)))
        except Exception as e:
            print(f"[会话] 发送输入事件失败: {e}")
            self._control_disconnect()
            self.control_var.set(False)

    # ---- 具体事件处理 ----

    def _on_mouse_move(self, event):
        pt = self._to_remote(event.x, event.y)
        if pt:
            self._send_input(EVT_MOUSE_MOVE, x=pt[0], y=pt[1])

    def _on_mouse_down(self, event, button):
        pt = self._to_remote(event.x, event.y)
        if pt:
            self._send_input(EVT_MOUSE_DOWN, x=pt[0], y=pt[1], button=button)
        try:
            self.screen_canvas.focus_set()
        except Exception:
            pass

    def _on_mouse_up(self, event, button):
        pt = self._to_remote(event.x, event.y)
        if pt:
            self._send_input(EVT_MOUSE_UP, x=pt[0], y=pt[1], button=button)

    def _on_mouse_wheel(self, event):
        # Windows: event.delta 通常是 ±120
        pt = self._to_remote(event.x, event.y) or (0, 0)
        self._send_input(EVT_MOUSE_WHEEL, x=pt[0], y=pt[1], delta=event.delta)

    def _on_mouse_wheel_linux(self, event, delta):
        pt = self._to_remote(event.x, event.y) or (0, 0)
        self._send_input(EVT_MOUSE_WHEEL, x=pt[0], y=pt[1], delta=delta)

    def _on_key_down(self, event):
        self._send_input(EVT_KEY_DOWN, key=event.keysym)

    def _on_key_up(self, event):
        self._send_input(EVT_KEY_UP, key=event.keysym)

    def _on_tab_changed(self, event=None):
        """
        标签页切换:
          - 切到「屏幕监控」→ 自动开始 30FPS 监控
          - 切到其它页     → 自动停止（省带宽、省 CPU）
        """
        try:
            current = self.nb.index(self.nb.select())
            screen_idx = self.nb.index(self.page_screen)
            proc_idx = self.nb.index(self.page_process)
            files_idx = self.nb.index(self.page_files)
        except Exception:
            return

        if current == screen_idx:
            if not getattr(self, "_monitoring", False):
                print(f"[会话] 切到屏幕监控，自动开始")
                self.act_start_monitor()
        elif current == proc_idx:
            # 切到「进程列表」自动载入一次（和屏幕监控一致的体验）
            if not self._proc_all:
                print(f"[会话] 切到进程列表，自动载入")
                self.proc_refresh()
        elif current == files_idx:
            # 切到「文件浏览」自动载入一次
            if not getattr(self, "_file_entries", None):
                print(f"[会话] 切到文件浏览，自动载入")
                self.file_refresh()
        else:
            # 离开屏幕页：自动停止监控 + 断开控制（防止误操作对方电脑）
            if self.control_var.get():
                print(f"[会话] 离开屏幕页，自动断开控制")
                self.control_var.set(False)
                self._control_disconnect()
            if getattr(self, "_monitoring", False):
                print(f"[会话] 离开屏幕监控，自动停止")
                self.act_stop_monitor()

    # ---------- 底部执行按钮 ----------

    def _build_bottom(self):
        bottom = tk.Frame(self.win, bg=C_APP_BG)
        bottom.pack(fill="x", padx=10, pady=(0, 8))
        tk.Button(bottom, text="执行", command=self.act_execute,
                  bg=C_TITLEBAR, fg="white",
                  activebackground=C_ACCENT, activeforeground="white",
                  relief="flat", bd=0, padx=26, pady=5,
                  font=(FONT, 9, "bold"), cursor="hand2").pack(side="right")

    # ---------- 动作（当前全是空壳，仅提示） ----------

    def _todo(self, what: str):
        """统一的"功能开发中"提示"""
        messagebox.showinfo(
            "功能开发中",
            f"{what}\n\n"
            f"目标设备: {self.name} ({self.ip}:{self.port})\n\n"
            f"界面壳已完成，实际功能将在后续阶段接入。",
            parent=self.win)

    def act_send_command(self):
        """
        「发送命令」按钮：弹对话框输入命令（支持多行/预设），发送到被控端执行。

        和命令栏的区别:
          - 命令栏: 快速单条执行
          - 本对话框: 可写多行脚本、选预设、设超时、勾"执行完弹窗通知"
        """
        dlg = tk.Toplevel(self.win)
        dlg.title("发送命令（被控端执行）")
        dlg.configure(bg=C_APP_BG)
        dlg.resizable(True, True)
        dlg.transient(self.win)
        dlg.grab_set()

        try:
            self.win.update_idletasks()
            px = self.win.winfo_x() + (self.win.winfo_width() - 560) // 2
            py = self.win.winfo_y() + (self.win.winfo_height() - 420) // 2
            dlg.geometry(f"560x420+{max(0, px)}+{max(0, py)}")
        except Exception:
            dlg.geometry("560x420")

        tk.Label(dlg, text="在被控端执行命令", bg=C_APP_BG, fg="#1565c0",
                 font=(FONT, 10, "bold")).pack(pady=(10, 6))

        # ---- 预设命令 ----
        pf = tk.Frame(dlg, bg=C_APP_BG)
        pf.pack(fill="x", padx=14, pady=(0, 4))
        tk.Label(pf, text="预设:", bg=C_APP_BG, fg="#1565c0",
                 font=(FONT, 9)).pack(side="left")
        presets = [
            ("查看IP", "ipconfig" if _IS_WIN else "ifconfig"),
            ("系统信息", "systeminfo" if _IS_WIN else "uname -a"),
            ("进程列表", "tasklist" if _IS_WIN else "ps aux"),
            ("磁盘空间", "wmic logicaldisk get size,freespace,caption"
                         if _IS_WIN else "df -h"),
        ]
        for label, real in presets:
            tk.Button(pf, text=label, command=lambda c=real: _set_cmd(c),
                      bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                      padx=8, pady=2, font=(FONT, 8),
                      cursor="hand2").pack(side="left", padx=2)

        # ---- 命令输入（多行） ----
        tk.Label(dlg, text="命令（可多行，将按顺序执行）:", bg=C_APP_BG,
                 fg="#1565c0", font=(FONT, 9), anchor="w").pack(
            fill="x", padx=14, pady=(6, 2))
        txt = tk.Text(dlg, height=8, font=("Consolas", 10),
                      relief="solid", bd=1, wrap="word")
        txt.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        def _set_cmd(c):
            txt.delete("1.0", "end")
            txt.insert("1.0", c)

        # ---- 选项 ----
        of = tk.Frame(dlg, bg=C_APP_BG)
        of.pack(fill="x", padx=14, pady=(0, 4))

        tk.Label(of, text="超时(秒):", bg=C_APP_BG, fg="#1565c0",
                 font=(FONT, 9)).pack(side="left")
        to_var = tk.StringVar(value=str(int(CMD_TIMEOUT)))
        tk.Spinbox(of, from_=1, to=int(CMD_MAX_TIMEOUT), width=6,
                   textvariable=to_var, font=(FONT, 9)).pack(side="left", padx=(4, 12))

        notify_var = tk.BooleanVar(value=False)
        tk.Checkbutton(of, text="执行完在被控端弹窗通知",
                       variable=notify_var, bg=C_APP_BG,
                       font=(FONT, 9), activebackground=C_APP_BG).pack(side="left")

        # ---- 提示 ----
        tk.Label(dlg, text=f"默认超时 {int(CMD_TIMEOUT)} 秒，最长 {int(CMD_MAX_TIMEOUT)} 秒",
                 bg=C_APP_BG, fg="#90a4ae", font=(FONT, 8)).pack(pady=(0, 4))

        # ---- 按钮 ----
        br = tk.Frame(dlg, bg=C_APP_BG)
        br.pack(pady=8)
        result = {"cmd": ""}

        def _ok():
            result["cmd"] = txt.get("1.0", "end-1c").strip()
            result["timeout"] = to_var.get().strip()
            result["notify"] = notify_var.get()
            dlg.destroy()

        def _cancel():
            result["cmd"] = ""
            dlg.destroy()

        tk.Button(br, text="发送执行", command=_ok,
                  bg="#1565c0", fg="white", relief="flat", bd=0,
                  padx=22, pady=5, font=(FONT, 9),
                  cursor="hand2").pack(side="left", padx=6)
        tk.Button(br, text="取消", command=_cancel,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=22, pady=5, font=(FONT, 9),
                  cursor="hand2").pack(side="left", padx=6)

        txt.focus_set()
        dlg.wait_window()

        cmd = result.get("cmd", "")
        if not cmd:
            return

        try:
            timeout = float(result.get("timeout", "") or CMD_TIMEOUT)
        except Exception:
            timeout = CMD_TIMEOUT

        self.nb.select(self.page_console)
        self._append_console(f"{self._prompt()}{cmd}\n")
        self._cmd_busy(True)
        threading.Thread(
            target=self._runcmd_worker,
            args=(cmd, timeout, result.get("notify", False)),
            daemon=True).start()

    def _runcmd_worker(self, cmd: str, timeout: float, want_notify: bool):
        """「发送命令」的执行线程（比命令栏多了"执行完弹窗"选项）"""
        wait = min(max(timeout, CMD_TIMEOUT), CMD_MAX_TIMEOUT) + 15
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=10)
            sock.settimeout(wait)
            send_all(sock, encode(make_runcmd_request(
                cmd, timeout, want_notify, title="远程命令已执行")))
            data = recv_all(sock, timeout=wait)
            sock.close()
            if not data:
                self._append_console("✗ (被控端无响应)\n\n")
                return
            resp = decode(data)
            cwd = resp.get("cwd", "")
            if cwd:
                self._remote_cwd = cwd
            out = resp.get("output", "")
            prefix = "✓ " if resp.get("ok") else "✗ "
            extra = ""
            if want_notify:
                extra = "\n（已在被控端弹窗通知）" if resp.get("notified") \
                    else "\n（弹窗通知失败：被控端无显示环境）"
            self._append_console(prefix + out + extra + "\n\n")
        except Exception as e:
            self._append_console(f"✗ 执行失败: {type(e).__name__}: {e}\n\n")
        finally:
            self.win.after(0, lambda: self._cmd_busy(False))

    def act_send_message(self):
        """
        「发送消息」按钮：弹对话框写消息 → 在被控端右下角弹出通知。

        弹窗从屏幕右下角向上滑入，多条消息自下而上堆叠，
        默认 8 秒后自动消失（可设 0 = 不自动消失，需手动点掉）。
        """
        dlg = tk.Toplevel(self.win)
        dlg.title("发送消息（被控端弹窗）")
        dlg.configure(bg=C_APP_BG)
        dlg.resizable(False, False)
        dlg.transient(self.win)
        dlg.grab_set()

        try:
            self.win.update_idletasks()
            px = self.win.winfo_x() + (self.win.winfo_width() - 470) // 2
            py = self.win.winfo_y() + (self.win.winfo_height() - 400) // 2
            dlg.geometry(f"470x400+{max(0, px)}+{max(0, py)}")
        except Exception:
            dlg.geometry("470x400")

        tk.Label(dlg, text="发送消息到被控端桌面", bg=C_APP_BG, fg="#1565c0",
                 font=(FONT, 10, "bold")).pack(pady=(10, 8))

        # 标题
        r1 = tk.Frame(dlg, bg=C_APP_BG)
        r1.pack(fill="x", padx=16, pady=4)
        tk.Label(r1, text="标题:", bg=C_APP_BG, fg="#1565c0", font=(FONT, 9),
                 width=6, anchor="w").pack(side="left")
        title_var = tk.StringVar(value="来自控制端的消息")
        tk.Entry(r1, textvariable=title_var, font=(FONT, 9),
                 relief="solid", bd=1).pack(side="left", fill="x", expand=True)

        # 内容
        r2 = tk.Frame(dlg, bg=C_APP_BG)
        r2.pack(fill="both", expand=True, padx=16, pady=4)
        tk.Label(r2, text="内容:", bg=C_APP_BG, fg="#1565c0", font=(FONT, 9),
                 width=6, anchor="nw").pack(side="left")
        txt = tk.Text(r2, height=7, font=(FONT, 9), relief="solid", bd=1,
                      wrap="word")
        txt.pack(side="left", fill="both", expand=True)

        # 快捷短语
        r3 = tk.Frame(dlg, bg=C_APP_BG)
        r3.pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(r3, text="常用:", bg=C_APP_BG, fg="#90a4ae", font=(FONT, 8),
                 width=6, anchor="w").pack(side="left")
        for phrase in ["请注意课堂纪律", "请打开课本第 30 页",
                       "还有 5 分钟下课", "请提交作业"]:
            tk.Button(r3, text=phrase,
                      command=lambda p=phrase: (txt.delete("1.0", "end"),
                                                txt.insert("1.0", p)),
                      bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                      padx=6, pady=2, font=(FONT, 8),
                      cursor="hand2").pack(side="left", padx=2)

        # 选项：级别 + 停留时长
        r4 = tk.Frame(dlg, bg=C_APP_BG)
        r4.pack(fill="x", padx=16, pady=4)
        tk.Label(r4, text="样式:", bg=C_APP_BG, fg="#1565c0", font=(FONT, 9),
                 width=6, anchor="w").pack(side="left")
        level_var = tk.StringVar(value="info")
        for label, val, color in (("普通", "info", "#1565c0"),
                                  ("提醒", "warn", "#ef6c00"),
                                  ("警告", "error", "#c62828")):
            tk.Radiobutton(r4, text=label, variable=level_var, value=val,
                           bg=C_APP_BG, fg=color, font=(FONT, 9),
                           activebackground=C_APP_BG,
                           selectcolor=C_APP_BG).pack(side="left", padx=4)

        r5 = tk.Frame(dlg, bg=C_APP_BG)
        r5.pack(fill="x", padx=16, pady=(0, 2))
        tk.Label(r5, text="停留:", bg=C_APP_BG, fg="#1565c0", font=(FONT, 9),
                 width=6, anchor="w").pack(side="left")
        to_var = tk.StringVar(value="8")
        tk.Spinbox(r5, from_=0, to=120, width=5, textvariable=to_var,
                   font=(FONT, 9)).pack(side="left")
        tk.Label(r5, text="秒（0 = 不自动消失，需手动点掉）",
                 bg=C_APP_BG, fg="#90a4ae", font=(FONT, 8)).pack(side="left", padx=6)

        # 说明
        tk.Label(dlg, text="弹窗从被控端屏幕右下角向上滑入，多条消息自下而上堆叠",
                 bg=C_APP_BG, fg="#90a4ae", font=(FONT, 8)).pack(pady=(4, 0))

        # 按钮
        br = tk.Frame(dlg, bg=C_APP_BG)
        br.pack(pady=10)
        result = {"text": ""}

        def _ok():
            result["text"] = txt.get("1.0", "end-1c").strip()
            result["title"] = title_var.get().strip() or "消息"
            result["level"] = level_var.get()
            try:
                result["timeout"] = float(to_var.get().strip() or 8)
            except Exception:
                result["timeout"] = 8.0
            dlg.destroy()

        def _cancel():
            result["text"] = ""
            dlg.destroy()

        tk.Button(br, text="发送", command=_ok,
                  bg="#1565c0", fg="white", relief="flat", bd=0,
                  padx=24, pady=5, font=(FONT, 9),
                  cursor="hand2").pack(side="left", padx=6)
        tk.Button(br, text="取消", command=_cancel,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=24, pady=5, font=(FONT, 9),
                  cursor="hand2").pack(side="left", padx=6)

        txt.focus_set()
        dlg.wait_window()

        text = result.get("text", "")
        if not text:
            return

        threading.Thread(
            target=self._send_msg_worker,
            args=(result.get("title", "消息"), text,
                  result.get("timeout", 8.0), result.get("level", "info")),
            daemon=True).start()

    def _send_msg_worker(self, title, text, timeout, level):
        """后台线程：让被控端弹通知，结果回显到控制台"""
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=10)
            sock.settimeout(10)
            send_all(sock, encode(make_message_request(
                title, text, sender="控制端", timeout=timeout, level=level)))
            data = recv_all(sock, timeout=10)
            sock.close()
            if not data:
                self._append_console("✗ 发送消息失败: 被控端无响应\n\n")
                return
            resp = decode(data)
            ok = resp.get("ok", False)
            shown = resp.get("shown", False)
            prefix = "✓ " if ok else "✗ "
            line = f"{prefix}发送消息「{title}」: {resp.get('message', '')}"
            self._append_console(line + "\n\n")
            if not ok:
                self.win.after(0, lambda: messagebox.showerror(
                    "发送失败", resp.get("message", ""), parent=self.win))
        except Exception as e:
            self._append_console(f"✗ 发送消息失败: {type(e).__name__}: {e}\n\n")

    def act_start_monitor(self):
        """
        开始屏幕监控: 30 FPS 实时拉帧。
        实现要点:
          - 复用【一条长连接】循环收发，避免每帧 TCP 握手（30FPS 必须）
          - 后台线程收发，拿到帧后用 after() 回主线程更新 UI（Tk 线程安全）
          - 自适应节流: 若一帧耗时已超过目标间隔，就不再额外 sleep，
            防止请求堆积导致延迟累积
        """
        if getattr(self, "_monitoring", False):
            return
        # 注意: 这里【不再】调用 nb.select() —— 由 _on_tab_changed 触发进来时
        # 已经在该页了，再 select 会重复触发事件，甚至递归。
        self._monitoring = True
        self._frame_count = 0
        self._fps = 0.0
        try:
            self.screen_hint.config(text="正在连接…")
        except Exception:
            pass

        t = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread = t
        t.start()

    def _monitor_loop(self):
        """后台线程: 30FPS 循环拉帧（长连接）"""
        import io
        import base64
        import socket
        try:
            from PIL import Image
        except Exception as e:
            self._monitoring = False
            self.win.after(0, lambda: self._show_error(f"缺少 Pillow，无法解码画面: {e}"))
            return

        # 建立长连接
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=5)
            sock.settimeout(SOCKET_TIMEOUT)
        except Exception as e:
            self._monitoring = False
            self.win.after(0, lambda: self._show_error(f"连接 {self.ip}:{self.port} 失败\n{e}"))
            return

        interval = 1.0 / TARGET_FPS      # 目标帧间隔
        self._sock = sock
        self._fps_t0 = time.time()       # FPS 统计起点
        self._fps_n0 = 0                 # 统计起点时的帧号

        try:
            while self._monitoring:
                t0 = time.time()
                try:
                    # 请求一帧（原始分辨率，quality 可调以省带宽）
                    req = make_screen_request(0, 0, FRAME_QUALITY)
                    send_all(sock, encode(req))

                    # 收响应（decode 需要 4 字节长度头 + 负载）
                    data = recv_all(sock, timeout=SOCKET_TIMEOUT)
                    if not data:
                        break
                    resp = decode(data)
                    if resp.get("type") != "screen_res":
                        continue
                    b64 = resp.get("frame", "")
                    if not b64:
                        continue

                    jpeg = base64.b64decode(b64)
                    img = Image.open(io.BytesIO(jpeg)).convert("RGB")

                    # 回主线程更新 UI
                    self.win.after(0, lambda im=img: self.update_frame(im))

                    self._frame_count += 1
                    # 每累计 30 帧统计一次实际 FPS（滑动窗口，反映真实吞吐）
                    if self._frame_count - self._fps_n0 >= 30:
                        dt = time.time() - self._fps_t0
                        if dt > 0:
                            self._fps = (self._frame_count - self._fps_n0) / dt
                        self._fps_t0 = time.time()
                        self._fps_n0 = self._frame_count
                except socket.timeout:
                    continue
                except Exception as e:
                    if self._monitoring:
                        print(f"[会话] 拉帧异常: {e}")
                    break

                # 帧率控制: 扣掉本帧耗时，剩余时间才 sleep
                elapsed = time.time() - t0
                remain = interval - elapsed
                if remain > 0:
                    time.sleep(remain)
        finally:
            try:
                sock.close()
            except Exception:
                pass
            self._monitoring = False

    def _show_error(self, msg: str):
        try:
            self.screen_hint.config(text=f"⚠ {msg}")
        except Exception:
            pass

    def act_stop_monitor(self):
        self._monitoring = False
        # 主动关 socket，让阻塞中的 recv 立刻返回，线程快速退出
        try:
            s = getattr(self, "_sock", None)
            if s:
                s.close()
                self._sock = None
        except Exception:
            pass
        try:
            self.screen_hint.config(text="正在连接…")
            # 恢复占位提示可见（下次切回来时会重新盖上画面）
            self.screen_canvas.itemconfig(self.screen_hint_id, state="normal")
            self.screen_canvas.delete("frame")
            self.screen_canvas.delete("hud")
        except Exception:
            pass

    def act_process_manage(self):
        """「进程管理」按钮：切到进程列表页并自动载入"""
        self.nb.select(self.page_process)
        self.proc_refresh()

    # ---------- 控制台页（命令 + 日志 双视图，共用一块显示区） ----------

    VIEW_CMD = "cmd"
    VIEW_LOG = "log"

    def _build_console_page(self) -> tk.Frame:
        """
        控制台页：顶部切换「命令 / 被控端日志」，共用同一个终端文本框。

        这样命令输出和 agent.log 都能在一个终端里看，来回切换不丢内容
        （每个视图各自缓存自己的文本）。
        """
        page = tk.Frame(self.nb, bg="white")
        self.nb.add(page, text="控制台")

        self._console_view = self.VIEW_CMD
        self._console_buf = {self.VIEW_CMD: "", self.VIEW_LOG: ""}

        # ---- 顶部切换栏 ----
        bar = tk.Frame(page, bg="white")
        bar.pack(fill="x", padx=6, pady=(6, 2))

        self._btn_view_cmd = tk.Button(
            bar, text="💻 命令", command=lambda: self._switch_console(self.VIEW_CMD),
            bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
            padx=14, pady=4, font=(FONT, 9), cursor="hand2")
        self._btn_view_cmd.pack(side="left")

        self._btn_view_log = tk.Button(
            bar, text="📄 被控端日志", command=lambda: self._switch_console(self.VIEW_LOG),
            bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
            padx=14, pady=4, font=(FONT, 9), cursor="hand2")
        self._btn_view_log.pack(side="left", padx=(4, 0))

        # 右侧操作按钮（随视图变化）
        self._console_action_frame = tk.Frame(bar, bg="white")
        self._console_action_frame.pack(side="right")

        tk.Button(self._console_action_frame, text="清空",
                  command=self._console_clear,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=12, pady=3, font=(FONT, 8),
                  cursor="hand2").pack(side="right")
        self._btn_log_refresh = tk.Button(
            self._console_action_frame, text="刷新日志",
            command=self.act_view_log,
            bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
            padx=12, pady=3, font=(FONT, 8), cursor="hand2")

        # ---- 常用命令（仅命令视图显示） ----
        self._console_quick = tk.Frame(page, bg="white")
        self._console_quick.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(self._console_quick, text="常用:", bg="white",
                 fg="#90a4ae", font=(FONT, 8)).pack(side="left")
        presets = [
            ("ipconfig / ifconfig", "ipconfig" if _IS_WIN else "ifconfig"),
            ("系统信息", "systeminfo" if _IS_WIN else "uname -a"),
            ("当前目录", "cd"),
            ("进程列表", "tasklist" if _IS_WIN else "ps aux"),
        ]
        for label, real in presets:
            tk.Button(self._console_quick, text=label,
                      command=lambda c=real: self._quick_cmd(c),
                      bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                      padx=8, pady=2, font=(FONT, 8),
                      cursor="hand2").pack(side="left", padx=2)

        # ---- 终端文本框（共用一个） ----
        term = tk.Frame(page, bg="white")
        term.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        self._console_text = tk.Text(
            term, wrap="none", bg="#0d1b33", fg="#c8e6c9",
            insertbackground="#c8e6c9", font=("Consolas", 9),
            relief="flat", bd=0)
        sb = tk.Scrollbar(term, command=self._console_text.yview)
        self._console_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._console_text.pack(side="left", fill="both", expand=True,
                                padx=(6, 0))

        # ---- 底部状态 ----
        self._console_hint = tk.Label(
            page,
            text="在此执行命令并查看输出   ·   切换「被控端日志」看 agent.log",
            bg="white", fg="#90a4ae", font=(FONT, 8), anchor="w")
        self._console_hint.pack(fill="x", padx=8, pady=(0, 6))

        # 初始：命令视图 + 就绪提示（页面一打开就是可用的终端）
        self._apply_console_view()
        self._set_console_text(
            "远程控制台已就绪。\n"
            "在上方「命令」输入框输入命令，回车或点「执行」即可在被控端运行。\n"
            "内置指令: SAFE_MODE_STATUS / SAFE_MODE_OFF / SAFE_MODE_ON\n\n")
        return page

    def _switch_console(self, view: str):
        """切换控制台视图（命令 / 日志）"""
        if view == self._console_view:
            if view == self.VIEW_LOG:
                self.act_view_log()      # 已在日志视图再点 → 刷新
            return
        # 先存住当前视图内容
        # 注意: 不保存"正在读取…"这类临时提示，否则日志还没拉回来就被切走时，
        #       缓冲区会被临时文案覆盖（真正日志到位后会再写回，但中间态会闪错内容）
        cur = self._get_console_text()
        if "正在读取" not in cur:
            self._console_buf[self._console_view] = cur
        self._console_view = view
        self._apply_console_view()

        if view == self.VIEW_LOG:
            if self._console_buf.get(self.VIEW_LOG, "").strip():
                self._set_console_text(self._console_buf[self.VIEW_LOG])
            else:
                self.act_view_log()      # 首次切过去自动拉一次
        else:
            self._set_console_text(self._console_buf.get(self.VIEW_CMD, ""))

    def _apply_console_view(self):
        """根据当前视图刷新按钮高亮与可见元素"""
        is_cmd = (self._console_view == self.VIEW_CMD)
        try:
            self._btn_view_cmd.configure(
                bg=("#1565c0" if is_cmd else BTN_BG),
                fg=("white" if is_cmd else BTN_FG))
            self._btn_view_log.configure(
                bg=(BTN_BG if is_cmd else "#1565c0"),
                fg=(BTN_FG if is_cmd else "white"))
            if is_cmd:
                self._console_quick.pack(fill="x", padx=6, pady=(0, 4))
                self._btn_log_refresh.pack_forget()
            else:
                self._console_quick.pack_forget()
                self._btn_log_refresh.pack(side="right", padx=(0, 6))
            self._console_hint.configure(
                text=("在此执行命令并查看输出   ·   切换「被控端日志」看 agent.log"
                      if is_cmd else
                      "被控端 agent.log 末尾内容   ·   点「刷新日志」重新拉取"))
        except Exception:
            pass

    def _get_console_text(self) -> str:
        """读取当前文本框内容（不含 Tk 自动补的末尾换行）"""
        try:
            t = self._console_text
            v = t.get("1.0", "end-1c")
            return v
        except Exception:
            return ""

    def _set_console_text(self, text: str):
        """主线程安全地替换文本框内容"""
        def _do():
            try:
                t = self._console_text
                t.configure(state="normal")
                t.delete("1.0", "end")
                t.insert("1.0", text)
                t.configure(state="disabled")
                t.see("end")
            except Exception:
                pass

        try:
            self.win.after(0, _do)
        except Exception:
            _do()

    def _append_console(self, text: str):
        """追加到当前视图；若当前在日志视图，先切回命令视图再追加"""
        # 命令输出永远写进命令视图（避免把命令回显混进日志内容）
        if self._console_view == self.VIEW_LOG:
            self._console_buf[self.VIEW_LOG] = self._get_console_text()
            self._console_view = self.VIEW_CMD
            self._apply_console_view()
            self._set_console_text(self._console_buf.get(self.VIEW_CMD, ""))
        self._console_buf[self.VIEW_CMD] += text

        def _do():
            try:
                t = self._console_text
                t.configure(state="normal")
                t.insert("end", text)
                t.see("end")
                t.configure(state="disabled")
            except Exception:
                pass

        try:
            self.win.after(0, _do)
        except Exception:
            _do()

    def _console_clear(self):
        """清空当前视图"""
        self._console_buf[self._console_view] = ""
        self._set_console_text("")

    # ---- 日志 ----

    def act_view_log(self):
        """「查看日志」按钮 / 切到日志视图：拉取被控端 agent.log"""
        try:
            self.nb.select(self.page_console)
        except Exception:
            pass
        if self._console_view != self.VIEW_LOG:
            self._console_buf[self._console_view] = self._get_console_text()
            self._console_view = self.VIEW_LOG
            self._apply_console_view()

        self._set_console_text("正在读取被控端日志…\n")
        threading.Thread(target=self._fetch_log_worker, daemon=True).start()

    def _set_log_text(self, text: str):
        """兼容性保留：写入日志视图"""
        self._console_buf[self.VIEW_LOG] = text
        if self._console_view == self.VIEW_LOG:
            self._set_console_text(text)

    def _ensure_log_view(self):
        """兼容旧调用：日志视图已随控制台页一起建好，无需再重建"""
        return

    def _ensure_console_view(self):
        """兼容旧调用：控制台页一开始就是真实视图，无需延迟创建"""
        if self._console_view != self.VIEW_CMD:
            self._switch_console(self.VIEW_CMD)

    def _fetch_log_worker(self):
        """后台线程：向被控端拉日志"""
        text = self.controller_ref.fetch_agent_log(self.machine, lines=300) \
            if getattr(self, "controller_ref", None) else None
        if text is None:
            text = self._fetch_log_direct()
        self._set_log_text(text)

    def _fetch_log_direct(self):
        """无 controller 引用时，自己建连接拉日志"""
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=5)
            sock.settimeout(5)
            send_all(sock, encode({"type": "log_req", "lines": 300}))
            data = recv_all(sock, timeout=5)
            sock.close()
            if not data:
                return "(被控端无响应)"
            resp = decode(data)
            return resp.get("log", "(空日志)")
        except Exception as e:
            return f"(读取失败: {type(e).__name__}: {e})\n目标: {self.ip}:{self.port}"

    def act_open_url(self):
        """
        「打开网址」按钮：弹对话框输入网址，在被控端浏览器打开。

        支持:
          - 直接输网址，不带协议会自动补 https://
          - 可选指定浏览器（Chrome / Edge / Firefox / IE）
          - 最近 10 条历史，下拉可选
        """
        from tkinter import simpledialog

        dlg = tk.Toplevel(self.win)
        dlg.title("打开网址（被控端）")
        dlg.configure(bg=C_APP_BG)
        dlg.resizable(False, False)
        dlg.transient(self.win)
        dlg.grab_set()

        # 居中到父窗口
        try:
            self.win.update_idletasks()
            px = self.win.winfo_x() + (self.win.winfo_width() - 470) // 2
            py = self.win.winfo_y() + (self.win.winfo_height() - 220) // 2
            dlg.geometry(f"470x220+{max(0, px)}+{max(0, py)}")
        except Exception:
            dlg.geometry("470x220")

        tk.Label(dlg, text="在被控端浏览器中打开网址",
                 bg=C_APP_BG, fg="#1565c0",
                 font=(FONT, 10, "bold")).pack(pady=(12, 8))

        # 网址输入
        row1 = tk.Frame(dlg, bg=C_APP_BG)
        row1.pack(fill="x", padx=16, pady=4)
        tk.Label(row1, text="网址:", bg=C_APP_BG, fg="#1565c0",
                 font=(FONT, 9), width=6, anchor="w").pack(side="left")
        url_var = tk.StringVar()
        entry = tk.Entry(row1, textvariable=url_var, font=(FONT, 9),
                         relief="solid", bd=1)
        entry.pack(side="left", fill="x", expand=True)

        # 浏览器选择
        row2 = tk.Frame(dlg, bg=C_APP_BG)
        row2.pack(fill="x", padx=16, pady=4)
        tk.Label(row2, text="浏览器:", bg=C_APP_BG, fg="#1565c0",
                 font=(FONT, 9), width=6, anchor="w").pack(side="left")
        browser_var = tk.StringVar(value="")
        choices = ["默认浏览器"] + [b for b in
                                   ("chrome", "edge", "firefox", "ie")]
        bcombo = ttk.Combobox(row2, textvariable=browser_var,
                              values=choices, state="readonly",
                              width=14, font=(FONT, 9))
        bcombo.set("默认浏览器")
        bcombo.pack(side="left")
        tk.Label(row2, text="（指定浏览器需被控端已安装）",
                 bg=C_APP_BG, fg="#90a4ae", font=(FONT, 8)).pack(
            side="left", padx=(8, 0))

        # 历史
        hist = getattr(self, "_url_history", [])
        if hist:
            row3 = tk.Frame(dlg, bg=C_APP_BG)
            row3.pack(fill="x", padx=16, pady=(2, 0))
            tk.Label(row3, text="最近:", bg=C_APP_BG, fg="#90a4ae",
                     font=(FONT, 8), width=6, anchor="w").pack(side="left")
            hcombo = ttk.Combobox(row3, values=hist, state="readonly",
                                  width=40, font=(FONT, 8))
            hcombo.pack(side="left", fill="x", expand=True)
            hcombo.bind("<<ComboboxSelected>>",
                        lambda e: url_var.set(hcombo.get()))

        # 提示
        tk.Label(dlg, text="不带协议会自动补 https://  ·  仅支持 http/https/ftp/mailto/file",
                 bg=C_APP_BG, fg="#90a4ae", font=(FONT, 8)).pack(pady=(6, 0))

        # 按钮
        btnrow = tk.Frame(dlg, bg=C_APP_BG)
        btnrow.pack(pady=14)

        result = {"url": ""}

        def _ok():
            result["url"] = url_var.get().strip()
            result["browser"] = "" if browser_var.get() == "默认浏览器" \
                else browser_var.get()
            dlg.destroy()

        def _cancel():
            result["url"] = ""
            dlg.destroy()

        tk.Button(btnrow, text="打开", command=_ok,
                  bg="#1565c0", fg="white", relief="flat", bd=0,
                  padx=24, pady=5, font=(FONT, 9),
                  cursor="hand2").pack(side="left", padx=6)
        tk.Button(btnrow, text="取消", command=_cancel,
                  bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                  padx=24, pady=5, font=(FONT, 9),
                  cursor="hand2").pack(side="left", padx=6)

        entry.bind("<Return>", lambda e: _ok())
        entry.focus_set()
        dlg.wait_window()

        url = result.get("url", "")
        if not url:
            return

        # 记历史（去重，最多 10 条）
        if not hasattr(self, "_url_history"):
            self._url_history = []
        if url in self._url_history:
            self._url_history.remove(url)
        self._url_history.insert(0, url)
        self._url_history = self._url_history[:10]

        browser = result.get("browser", "")
        threading.Thread(target=self._open_url_worker,
                         args=(url, browser), daemon=True).start()

    def _open_url_worker(self, url: str, browser: str = ""):
        """后台线程：让被控端打开网址，结果回显到控制台"""
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=10)
            sock.settimeout(10)
            send_all(sock, encode(make_open_url_request(url, browser)))
            data = recv_all(sock, timeout=10)
            sock.close()
            if not data:
                self._append_console("✗ 打开网址失败: 被控端无响应\n\n")
                return
            resp = decode(data)
            ok = resp.get("ok", False)
            msg = resp.get("message", "")
            used = resp.get("browser", "")
            prefix = "✓ " if ok else "✗ "
            line = f"{prefix}打开网址: {msg}"
            if used:
                line += f"  [{used}]"
            self._append_console(line + "\n\n")
            if not ok:
                self.win.after(0, lambda: messagebox.showerror(
                    "打开失败", msg, parent=self.win))
        except Exception as e:
            err = f"✗ 打开网址失败: {type(e).__name__}: {e}\n\n"
            self._append_console(err)

    def _quick_cmd(self, cmd: str):
        """快捷按钮：填入命令栏并立即执行"""
        try:
            self.cmd_var.set(cmd)
        except Exception:
            pass
        self.act_execute()

    def _cmd_history_up(self, event=None):
        """↑ 上一条命令"""
        if not getattr(self, "_cmd_history", None):
            return "break"
        if self._cmd_hist_idx < len(self._cmd_history) - 1:
            self._cmd_hist_idx += 1
            self.cmd_var.set(self._cmd_history[self._cmd_hist_idx])
            self.cmd_entry.icursor("end")
        return "break"

    def _cmd_history_down(self, event=None):
        """↓ 下一条命令"""
        if not getattr(self, "_cmd_history", None):
            return "break"
        if self._cmd_hist_idx > 0:
            self._cmd_hist_idx -= 1
            self.cmd_var.set(self._cmd_history[self._cmd_hist_idx])
        elif self._cmd_hist_idx == 0:
            self._cmd_hist_idx = -1
            self.cmd_var.set("")
        self.cmd_entry.icursor("end")
        return "break"

    def act_execute(self):
        """「执行」按钮 / 回车：把命令栏内容发给被控端"""
        try:
            cmd = self.cmd_var.get().strip()
        except Exception:
            cmd = ""
        if not cmd:
            messagebox.showwarning("提示", "请先输入命令", parent=self.win)
            return

        # 记入历史（连续的重复命令不重复记录）
        if not self._cmd_history or self._cmd_history[0] != cmd:
            self._cmd_history.insert(0, cmd)
            self._cmd_history = self._cmd_history[:50]   # 最多留 50 条
        self._cmd_hist_idx = -1

        self.nb.select(self.page_console)
        self._ensure_console_view()
        self._append_console(f"{self._prompt()}{cmd}\n")
        self.cmd_var.set("")          # 清空输入框
        self._cmd_busy(True)
        threading.Thread(target=self._cmd_worker,
                         args=(cmd,), daemon=True).start()

    def _prompt(self) -> str:
        """控制台提示符，形如 C:\\Users\\Student> """
        cwd = getattr(self, "_remote_cwd", "") or ""
        return f"{cwd}> " if cwd else "> "

    def _cmd_busy(self, busy: bool):
        """命令执行中：输入框置灰 + 提示，避免重复提交"""
        try:
            if busy:
                self.cmd_entry.configure(state="disabled",
                                         disabledbackground="#eceff1")
                self._append_console("(执行中…)\n")
            else:
                self.cmd_entry.configure(state="normal")
                self.cmd_entry.focus_set()
        except Exception:
            pass

    def _cmd_worker(self, cmd: str):
        """后台线程：把命令发给被控端并显示回显"""
        # 命令可能跑满 30 秒，这里的超时必须比被控端的大
        wait = CMD_MAX_TIMEOUT + 10
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=10)
            sock.settimeout(wait)
            send_all(sock, encode(make_command_request(cmd)))
            data = recv_all(sock, timeout=wait)
            sock.close()
            if not data:
                self._append_console("✗ (被控端无响应)\n\n")
                return
            resp = decode(data)
            # 更新提示符用的远端 cwd
            cwd = resp.get("cwd", "")
            if cwd:
                self._remote_cwd = cwd
            out = resp.get("output", "")
            prefix = "✓ " if resp.get("ok") else "✗ "
            self._append_console(prefix + out + "\n\n")
        except Exception as e:
            self._append_console(f"✗ 执行失败: {type(e).__name__}: {e}\n\n")
        finally:
            self.win.after(0, lambda: self._cmd_busy(False))

    # ---------- 预留接口：供后续接入真实画面 ----------

    def update_frame(self, pil_image):
        """
        更新屏幕监控页画面（30FPS 由 _monitor_loop 调用）。
        按画布尺寸等比缩放，保持画面不变形。
        """
        try:
            from PIL import ImageTk, Image
            cw = max(1, self.screen_canvas.winfo_width())
            ch = max(1, self.screen_canvas.winfo_height())

            # 等比缩放，居中留边（不变形）
            iw, ih = pil_image.size
            if iw <= 0 or ih <= 0:
                return
            scale = min(cw / iw, ch / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            # 30FPS 场景: 用 BILINEAR 而非 LANCZOS，速度更快、画质足够
            if (nw, nh) != (iw, ih):
                from PIL import Image as _PILImage
                pil_image = pil_image.resize((nw, nh), _PILImage.BILINEAR)

            photo = ImageTk.PhotoImage(pil_image)
            self.screen_canvas.delete("frame")
            # 居中放置
            ox, oy = (cw - nw) // 2, (ch - nh) // 2
            self.screen_canvas.create_image(ox, oy, anchor="nw",
                                            image=photo, tags="frame")
            self.screen_canvas._photo = photo   # 防 GC（关键！）

            # 记录坐标变换参数：键鼠控制需要把画布坐标还原成被控端原始坐标
            self._scale = scale
            self._offx = ox
            self._offy = oy
            self._remote_w = iw
            self._remote_h = ih

            # 隐藏占位提示（用 state hidden，比 place_forget 更可靠）
            try:
                self.screen_canvas.itemconfig(self.screen_hint_id, state="hidden")
            except Exception:
                pass

            # 左上角显示实时 FPS
            fps = getattr(self, "_fps", 0.0)
            n = getattr(self, "_frame_count", 0)
            self.screen_canvas.delete("hud")
            self.screen_canvas.create_text(
                8, 8, anchor="nw", tags="hud",
                text=f"● 监控中  {fps:.0f} FPS  第{n}帧",
                fill="#69f0ae", font=(FONT, 9, "bold"))
        except Exception as e:
            print(f"[会话] 画面更新失败: {e}")

    def close(self):
        """关闭窗口（停止监控线程、断开控制连接等清理）"""
        self._monitoring = False
        # 主动关 socket，让阻塞中的 recv 立即返回，线程快速退出
        for attr in ("_sock", "_ctrl_sock"):
            try:
                s = getattr(self, attr, None)
                if s:
                    s.close()
            except Exception:
                pass
        try:
            self.win.destroy()
        except Exception:
            pass


def open_session(master: tk.Misc, machine, controller=None) -> SessionWindow:
    """便捷入口：打开一个设备详情窗口"""
    return SessionWindow(master, machine, controller=controller)
