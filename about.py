# -*- coding: utf-8 -*-
"""
about.py - 「关于软件」对话框（主控端）

点主界面工具栏的「关于软件」打开，显示:
  - 软件名称 / 版本
  - 作者
  - 免责声明（重点）
  - 开源协议与合规提示

用法:
    from about import open_about_dialog
    open_about_dialog(controller_root)
"""

import os
import tkinter as tk
from tkinter import messagebox

# ============ 蓝色主题（与 controller.py 一致）============
C_TITLEBAR    = "#1565c0"
C_TITLEBAR_FG = "#e3f2fd"
C_APP_BG      = "#f5f9ff"
C_ACCENT      = "#42a5f5"
C_BTN_BG      = "#1565c0"
C_BTN_FG      = "#ffffff"
C_BTN_LIGHT   = "#e3f2fd"
C_TEXT        = "#37474f"
C_MUTED       = "#78909c"
C_BORDER      = "#c8d7ea"
C_WHITE       = "#ffffff"
C_WARN_BG     = "#fff8e1"
C_WARN_FG     = "#e65100"
C_WARN_BORDER = "#ffb300"
FONT          = "Microsoft YaHei"

# ============ 软件信息 ============
APP_NAME    = "局域网远控 / 电子教室"
APP_VERSION = "v2"
APP_AUTHOR  = "@爱分享的校长"
APP_DESC    = "面向机房 / 教室局域网的远程管理工具"

DISCLAIMER = (
    "本软件仅供学习研究与机房管理使用。\n\n"
    "1. 请务必在自己拥有、或已获得明确授权管理的设备上部署和使用，\n"
    "   严禁在他人设备上安装或运行。\n\n"
    "2. 本软件功能等价于远程控制，可查看屏幕、控制键鼠、传输文件、\n"
    "   执行命令、管理进程。使用者需自行确保用途合法合规。\n\n"
    "3. 因使用者违反上述约定、或违反所在地法律法规而产生的一切\n"
    "   后果，由使用者本人承担，作者不承担任何责任。\n\n"
    "4. 本软件代码完全开源可审计，不含任何恶意行为；\n"
    "   若杀毒软件误报，请自行判断后添加信任。"
)


def _center(parent, win, w, h):
    """在父窗口中心弹出"""
    try:
        parent.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - w) // 2
        py = parent.winfo_y() + (parent.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{max(0, px)}+{max(0, py)}")
    except Exception:
        win.geometry(f"{w}x{h}")


class AboutDialog:
    """「关于软件」对话框"""

    def __init__(self, parent):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("关于软件")
        self.win.configure(bg=C_APP_BG)
        self.win.resizable(False, False)
        self.win.transient(parent)
        try:
            self.win.grab_set()
        except Exception:
            pass
        _center(parent, self.win, 560, 520)
        self._install_icon(self.win)

        self._build()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 图标 ----------------
    def _install_icon(self, win):
        try:
            from PIL import Image, ImageDraw, ImageTk
            cache = os.path.join(os.path.dirname(__file__), ".deploy_icon.png")
            if not os.path.isfile(cache):
                img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                d = ImageDraw.Draw(img)
                d.ellipse([0, 0, 63, 63], fill=(21, 101, 192, 255))
                d.polygon([(20, 40), (30, 24), (40, 40), (34, 40), (34, 48),
                           (30, 48), (30, 40)], fill=(255, 255, 255, 255))
                img.save(cache)
            self._icon = ImageTk.PhotoImage(file=cache)
            win.iconphoto(True, self._icon)
        except Exception:
            pass

    # ---------------- 界面 ----------------
    def _build(self):
        w = self.win

        # ===== 标题栏 =====
        bar = tk.Frame(w, bg=C_TITLEBAR, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="关于软件", bg=C_TITLEBAR, fg=C_TITLEBAR_FG,
                 font=(FONT, 12, "bold"), anchor="w").pack(side="left", padx=14)
        tk.Button(bar, text="✕", command=self._on_close, bg=C_TITLEBAR,
                  fg=C_TITLEBAR_FG, activebackground="#0d47a1",
                  activeforeground="white", relief="flat", bd=0,
                  font=(FONT, 10), cursor="hand2", padx=12).pack(side="right")

        # ===== 头部：软件名 + 版本 + 作者 =====
        head = tk.Frame(w, bg=C_APP_BG)
        head.pack(fill="x", padx=20, pady=(18, 6))

        tk.Label(head, text=APP_NAME, bg=C_APP_BG, fg=C_TITLEBAR,
                 font=(FONT, 16, "bold"), anchor="w").pack(anchor="w")
        tk.Label(head, text=APP_DESC, bg=C_APP_BG, fg=C_MUTED,
                 font=(FONT, 9), anchor="w").pack(anchor="w", pady=(3, 0))

        # 版本 / 作者 信息条
        info = tk.Frame(w, bg=C_BTN_LIGHT)
        info.pack(fill="x", padx=20, pady=(10, 6))
        for label, value in (("版本", APP_VERSION), ("作者", APP_AUTHOR)):
            row = tk.Frame(info, bg=C_BTN_LIGHT)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, bg=C_BTN_LIGHT, fg=C_TITLEBAR,
                     font=(FONT, 9), width=6, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=C_BTN_LIGHT, fg=C_TEXT,
                     font=(FONT, 10, "bold"), anchor="w").pack(side="left")

        # ===== 免责声明 =====
        warn = tk.Frame(w, bg=C_WARN_BG, highlightbackground=C_WARN_BORDER,
                        highlightthickness=1)
        warn.pack(fill="both", expand=True, padx=20, pady=(10, 6))

        tk.Label(warn, text="⚠  免责声明", bg=C_WARN_BG, fg=C_WARN_FG,
                 font=(FONT, 10, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(10, 6))

        # 用 Text 便于多行排版 + 只读
        txt = tk.Text(warn, wrap="word", bg=C_WARN_BG, fg=C_TEXT,
                      font=(FONT, 9), relief="flat", bd=0,
                      highlightthickness=0, height=13, cursor="arrow")
        txt.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        txt.insert("1.0", DISCLAIMER)
        txt.config(state="disabled")   # 只读，防止误改

        # ===== 按钮 =====
        br = tk.Frame(w, bg=C_APP_BG)
        br.pack(fill="x", padx=20, pady=(6, 16))
        tk.Button(br, text="确定", command=self._on_close,
                  bg=C_BTN_BG, fg=C_BTN_FG,
                  activebackground=C_ACCENT, activeforeground="white",
                  relief="flat", bd=0, padx=30, pady=6,
                  font=(FONT, 9, "bold"), cursor="hand2").pack(side="right")

    # ---------------- 关闭 ----------------
    def _on_close(self):
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()


def open_about_dialog(parent):
    """供主控端工具栏调用: from about import open_about_dialog"""
    if parent is None:
        root = tk.Tk()
        root.withdraw()
        AboutDialog(root)
        root.mainloop()
    else:
        AboutDialog(parent)


def show_about_messagebox(parent=None):
    """
    极简版：直接弹系统消息框（tkinter 不可用时的兜底）。
    正常情况用 open_about_dialog。
    """
    messagebox.showinfo(
        "关于软件",
        f"{APP_NAME} {APP_VERSION}\n"
        f"作者：{APP_AUTHOR}\n\n"
        f"{DISCLAIMER}",
        parent=parent)


if __name__ == "__main__":
    open_about_dialog(None)
