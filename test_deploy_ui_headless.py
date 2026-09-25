# -*- coding: utf-8 -*-
"""
headless 逻辑验证: 在无显示环境的服务器上，用 fake Tk 对象
验证 DeployDialog 的所有方法调用不会抛异常、字段/变量齐全。
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# ---- 构造一个 fake tkinter，避免 ImportError ----
tk = types.ModuleType("tkinter")
tk.LEFT, tk.RIGHT, tk.TOP, tk.BOTTOM = "l", "r", "t", "b"
tk.SOLID = "solid"
tk.CENTER = "center"


class _Widget:
    def __init__(self, *a, **kw):
        self._children = []
        self._kw = kw
        self._var = kw.get("textvariable")
        self._text = kw.get("text", "")
        self._state = kw.get("state", "normal")
        self._command = kw.get("command")
        for k, v in kw.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        # 未显式设置的属性 -> 返回可调用桩
        def _stub(*a, **k):
            return None
        return _stub

    def pack(self, *a, **k): pass
    def pack_forget(self, *a, **k): pass
    def grid(self, *a, **k): pass
    def config(self, **k):
        for key, val in k.items():
            setattr(self, key, val)
        # 让 btn["state"] / cget("state") 都能取到
        if "state" in k:
            self._state = k["state"]

    def cget(self, key):
        return getattr(self, key, None)
    configure = cget = config
    def bind(self, *a, **k): pass
    def winfo_exists(self): return True
    def after(self, *a, **k): pass
    def destroy(self): pass
    def set(self, v): self._text = v
    def get(self): return self._text


class _Text(_Widget):
    """支持 get / insert / delete 的最小 Text 桩"""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._buf = ""

    def get(self, start, end=None):
        if end in ("end-1c", "end"):
            return self._buf
        return self._buf

    def insert(self, index, text):
        self._buf = text

    def delete(self, start, end=None):
        self._buf = ""


class _Var(_Widget):
    def __init__(self, master=None, value=""):
        super().__init__(master, value=value)
        self._val = value

    def set(self, v): self._val = v
    def get(self): return self._val


class _Toplevel(_Widget):
    def __init__(self, master=None):
        super().__init__(master)
        self._vars = {}

    def title(self, *a): pass
    def geometry(self, *a): pass
    def transient(self, *a): pass
    def grab_set(self): pass
    def grab_release(self): pass
    def protocol(self, *a): pass
    def update_idletasks(self): pass


class _Tree(_Widget):
    def __init__(self, master=None, columns=(), **kw):
        super().__init__(master, **kw)
        self._columns = tuple(columns)
        self._rows = []
        self._tags = {}

    def heading(self, col, **kw): pass
    def column(self, col, **kw): pass
    def insert(self, parent, index, iid=None, values=(), tags=()):
        self._rows.append((iid, values, tags))
        return iid
    def delete(self, *iids):
        self._rows = [r for r in self._rows if r[0] not in iids]
    def item(self, iid, **kw):
        for i, (rid, vals, tags) in enumerate(self._rows):
            if rid == iid:
                if "values" in kw:
                    self._rows[i] = (rid, kw["values"], self._tags.get(iid, ()))
                if "tags" in kw:
                    self._tags[iid] = kw["tags"]
                break
    def get_children(self): return [r[0] for r in self._rows]
    def see(self, iid): pass
    def tag_configure(self, tag, **kw): pass
    def tag_names(self): return list(self._tags.keys())
    def heading(self, *a, **k): return None


class _Msg:
    @staticmethod
    def showwarning(*a, **k): print("  [WARN]", a[0], "::", a[1][:60])
    @staticmethod
    def showerror(*a, **k): print("  [ERROR]", a[0], "::", a[1][:60])
    @staticmethod
    def showinfo(*a, **k): print("  [INFO]", a[0], "::", a[1][:60])
    @staticmethod
    def askyesno(*a, **k): return False


def _mk(class_name):
    def _c(*a, **k):
        return _Widget(*a, **k)
    return _c


tk.Tk = lambda: _Toplevel()
tk.Toplevel = _Toplevel
tk.Frame = _mk("Frame")
tk.Label = _mk("Label")
class _Button(_Widget):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._state = kw.get("state", "normal")
tk.Button = _Button
tk.Entry = _mk("Entry")
tk.Text = _Text
tk.Spinbox = _mk("Spinbox")
tk.Checkbutton = _mk("Checkbutton")
tk.LabelFrame = _mk("LabelFrame")
tk.StringVar = _Var
tk.BooleanVar = _Var
tk.PhotoImage = lambda *a, **k: None
tk.Canvas = _mk("Canvas")
tk.Scrollbar = _mk("Scrollbar")
sys.modules["tkinter"] = tk

ttk = types.ModuleType("tkinter.ttk")
ttk.Treeview = _Tree
ttk.Scrollbar = _mk("Scrollbar")


class _Style:
    def theme_use(self, *a): pass
    def configure(self, *a, **k): pass
    def map(self, *a, **k): pass
ttk.Style = _Style
sys.modules["tkinter.ttk"] = ttk

mb = types.ModuleType("tkinter.messagebox")
mb.showwarning = _Msg.showwarning
mb.showerror = _Msg.showerror
mb.showinfo = _Msg.showinfo
mb.askyesno = _Msg.askyesno
sys.modules["tkinter.messagebox"] = mb

fd = types.ModuleType("tkinter.filedialog")
fd.askopenfilename = lambda *a, **k: ""
sys.modules["tkinter.filedialog"] = fd

# PIL 也桩掉（图标生成处）
try:
    import PIL  # noqa
except ImportError:
    pil = types.ModuleType("PIL")
    sys.modules["PIL"] = pil
    img_mod = types.ModuleType("PIL.Image")
    img_mod.new = lambda *a, **k: _Widget()
    img_mod.ImageDraw = types.ModuleType("PIL.ImageDraw")
    sys.modules["PIL.Image"] = img_mod


def main():
    print("=" * 60)
    print("  headless 逻辑验证（fake Tk，无显示环境）")
    print("=" * 60)

    from deploy_ui import DeployDialog, open_deploy_dialog, STAGE_TEXT

    print("\n[1] 模块导入 + 入口函数")
    from deploy_ui import open_deploy_dialog as odd
    assert callable(odd), "open_deploy_dialog 不可调用!"
    print("    open_deploy_dialog 存在且可调用 ✓")

    print("\n[2] 构建对话框（模拟 controller.root）")
    root = _Toplevel()
    dlg = DeployDialog(root)
    print("    实例化成功 ✓")

    print("\n[3] 字段/控件齐全性检查")
    required = ["ip_text", "exe_var", "jcc_var", "dir_var", "name_var",
                "workers_var", "timeout_var", "start_var", "tree", "summary",
                "start_btn", "stop_btn", "close_btn", "jcc_state"]
    missing = [n for n in required if not hasattr(dlg, n)]
    assert not missing, f"缺少: {missing}"
    print(f"    全部 {len(required)} 个属性存在 ✓")

    print("\n[4] 默认值")
    from deploy import (DEFAULT_REMOTE_DIR, DEFAULT_TARGET_NAME,
                        DEFAULT_TIMEOUT, DEFAULT_WORKERS)
    assert dlg.dir_var.get() == DEFAULT_REMOTE_DIR
    assert dlg.name_var.get() == DEFAULT_TARGET_NAME
    assert int(dlg.workers_var.get()) == DEFAULT_WORKERS
    assert int(dlg.timeout_var.get()) == int(DEFAULT_TIMEOUT)
    print("    目录/文件名/并发/超时 均为默认值 ✓")

    print("\n[5] IP 快捷填入")
    dlg._fill_local()
    dlg._fill_full()
    print("    _fill_local / _fill_full 无异常 ✓")

    print("\n[6] 阶段中文映射")
    for k in ("待部署", "建目录", "下载", "启动", "完成", "失败", "取消"):
        assert k in STAGE_TEXT and STAGE_TEXT[k]
    print(f"    {len(STAGE_TEXT)} 个阶段映射齐全 ✓")

    print("\n[7] 进度表结构")
    src = open(os.path.join(HERE, "deploy_ui.py"), encoding="utf-8").read()
    assert 'cols = ("ip", "stage", "detail")' in src, "列定义缺失"
    assert 'self.tree.heading("ip", text="IP 地址")' in src
    assert 'self.tree.heading("stage", text="状态")' in src
    assert 'self.tree.heading("detail", text="详情")' in src
    print("    列: IP 地址 / 状态 / 详情（源码校验通过）✓")

    print("\n[8] 文件探测")
    dlg._auto_detect()
    print(f"    jcc_state = {dlg.jcc_state._text[:50]!r} ✓")

    print("\n[9] 异常输入拦截（不应崩溃，应弹警告）")
    dlg.exe_var.set("")
    dlg.jcc_var.set(os.path.join(HERE, "deploy.py"))
    print("    -- 缺少被控端 --")
    dlg.start()
    dlg.ip_text.delete("1.0", "end")
    dlg.ip_text.insert("1.0", "这不是IP\n999.999.999.999")
    print("    -- IP 无效 --")
    dlg.start()

    print("\n[10] 运行状态切换")
    dlg._set_running_ui(True)
    assert dlg.stop_btn._state == "normal"
    dlg._set_running_ui(False)
    assert dlg.stop_btn._state == "disabled"
    print("    _set_running_ui 正常 ✓")

    print("\n[11] open_deploy_dialog(None) 不崩溃")
    open_deploy_dialog(None)
    print("    通过 ✓")

    print("\n" + "=" * 60)
    print("  全部逻辑验证通过 ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
