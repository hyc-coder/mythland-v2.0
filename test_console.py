"""
test_console.py - 控制台页（命令 + 日志 双视图）验证

修的两个问题:
  1. 控制台页初始显示"功能开发中" —— 现在一开始就构建成真实终端视图
  2. 命令输出和日志互相覆盖 —— 现在共用一块显示区，两个视图各自缓存

覆盖:
  1. 控制台页不再是占位页（无"功能开发中"字样）
  2. 有命令/日志两个切换按钮
  3. 两个视图共用同一个 Text 控件
  4. 切换视图时内容各自保留（不互相清空）
  5. 命令输出永远写进命令视图（即使当前在日志视图）
  6. 清空只清当前视图
  7. 日志视图有刷新按钮，命令视图有常用命令
  8. 源码里不再有重复的 _ensure_console_view 实现
"""

import inspect
import os
import sys
from unittest.mock import MagicMock, Mock

sys.path.insert(0, os.path.dirname(__file__))
for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
    sys.modules.setdefault(_m, MagicMock())

import session as S
from session import SessionWindow


class M:
    name = "演示机-01"
    ip = "127.0.0.1"
    port = 9001
    os = "Windows 11"
    status = "online"


# Tk 控件打桩：记录文本与配置
class FakeText:
    def __init__(self, *a, **k):
        self.value = ""
        self.state = "normal"
        self.opts = {}

    def configure(self, **k):
        self.opts.update(k)
        if "state" in k:
            self.state = k["state"]

    def config(self, **k):
        self.configure(**k)

    def insert(self, idx, text):
        self.value += text

    def delete(self, a, b=None):
        self.value = ""

    def get(self, a, b=None):
        return self.value

    def see(self, *a, **k):
        pass

    def yview(self, *a, **k):
        pass


def build():
    """构造 SessionWindow，并把 win.after 变成同步执行（方便断言）"""
    win = SessionWindow(MagicMock(), M())
    # after → 立即执行，避免断言时还没渲染
    win.win.after = lambda delay, fn, *a: fn(*a)
    # 文本框换成可控的假对象
    fake = FakeText()
    win._console_text = fake
    return win, fake


def test_not_placeholder():
    print("\n[测试1] 控制台页不再是占位页")
    src = inspect.getsource(SessionWindow._build_console_page)
    assert "功能开发中" not in src, "控制台页不应再有'功能开发中'提示"
    print("  _build_console_page 源码无'功能开发中' ✓")

    # 页面构建调用的是真实构建函数，而不是 _make_placeholder_page
    src2 = inspect.getsource(SessionWindow._build_notebook) \
        + inspect.getsource(SessionWindow.__init__)
    assert "_build_console_page" in src2, "应调用真实构建函数"
    assert 'page_console = self._make_placeholder_page' not in src2, \
        "不应再用占位页"
    print("  page_console 由 _build_console_page 构建 ✓")
    print("  ✓ 初始状态就是真实控制台，不再显示'功能开发中'")


def test_view_buttons():
    print("\n[测试2] 命令 / 日志 切换按钮")
    win, fake = build()
    assert hasattr(win, "_btn_view_cmd"), "缺命令视图按钮"
    assert hasattr(win, "_btn_view_log"), "缺日志视图按钮"
    print("  ✓ 两个切换按钮均已创建")

    # 视图常量与缓存
    assert win.VIEW_CMD == "cmd" and win.VIEW_LOG == "log"
    print(f"  视图常量: VIEW_CMD={win.VIEW_CMD}, VIEW_LOG={win.VIEW_LOG}")
    assert set(win._console_buf.keys()) == {"cmd", "log"}, "应有两个缓冲区"
    print(f"  缓冲区: {sorted(win._console_buf.keys())}")
    print("  ✓ 双缓冲区已就绪")


def test_shared_text():
    print("\n[测试3] 两个视图共用同一个 Text")
    win, fake = build()
    assert win._console_text is fake, "共用的是同一个控件"
    # 切来切去，控件不变
    win._switch_console(win.VIEW_LOG)
    assert win._console_text is fake, "切换后仍应是同一个控件"
    win._switch_console(win.VIEW_CMD)
    assert win._console_text is fake
    print("  ✓ 切换视图不重建控件（不会互相覆盖）")


def test_content_kept():
    print("\n[测试4] 切换视图时内容各自保留")
    win, fake = build()

    # 命令视图写点东西
    win._console_view = win.VIEW_CMD
    win._append_console("$ ipconfig\n  192.168.1.101\n")
    cmd_text = win._console_buf[win.VIEW_CMD]
    print(f"  命令视图内容: {cmd_text[:30]!r}...")
    assert "192.168.1.101" in cmd_text

    # 预置日志内容（先填缓冲区，切过去时就不会触发真实网络拉取）
    win._console_buf[win.VIEW_LOG] = "[Agent] 启动于 2026-09-16\n"
    win._switch_console(win.VIEW_LOG)
    log_text = win._console_buf[win.VIEW_LOG]
    print(f"  日志视图内容: {log_text[:30]!r}...")

    # 切回命令视图，命令内容应还在
    win._switch_console(win.VIEW_CMD)
    assert "192.168.1.101" in win._console_buf[win.VIEW_CMD], \
        "切回命令视图后内容丢失了"
    assert "[Agent]" not in win._console_buf[win.VIEW_CMD], \
        "日志内容混进了命令视图"
    print("  ✓ 命令内容保留，且未被日志污染")

    # 再切回日志，日志内容也还在
    win._switch_console(win.VIEW_LOG)
    assert "[Agent]" in win._console_buf[win.VIEW_LOG], "日志内容丢失了"
    print("  ✓ 日志内容同样保留")


def test_cmd_goes_to_cmd_view():
    print("\n[测试5] 命令输出永远写进命令视图")
    win, fake = build()

    # 当前停在日志视图
    win._console_view = win.VIEW_LOG
    win._console_buf[win.VIEW_LOG] = "[Agent] 日志行\n"

    # 此时来了一条命令输出
    win._append_console("> echo hi\nhi\n")

    assert win._console_view == win.VIEW_CMD, "应自动切回命令视图"
    print("  收到命令输出时自动切回命令视图 ✓")
    assert "echo hi" in win._console_buf[win.VIEW_CMD]
    assert "echo hi" not in win._console_buf[win.VIEW_LOG], \
        "命令回显不该混进日志"
    print("  ✓ 命令回显只进命令视图，日志未被污染")


def test_clear_only_current():
    print("\n[测试6] 清空只清当前视图")
    win, fake = build()
    win._console_view = win.VIEW_CMD
    win._append_console("cmd-output\n")
    win._console_buf[win.VIEW_LOG] = "log-content\n"

    win._console_clear()
    assert win._console_buf[win.VIEW_CMD] == "", "当前视图应被清空"
    assert win._console_buf[win.VIEW_LOG] == "log-content\n", \
        "另一个视图不该被清空"
    print("  命令视图已清空，日志视图不受影响 ✓")
    print("  ✓ 清空是视图隔离的")


def test_view_specific_widgets():
    print("\n[测试7] 各视图专属控件")
    win, fake = build()
    assert hasattr(win, "_console_quick"), "命令视图应有常用命令区"
    assert hasattr(win, "_btn_log_refresh"), "日志视图应有刷新按钮"
    print("  常用命令区 + 刷新日志按钮 均已创建 ✓")

    # 切换时不应抛异常（pack/pack_forget 在 mock 下是 no-op）
    for v in (win.VIEW_CMD, win.VIEW_LOG, win.VIEW_CMD):
        win._switch_console(v)
    print("  反复切换无异常 ✓")
    print("  ✓ 视图专属控件正常")


def test_no_duplicate_impl():
    print("\n[测试8] 无重复实现（旧 bug 根因）")
    src = open(os.path.join(os.path.dirname(__file__), "session.py"),
               encoding="utf-8").read()
    for fn in ("_set_console_text", "_append_console", "_ensure_console_view"):
        n = src.count(f"def {fn}(")
        print(f"  def {fn}( 出现 {n} 次")
        assert n == 1, f"{fn} 有 {n} 份实现，会互相覆盖"

    # 不应再有 destroy 页面的延迟重建逻辑
    assert "self.page_console.winfo_children()" not in src, \
        "不应再销毁控制台页重建（会把另一视图的内容清掉）"
    print("  无 page_console 销毁重建逻辑 ✓")
    print("  ✓ 每个方法只有一份实现，不再互相打架")


if __name__ == "__main__":
    print("=" * 62)
    print("  控制台页（命令 + 日志 双视图）验证")
    print("=" * 62)
    test_not_placeholder()
    test_view_buttons()
    test_shared_text()
    test_content_kept()
    test_cmd_goes_to_cmd_view()
    test_clear_only_current()
    test_view_specific_widgets()
    test_no_duplicate_impl()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("=" * 62)
