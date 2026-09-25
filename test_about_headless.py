# -*- coding: utf-8 -*-
"""
test_about_headless.py - 「关于软件」对话框验证（无显示环境）

沙盒无 tkinter / 无显示器，用 fake tkinter 桩验证:
  1. about.py 可导入
  2. 软件信息正确（名称 / 版本 / 作者 = @爱分享的校长）
  3. 免责声明内容齐全（含 授权 / 合法 / 责任 / 开源 关键词）
  4. open_about_dialog / show_about_messagebox 可调用
  5. AboutDialog 可实例化，控件创建无异常
  6. controller.py 有「关于软件」按钮 + open_about 方法
  7. build.py 打包配置含 about（否则打包后点按钮会 ModuleNotFoundError）
"""

import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


# ============ fake tkinter（够 about.py 用即可）============
class _W:
    def __init__(self, *a, **kw):
        self._kw = kw
        self._text = kw.get("text", "")
        self._buf = ""
        for k, v in kw.items():
            setattr(self, k, v)

    def __getattr__(self, n):
        def _s(*a, **k):
            return None
        return _s

    def pack(self, *a, **k): pass
    def pack_propagate(self, *a, **k): pass
    def grid(self, *a, **k): pass
    def config(self, **k):
        for k2, v in k.items():
            setattr(self, k2, v)
    configure = cget = config
    def bind(self, *a, **k): pass
    def destroy(self): pass
    def title(self, *a): pass
    def geometry(self, *a): pass
    def transient(self, *a): pass
    def grab_set(self): pass
    def grab_release(self): pass
    def protocol(self, *a): pass
    def resizable(self, *a): pass
    def update_idletasks(self): pass
    def iconphoto(self, *a, **k): pass
    def winfo_x(self): return 0
    def winfo_y(self): return 0
    def winfo_width(self): return 100
    def winfo_height(self): return 100
    def insert(self, idx, text): self._buf = text
    def get(self, *a): return self._buf
    def set(self, v): self._text = v


tk = types.ModuleType("tkinter")
tk.Tk = lambda: _W()
tk.Toplevel = lambda master=None: _W(master)
tk.Frame = lambda *a, **k: _W(*a, **k)
tk.Label = lambda *a, **k: _W(*a, **k)
tk.Button = lambda *a, **k: _W(*a, **k)
tk.Text = lambda *a, **k: _W(*a, **k)
tk.PhotoImage = lambda *a, **k: None
tk.StringVar = lambda *a, **k: _W(*a, **k)
sys.modules["tkinter"] = tk

mb = types.ModuleType("tkinter.messagebox")
mb.showinfo = lambda *a, **k: print("  [INFO]", a[0] if a else "")
sys.modules["tkinter.messagebox"] = mb

ttk = types.ModuleType("tkinter.ttk")
sys.modules["tkinter.ttk"] = ttk


def main():
    print("=" * 62)
    print("  「关于软件」验证（fake Tk，无显示环境）")
    print("=" * 62)

    import about

    print("\n[1] 模块导入")
    assert hasattr(about, "AboutDialog"), "缺 AboutDialog"
    assert hasattr(about, "open_about_dialog"), "缺 open_about_dialog"
    print("    AboutDialog + open_about_dialog 存在 ✓")

    print("\n[2] 软件信息")
    print(f"    名称: {about.APP_NAME}")
    print(f"    版本: {about.APP_VERSION}")
    print(f"    作者: {about.APP_AUTHOR}")
    assert about.APP_AUTHOR == "@爱分享的校长", f"作者应为 @爱分享的校长，实际 {about.APP_AUTHOR}"
    assert about.APP_NAME
    print("    作者正确 ✓")

    print("\n[3] 免责声明内容")
    d = about.DISCLAIMER
    print(f"    共 {len(d)} 字")
    # 关键要素
    keywords = {
        "授权": "授权",
        "严禁": "严禁",
        "合法": "合法",
        "责任": "责任",
        "开源": "开源",
    }
    for name, kw in keywords.items():
        assert kw in d, f"免责声明缺少关键词: {name}"
        print(f"    含「{name}」 ✓")
    assert len(d) > 100, "免责声明太短"
    print("    免责声明齐全 ✓")

    print("\n[4] 入口函数可调用")
    assert callable(about.open_about_dialog)
    assert callable(about.show_about_messagebox)
    print("    open_about_dialog / show_about_messagebox 可调用 ✓")

    print("\n[5] 实例化对话框（不应抛异常）")
    root = _W()
    dlg = about.AboutDialog(root)
    assert dlg.win is not None
    print("    AboutDialog 实例化成功 ✓")

    print("\n[6] open_about_dialog(parent=None) 不崩溃")
    about.show_about_messagebox(None)
    print("    兜底消息框可用 ✓")

    print("\n[7] controller.py 集成")
    src = open(os.path.join(HERE, "controller.py"), encoding="utf-8").read()
    assert '"关于软件"' in src or "'关于软件'" in src, "工具栏缺「关于软件」按钮"
    assert "def open_about" in src, "缺 open_about 方法"
    assert "from about import open_about_dialog" in src, "未导入 open_about_dialog"
    print("    工具栏按钮 + open_about + 动态导入 齐全 ✓")

    print("\n[8] 打包配置（关键！漏了打包后点按钮会崩）")
    import build as B
    assert "about" in B.CONTROLLER_HIDDEN, "CONTROLLER_HIDDEN 缺 about"
    print("    CONTROLLER_HIDDEN 含 about ✓")
    # 控制端打包命令里应出现
    import subprocess
    r = subprocess.run([sys.executable, "build.py", "--dry-run"],
                       cwd=HERE, capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    ctrl_line = [l for l in out.split("\n") if "--name=控制端" in l]
    assert ctrl_line and "--hidden-import=about" in ctrl_line[0], "控制端打包命令缺 about"
    print("    控制端打包命令含 --hidden-import=about ✓")

    print("\n" + "=" * 62)
    print("  全部验证通过 ✓")
    print("=" * 62)


if __name__ == "__main__":
    main()
