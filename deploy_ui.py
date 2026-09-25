# -*- coding: utf-8 -*-
"""
deploy_ui.py - 「一键部署」对话框（主控端）

把同目录下的被控端 exe（agent.exe / 被控端.exe）批量装到指定 IP 的电脑上，
远程执行由同目录的 jcc.exe 完成:
    jcc.exe -ip [ip] -c [command]
    ip 支持单个(192.168.80.12)或范围(192.168.80.10-56)

界面: 与主控制台一致的蓝色主题
  - 顶部蓝色标题栏 + 关闭按钮
  - 目标 IP（支持逗号/分号/换行分隔、常用网段快捷填入）
  - 部署文件选择（默认自动探测同目录）
  - 目标目录 / 文件名 / 是否部署后启动
  - 并发数 / 超时
  - 进度表: 每台机器一行，实时显示 阶段(建目录/下载/启动) 与结果
  - 底部状态栏 + 一键部署/停止/关闭

对外入口:
    from deploy_ui import open_deploy_dialog
    open_deploy_dialog(controller_root)
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from deploy import (
    Deployer, DeployResult,
    parse_ip_spec, summarize,
    DEFAULT_REMOTE_DIR, DEFAULT_TARGET_NAME,
    DEFAULT_TIMEOUT, DEFAULT_WORKERS,
    local_subnet_prefix, get_local_ip,
)

# ============ 蓝色主题（与 controller.py 完全一致）============
C_TITLEBAR    = "#1565c0"
C_TITLEBAR_FG = "#e3f2fd"
C_APP_BG      = "#f5f9ff"
C_ACCENT      = "#42a5f5"
C_BTN_BG      = "#1565c0"
C_BTN_FG      = "#ffffff"
C_BTN_LIGHT   = "#e3f2fd"
C_BTN_HOVER   = "#1976d2"
C_TEXT        = "#37474f"
C_MUTED       = "#78909c"
C_BORDER      = "#c8d7ea"
C_GROUP_BG    = "#eef5ff"
C_INPUT_BG    = "#ffffff"
C_OK          = "#2e7d32"
C_FAIL        = "#c62828"
C_RUN         = "#1565c0"
C_PEND        = "#90a4ae"
C_WARN        = "#e65100"
FONT          = "Microsoft YaHei"

# 阶段 -> 中文显示（保持原顺序：左->右 = 旧->新）
STAGE_TEXT = {
    "待部署": "等待中",
    "建目录": "创建目录",
    "下载":   "下载文件",
    "启动":   "启动服务",
    "完成":   "已完成",
    "失败":   "失败",
    "取消":   "已取消",
}


def _center(parent, win, w, h):
    """在父窗口中心弹出"""
    try:
        parent.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - w) // 2
        py = parent.winfo_y() + (parent.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{max(0, px)}+{max(0, py)}")
    except Exception:
        win.geometry(f"{w}x{h}")


class DeployDialog:
    """「一键部署」对话框"""

    def __init__(self, parent):
        self.parent = parent
        self.deployer = None
        self.results = {}
        self._running = False
        self._poll_job = None

        # ---- 窗口 ----
        self.win = tk.Toplevel(parent)
        self.win.title("一键部署")
        self.win.configure(bg=C_APP_BG)
        self.win.resizable(True, True)
        self.win.minsize(680, 560)
        self.win.transient(parent)
        try:
            self.win.grab_set()
        except Exception:
            pass
        _center(self.win, self.win, 720, 640)
        self._install_icon(self.win)

        self._build_ui()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._auto_detect()

    # ---------------- 窗口图标 ----------------
    def _install_icon(self, win):
        """尽量给窗口贴一个蓝色圆角图标（找不到图片也不报错）"""
        try:
            from PIL import Image, ImageTk
            cache = os.path.join(os.path.dirname(__file__), ".deploy_icon.png")
            if not os.path.isfile(cache):
                img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                d = __import__("PIL").ImageDraw.Draw(img)
                d.ellipse([0, 0, 63, 63], fill=(21, 101, 192, 255))
                d.polygon([(20, 40), (30, 24), (40, 40), (34, 40), (34, 48),
                           (30, 48), (30, 40)], fill=(255, 255, 255, 255))
                img.save(cache)
            self._icon = ImageTk.PhotoImage(file=cache)
            win.iconphoto(True, self._icon)
        except Exception:
            pass

    # ---------------- 界面 ----------------
    def _build_ui(self):
        # ===== 标题栏（与主控端一致）=====
        bar = tk.Frame(self.win, bg=C_TITLEBAR, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="一键部署", bg=C_TITLEBAR, fg=C_TITLEBAR_FG,
                 font=(FONT, 12, "bold"), anchor="w").pack(side="left", padx=14)
        tk.Label(bar, text="通过 jcc.exe 远程执行 · 批量安装被控端",
                 bg=C_TITLEBAR, fg="#bbdefb", font=(FONT, 8)).pack(side="left", padx=6)
        tk.Button(bar, text="✕", command=self._on_close, bg=C_TITLEBAR,
                   fg=C_TITLEBAR_FG, activebackground="#0d47a1",
                   activeforeground="white", relief="flat", bd=0,
                   font=(FONT, 10), cursor="hand2", padx=12).pack(side="right")

        # ===== 内容区 =====
        body = tk.Frame(self.win, bg=C_APP_BG)
        body.pack(fill="both", expand=True, padx=14, pady=10)

        # --- 1. 目标 IP ---
        self._group(body, "目标 IP").pack(fill="x", pady=(0, 8))
        ip_box = tk.Frame(body, bg=C_APP_BG)
        ip_box.pack(fill="x", pady=(0, 8))

        tip = tk.Frame(ip_box, bg=C_APP_BG)
        tip.pack(fill="x", padx=10)
        tk.Label(tip, text="支持: 单个IP (192.168.80.12)、IP范围 (192.168.80.10-56)，多个用逗号或换行分隔",
                 bg=C_APP_BG, fg=C_MUTED, font=(FONT, 8), anchor="w").pack(side="left")
        self._link(tip, "本机网段", self._fill_local).pack(side="right", padx=(4, 10))
        self._link(tip, "全段扫描 1-254", self._fill_full).pack(side="right", padx=4)

        self.ip_text = tk.Text(ip_box, height=3, font=("Consolas", 10),
                               relief="solid", bd=1, wrap="word",
                               highlightbackground=C_BORDER,
                               highlightcolor=C_ACCENT, highlightthickness=1)
        self.ip_text.pack(fill="x", padx=10, pady=(4, 0))
        self.ip_text.insert("1.0", local_subnet_prefix() + "10-56")

        # --- 2. 部署文件 ---
        self._group(body, "部署文件").pack(fill="x", pady=(0, 8))
        f_box = tk.Frame(body, bg=C_APP_BG)
        f_box.pack(fill="x", pady=(0, 8), padx=10)

        self.exe_var = tk.StringVar()
        self.jcc_var = tk.StringVar()
        self._field(f_box, "被控端:", self.exe_var, "选择…", self._pick_exe).pack(fill="x", pady=3)
        self._field(f_box, "jcc.exe:", self.jcc_var, "选择…", self._pick_jcc).pack(fill="x", pady=3)

        self.jcc_state = tk.Label(f_box, text="", bg=C_APP_BG, fg=C_MUTED,
                                   font=(FONT, 8), anchor="w")
        self.jcc_state.pack(fill="x", padx=92, pady=(2, 0))

        # --- 3. 目标位置 ---
        self._group(body, "目标位置").pack(fill="x", pady=(0, 8))
        t_box = tk.Frame(body, bg=C_APP_BG)
        t_box.pack(fill="x", pady=(0, 8), padx=10)

        r = tk.Frame(t_box, bg=C_APP_BG); r.pack(fill="x", pady=3)
        tk.Label(r, text="目录:", bg=C_APP_BG, fg=C_TITLEBAR, font=(FONT, 9),
                 width=8, anchor="w").pack(side="left")
        self.dir_var = tk.StringVar(value=DEFAULT_REMOTE_DIR)
        self._entry(r, self.dir_var, font=(FONT, 9)).pack(side="left", fill="x", expand=True)

        r = tk.Frame(t_box, bg=C_APP_BG); r.pack(fill="x", pady=3)
        tk.Label(r, text="文件名:", bg=C_APP_BG, fg=C_TITLEBAR, font=(FONT, 9),
                 width=8, anchor="w").pack(side="left")
        self.name_var = tk.StringVar(value=DEFAULT_TARGET_NAME)
        self._entry(r, self.name_var, width=20, font=(FONT, 9)).pack(side="left")
        self.start_var = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(r, text="部署后自动启动", variable=self.start_var,
                             bg=C_APP_BG, font=(FONT, 9), fg=C_TEXT,
                             activebackground=C_APP_BG, selectcolor=C_INPUT_BG,
                             cursor="hand2")
        chk.pack(side="left", padx=(14, 0))

        # --- 4. 参数 ---
        self._group(body, "参数").pack(fill="x", pady=(0, 8))
        p_box = tk.Frame(body, bg=C_APP_BG)
        p_box.pack(fill="x", pady=(0, 8), padx=10)
        tk.Label(p_box, text="并发:", bg=C_APP_BG, fg=C_TITLEBAR, font=(FONT, 9)).pack(side="left")
        self.workers_var = tk.StringVar(value=str(DEFAULT_WORKERS))
        self._spin(p_box, self.workers_var, 1, 64, 5).pack(side="left", padx=(6, 16))
        tk.Label(p_box, text="超时(秒):", bg=C_APP_BG, fg=C_TITLEBAR, font=(FONT, 9)).pack(side="left")
        self.timeout_var = tk.StringVar(value=str(int(DEFAULT_TIMEOUT)))
        self._spin(p_box, self.timeout_var, 10, 300, 5).pack(side="left", padx=6)
        tk.Label(p_box, text="（单台每步等待上限）", bg=C_APP_BG, fg=C_MUTED,
                 font=(FONT, 8)).pack(side="left", padx=8)

        # --- 5. 进度 ---
        self._group(body, "部署进度").pack(fill="both", expand=True, pady=(0, 8))
        pg = tk.Frame(body, bg=C_APP_BG)
        pg.pack(fill="both", expand=True, padx=10)

        cols = ("ip", "stage", "detail")
        self.tree = ttk.Treeview(pg, columns=cols, show="headings", height=7)
        self.tree.heading("ip", text="IP 地址")
        self.tree.heading("stage", text="状态")
        self.tree.heading("detail", text="详情")
        self.tree.column("ip", width=130, anchor="w", stretch=False)
        self.tree.column("stage", width=90, anchor="center", stretch=False)
        self.tree.column("detail", width=340, anchor="w")
        sb = tk.Scrollbar(pg, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self._style_tree()
        for tag, color in (("ok", C_OK), ("fail", C_FAIL), ("run", C_RUN),
                           ("pend", C_PEND), ("cancel", C_WARN)):
            self.tree.tag_configure(tag, foreground=color)

        # 汇总
        self.summary = tk.Label(body, text="填写 IP 范围后，点击「开始部署」",
                               bg=C_APP_BG, fg=C_MUTED, font=(FONT, 9), anchor="w")
        self.summary.pack(fill="x", padx=10, pady=(0, 6))

        # --- 按钮 ---
        br = tk.Frame(self.win, bg=C_APP_BG)
        br.pack(fill="x", padx=14, pady=(0, 12))
        self.start_btn = self._big_btn(br, "🚀  开始部署", self.start, primary=True)
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = self._big_btn(br, "⏹  停止", self.stop, primary=False)
        self.stop_btn.pack(side="left", padx=4)
        self.close_btn = self._big_btn(br, "关闭", self._on_close, primary=False)
        self.close_btn.pack(side="right", padx=0)

    # ---------------- 小组件 ----------------
    def _group(self, parent, title):
        """圆角分组标题（占位 Frame，便于后续换成 Canvas）"""
        f = tk.LabelFrame(parent, bg=C_GROUP_BG, fg=C_TITLEBAR,
                          font=(FONT, 9, "bold"), labelanchor="nw",
                          relief="solid", bd=1, padx=2, pady=4)
        # ttk 风格的分隔线标题
        f.configure(font=(FONT, 9, "bold"))
        return f

    def _field(self, parent, label, var, btn_text, cmd):
        """标签 + 输入框 + 选择按钮"""
        r = tk.Frame(parent, bg=C_APP_BG)
        tk.Label(r, text=label, bg=C_APP_BG, fg=C_TITLEBAR, font=(FONT, 9),
                 width=8, anchor="w").pack(side="left")
        self._entry(r, var, font=(FONT, 9)).pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(r, text=btn_text, command=cmd, bg=C_BTN_LIGHT, fg=C_TITLEBAR,
                  activebackground=C_ACCENT, activeforeground="white",
                  relief="flat", bd=0, padx=10, pady=3, font=(FONT, 8),
                  cursor="hand2").pack(side="left")
        return r

    def _entry(self, parent, var, **kw):
        e = tk.Entry(parent, textvariable=var, bg=C_INPUT_BG, fg=C_TEXT,
                     relief="solid", bd=1, insertbackground=C_TEXT, **kw)
        e.configure(highlightbackground=C_BORDER, highlightcolor=C_ACCENT,
                    highlightthickness=1)
        return e

    def _spin(self, parent, var, lo, hi, width):
        return tk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=width,
                          font=(FONT, 9), relief="solid", bd=1,
                          highlightbackground=C_BORDER, highlightthickness=1)

    def _link(self, parent, text, cmd):
        l = tk.Label(parent, text=text, bg=C_APP_BG, fg=C_TITLEBAR,
                     font=(FONT, 8, "underline"), cursor="hand2")
        l.bind("<Button-1>", lambda e: cmd())
        l.bind("<Enter>", lambda e: l.config(fg=C_ACCENT))
        l.bind("<Leave>", lambda e: l.config(fg=C_TITLEBAR))
        return l

    def _big_btn(self, parent, text, cmd, primary):
        if primary:
            b = tk.Button(parent, text=text, command=cmd, bg=C_BTN_BG, fg=C_BTN_FG,
                          activebackground=C_BTN_HOVER, activeforeground="white",
                          relief="flat", bd=0, padx=22, pady=7,
                          font=(FONT, 10, "bold"), cursor="hand2")
        else:
            b = tk.Button(parent, text=text, command=cmd, bg=C_BTN_LIGHT, fg=C_TITLEBAR,
                          activebackground=C_ACCENT, activeforeground="white",
                          relief="flat", bd=0, padx=18, pady=7,
                          font=(FONT, 9), cursor="hand2")
        return b

    def _style_tree(self):
        try:
            s = ttk.Style(self.win)
            s.theme_use("clam")
            s.configure("Treeview", background=C_INPUT_BG, foreground=C_TEXT,
                        fieldbackground=C_INPUT_BG, rowheight=22,
                        font=(FONT, 9), bordercolor=C_BORDER,
                        lightcolor=C_BORDER, darkcolor=C_BORDER)
            s.configure("Treeview.Heading", background=C_BTN_LIGHT, foreground=C_TITLEBAR,
                        font=(FONT, 9, "bold"), relief="flat")
            s.map("Treeview.Heading", background=[("active", "#bbdefb")])
            s.map("Treeview", background=[("selected", "#bbdefb")],
                  foreground=[("selected", C_TEXT)])
        except Exception:
            pass

    # ---------------- 文件探测 ----------------
    def _auto_detect(self):
        exe = Deployer.find_agent_exe()
        if exe:
            self.exe_var.set(exe)
        jcc = Deployer.find_jcc()
        if jcc:
            self.jcc_var.set(jcc)
            self.jcc_state.config(text="✓ 已找到 jcc.exe：" + jcc, fg=C_OK)
        else:
            self.jcc_state.config(
                text="⚠ 未找到 jcc.exe —— 请把它放到程序同目录，或点「选择」指定",
                fg=C_FAIL)

    def _pick(self, var, title):
        p = filedialog.askopenfilename(
            parent=self.win, title=title,
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")])
        if p:
            var.set(p)
            return p
        return None

    def _pick_exe(self):
        if self._pick("被控端程序", self.exe_var):
            self._check_ready()

    def _pick_jcc(self):
        if self._pick("选择 jcc.exe", self.jcc_var):
            self.jcc_state.config(text="✓ 已选择：" + self.jcc_var.get(), fg=C_OK)
        self._check_ready()

    def _fill_local(self):
        self.ip_text.delete("1.0", "end")
        self.ip_text.insert("1.0", local_subnet_prefix() + "10-56")

    def _fill_full(self):
        self.ip_text.delete("1.0", "end")
        self.ip_text.insert("1.0", local_subnet_prefix() + "1-254")

    def _check_ready(self):
        exe = self.exe_var.get().strip()
        jcc = self.jcc_var.get().strip()
        ready = exe and os.path.isfile(exe) and jcc and os.path.isfile(jcc)
        self.start_btn.config(state="normal" if ready else "disabled")

    # ---------------- 部署 ----------------
    def start(self):
        if self._running:
            return

        spec = self.ip_text.get("1.0", "end-1c")
        ips, errors = parse_ip_spec(spec)
        if not ips:
            self._warn("IP 无效", "没有解析到任何有效 IP。\n\n支持格式:\n"
                       "  192.168.80.12\n  192.168.80.10-56\n"
                       "  多个用逗号或换行分隔" +
                       ("\n\n解析错误:\n  " + "\n  ".join(errors[:5]) if errors else ""))
            return

        exe = self.exe_var.get().strip()
        if not exe or not os.path.isfile(exe):
            self._warn("缺少文件", f"找不到被控端程序:\n{exe or '(未选择)'}\n\n"
                                  f"请先打包（build.bat）或手动选择 agent.exe。")
            return

        jcc = self.jcc_var.get().strip()
        if not jcc or not os.path.isfile(jcc):
            self._warn("缺少 jcc.exe", f"找不到 jcc.exe:\n{jcc or '(未选择)'}\n\n"
                                     f"请把 jcc.exe 放到程序同目录，或点「选择」指定。")
            return

        try:
            workers = max(1, int(self.workers_var.get()))
            timeout = max(10, float(self.timeout_var.get()))
        except Exception:
            workers, timeout = DEFAULT_WORKERS, DEFAULT_TIMEOUT

        # 重置进度表
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results = {ip: DeployResult(ip) for ip in ips}
        for ip in ips:
            self.tree.insert("", "end", iid=ip, values=(ip, "等待中", ""), tags=("pend",))

        self.summary.config(
            text=f"共 {len(ips)} 台 · 准备部署…", fg=C_RUN)
        self._set_running_ui(True)

        try:
            self.deployer = Deployer(
                exe_path=exe, jcc_path=jcc,
                remote_dir=self.dir_var.get().strip() or DEFAULT_REMOTE_DIR,
                target_name=self.name_var.get().strip() or DEFAULT_TARGET_NAME,
                timeout=timeout, workers=workers,
                auto_start=self.start_var.get())
            self.deployer.start_http()
        except Exception as e:
            self._error("启动失败", str(e))
            self._set_running_ui(False)
            return

        self._running = True
        self._poll()
        threading.Thread(target=self._worker, args=(ips,),
                         daemon=True, name="一键部署").start()

    def _worker(self, ips):
        try:
            self.deployer.deploy_all(ips)
        except Exception as e:
            print(f"[部署] 异常: {e}")
        finally:
            try:
                if self.deployer:
                    self.deployer.stop_http()
            except Exception:
                pass
            self.win.after(0, self._finished)

    def _poll(self):
        if not self._running:
            return
        try:
            if self.deployer:
                for r in self.deployer.drain_progress():
                    self.results[r.ip] = r
                    stage = STAGE_TEXT.get(r.stage, r.stage)
                    tag = ("ok" if r.ok else
                           "fail" if r.stage in ("失败",) else
                           "cancel" if r.stage == "取消" else
                           "run" if r.stage != "待部署" else "pend")
                    self.tree.item(r.ip, values=(r.ip, stage, (r.detail or "")[:90]),
                                   tags=(tag,))
                    self.tree.see(r.ip)
            n_ok = sum(1 for r in self.results.values() if r.ok)
            n_fail = sum(1 for r in self.results.values() if r.stage in ("失败", "取消"))
            self.summary.config(
                text=f"进行中…  成功 {n_ok}  ·  失败 {n_fail}  ·  共 {len(self.results)}",
                fg=C_RUN)
        except Exception:
            pass
        self._poll_job = self.win.after(200, self._poll)

    def _finished(self):
        self._running = False
        if self._poll_job:
            try:
                self.win.after_cancel(self._poll_job)
            except Exception:
                pass
        self._poll()
        results = list(self.results.values())
        n_ok = sum(1 for r in results if r.ok)
        self.summary.config(
            text=f"完成：成功 {n_ok} / {len(results)}",
            fg=C_OK if n_ok == len(results) else C_WARN)
        self._set_running_ui(False)
        # 弹窗前把结果按 IP 排序，方便核对
        ordered = sorted(results, key=lambda r: r.ip)
        messagebox.showinfo("部署完成", summarize(ordered), parent=self.win)

    def _set_running_ui(self, running):
        self.start_btn.config(state="disabled" if running else "normal")
        self.stop_btn.config(state="normal" if running else "disabled")
        for child in (self.ip_text,):
            try:
                child.config(state="disabled" if running else "normal")
            except Exception:
                pass

    def stop(self):
        if self.deployer:
            self.deployer.cancel()
            self.summary.config(text="正在停止…（已开始的会跑完）", fg=C_MUTED)

    # ---------------- 关闭 ----------------
    def _on_close(self):
        if self._running:
            if not messagebox.askyesno("确认", "部署正在进行中，确定要关闭吗？\n"
                                                     "（已在执行的机器会继续跑完）",
                                       parent=self.win):
                return
            if self.deployer:
                self.deployer.cancel()
        try:
            if self.deployer:
                self.deployer.stop_http()
        except Exception:
            pass
        if self._poll_job:
            try:
                self.win.after_cancel(self._poll_job)
            except Exception:
                pass
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()

    # ---------------- 提示（统一 parent）----------------
    def _warn(self, title, msg):
        messagebox.showwarning(title, msg, parent=self.win)

    def _error(self, title, msg):
        messagebox.showerror(title, msg, parent=self.win)


def open_deploy_dialog(parent):
    """供主控端工具栏调用: from deploy_ui import open_deploy_dialog"""
    if parent is None:
        # 允许独立运行 / 无主窗口场景
        root = tk.Tk()
        root.withdraw()
        DeployDialog(root)
        root.mainloop()
    else:
        DeployDialog(parent)


if __name__ == "__main__":
    # 独立预览（不依赖 controller）
    open_deploy_dialog(None)
