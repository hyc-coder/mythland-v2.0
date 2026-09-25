"""
test_session.py - 设备详情（控制会话）窗口「壳」验证

验证点（纯结构，不需要真实远端功能）:
  1. 窗口标题: 设备详情 - <机器名>
  2. 设备操作区: 9 个按钮齐全
  3. 标签页: 控制台 / 文件浏览 / 进程列表 / 屏幕监控
  4. 底部「执行」按钮 + 命令输入框
  5. 屏幕监控页有画布和占位提示
  6. 所有按钮点击不报错（弹"功能开发中"）
  7. 同一机器重复打开只保留一个窗口
"""
import sys
import os
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, os.path.dirname(__file__))

# tkinter 打桩（沙盒无 GUI）
tk_mock = MagicMock()
ttk_mock = MagicMock()
mb_mock = MagicMock()
sys.modules.setdefault("tkinter", tk_mock)
sys.modules.setdefault("tkinter.ttk", ttk_mock)
sys.modules.setdefault("tkinter.messagebox", mb_mock)

import tkinter as tk

# 关键: session.py 用 `from tkinter import messagebox`，
# 这会取 tk_mock.messagebox（自动子 mock），而非 sys.modules 里的 mb_mock。
# 显式指向同一个对象，测试才能断言到。
tk_mock.messagebox = mb_mock
tk_mock.ttk = ttk_mock

# 让 Toplevel/Frame/Label 每次返回独立 mock
for _cls in ("Toplevel", "Frame", "Label", "Button", "Canvas", "Entry",
             "LabelFrame", "StringVar"):
    getattr(tk_mock, _cls).side_effect = lambda *a, **k: MagicMock()


class FakeMachine:
    def __init__(self, mid="mid-1", name="演示机-01", ip="192.168.1.101", port=9001):
        self.id = mid
        self.name = name
        self.ip = ip
        self.port = port
        self.os = "Windows 11"
        self.status = "online"


def build_session():
    """构造一个 SessionWindow 并收集 UI 调用"""
    import session
    from session import SessionWindow

    # 每次重建前重置调用记录，避免测试间互相污染
    tk_mock.Button.reset_mock()
    ttk_mock.Notebook.reset_mock()
    mb_mock.showinfo.reset_mock()

    master = Mock()
    m = FakeMachine()

    win = SessionWindow(master, m)

    # 统计按钮文字: Button(parent, text=..., ...) → text 是关键字参数
    btn_texts = []
    for call in tk_mock.Button.call_args_list:
        args, kwargs = call
        if "text" in kwargs:
            btn_texts.append(kwargs["text"])
        elif len(args) >= 2 and isinstance(args[1], str):
            btn_texts.append(args[1])

    # 统计标签页: notebook.add(page, text=...) → 用 win.nb.add
    tab_texts = []
    for call in win.nb.add.call_args_list:
        args, kwargs = call
        if "text" in kwargs:
            tab_texts.append(kwargs["text"])
        elif len(args) >= 2:
            tab_texts.append(args[1])

    return win, btn_texts, tab_texts


def test_window_title():
    print("\n[测试1] 窗口标题")
    win, _, _ = build_session()
    # 注意: Toplevel 用了 side_effect，实际返回对象保存在 win.win 上
    calls = [c for c in win.win.title.call_args_list]
    assert calls, "应调用 win.title()"
    title = calls[-1][0][0] if calls and calls[-1][0] else None
    print(f"  标题: {title}")
    assert title and "设备详情" in title, f"标题应含'设备详情'，实际 {title}"
    assert "演示机-01" in title, "标题应含机器名"
    print("  ✓ 标题格式正确: 设备详情 - 机器名")


def test_action_buttons():
    print("\n[测试2] 设备操作按钮（单行居中）")
    expected = ["发送命令", "发送消息", "上传文件", "进程管理",
                "查看日志", "打开网址", "执行"]
    win, btn_texts, _ = build_session()
    print(f"  实际按钮: {btn_texts}")
    missing = [b for b in expected if b not in btn_texts]
    assert not missing, f"缺少按钮: {missing}"

    # 「已删除」只针对【设备操作区】判断 —— 其它页（进程列表、常用命令）
    # 也有同名按钮，不能全局匹配。
    ops = [t for t in btn_texts if t in set(expected)]
    removed = ["进程列表", "文件列表", "开始监控", "停止监控"]
    still = [b for b in removed if b in ops]
    assert not still, f"设备操作区不应有这些按钮: {still}"
    print(f"  ✓ {len(expected)} 个按钮齐全，设备操作区已无 {removed}")


def test_tabs():
    print("\n[测试3] 标签页（4 个）")
    expected = ["控制台", "文件浏览", "进程列表", "屏幕监控"]
    win, _, tab_texts = build_session()
    print(f"  实际标签: {tab_texts}")
    missing = [t for t in expected if t not in tab_texts]
    assert not missing, f"缺少标签页: {missing}"
    print("  ✓ 4 个标签页齐全")


def test_screen_page():
    print("\n[测试4] 屏幕监控页")
    win, _, _ = build_session()
    assert hasattr(win, "screen_canvas"), "应有 screen_canvas"
    assert hasattr(win, "screen_hint"), "应有占位提示"
    assert win.screen_canvas is not None
    print("  ✓ 画布 + 占位提示已创建")
    # 开始/停止监控不报错
    try:
        win.act_start_monitor()
        assert win._monitoring is True
        win.act_stop_monitor()
        assert win._monitoring is False
        print("  ✓ 开始/停止监控状态切换正常")
    except Exception as e:
        raise AssertionError(f"监控切换报错: {e}")


def test_all_buttons_clickable():
    print("\n[测试5] 所有按钮点击不报错")
    win, _, _ = build_session()
    actions = [
        ("发送命令", win.act_send_command),
        ("发送消息", win.act_send_message),
        ("上传文件", win.act_upload_file),
        ("进程管理", win.act_process_manage),
        ("查看日志", win.act_view_log),
        ("打开网址", win.act_open_url),
        ("执行", win.act_execute),
        # 监控仍保留方法（供标签切换自动调用），但已无按钮
        ("开始监控(自动)", win.act_start_monitor),
        ("停止监控(自动)", win.act_stop_monitor),
    ]
    for name, fn in actions:
        try:
            fn()
        except Exception as e:
            raise AssertionError(f"点击「{name}」报错: {e}")
    print(f"  ✓ {len(actions)} 个动作全部可调用，无异常")


def test_tooltip_shown():
    """
    原先验证"点击弹『功能开发中』"—— 所有功能已实现，这条断言已过时。
    现在改为验证: 点击「发送命令」不再弹占位提示，而是走真实流程。
    """
    print("\n[测试6] 不再弹「功能开发中」（占位已全部实现）")
    win, _, _ = build_session()
    mb_mock.showinfo.reset_mock()

    # act_send_command 会弹【输入对话框】(wait_window)。
    # 在 mock 环境下 wait_window 立即返回，因此不会调 showinfo 报"开发中"。
    try:
        win.act_send_command()
    except Exception as e:
        raise AssertionError(f"act_send_command 报错: {e}")

    called = mb_mock.showinfo.called
    if called:
        args = mb_mock.showinfo.call_args[0]
        title = args[0] if args else ""
        print(f"  弹窗标题: {title}")
        assert "开发中" not in title, \
            f"不应再出现'开发中'占位提示，实际: {title}"
    else:
        print("  未弹占位提示 ✓（已走真实流程）")

    # 源码层面确认没有 _todo 占位调用了
    import inspect
    src = inspect.getsource(type(win))
    assert "self._todo(" not in src, "实现里不应再有 _todo 占位调用"
    print("  ✓ 占位提示已全部清除")


def test_update_frame_interface():
    print("\n[测试7] update_frame 预留接口")
    win, _, _ = build_session()
    assert hasattr(win, "update_frame"), "应预留 update_frame 接口"
    import inspect
    sig = inspect.signature(win.update_frame)
    assert "pil_image" in sig.parameters, "应接受 pil_image 参数"
    print("  ✓ 接口签名正确: update_frame(pil_image)")
    print("    （后续接实时画面时调用即可）")


def test_tab_autostop():
    """测试8: 切到屏幕监控自动开始，切走自动停止"""
    print("\n[测试8] 标签页自动启停监控")
    win, _, _ = build_session()

    # 模拟 notebook 索引: 控制台0 / 文件浏览1 / 进程列表2 / 屏幕监控3
    # 页面对象的身份判断要放在字符串判断之前（MagicMock 可能相等）
    def fake_index(x):
        if x is win.page_screen:
            return 3
        if x is win.page_process:
            return 2
        if x is win.page_console:
            return 0
        if x == "screen":
            return 3
        if x == "process":
            return 2
        if x == "console":
            return 0
        return 1              # 其它页（文件浏览）
    win.nb.index = Mock(side_effect=fake_index)
    win.nb.select = Mock(return_value="screen")

    # 用桩替换真正会开线程的方法，避免真的连网络
    started = []
    stopped = []
    win.act_start_monitor = lambda: started.append(1)
    win.act_stop_monitor = lambda: stopped.append(1)

    # 切到屏幕监控
    win.nb.select.return_value = "screen"
    win._on_tab_changed()
    assert started, "切到屏幕监控应自动开始"
    print("  ✓ 切到「屏幕监控」→ 自动开始")

    # 切到其它页
    win.nb.select.return_value = "console"
    win._monitoring = True
    win._on_tab_changed()
    assert stopped, "切走应自动停止"
    print("  ✓ 切到其它页 → 自动停止")

    # 已在监控中，重复切到该页不应重复启动
    win._monitoring = True
    started.clear()
    win.nb.select.return_value = "screen"
    win._on_tab_changed()
    assert not started, "已在监控中不应重复启动"
    print("  ✓ 已在监控中时不会重复启动")


def test_single_row_center():
    """测试9: 按钮排成一行且居中"""
    print("\n[测试9] 按钮单行居中布局")
    win, btn_texts, _ = build_session()
    # 设备操作区的按钮（排除底部「执行」和进程页自己的按钮）
    expected_ops = {"发送命令", "发送消息", "上传文件",
                    "进程管理", "查看日志", "打开网址"}
    ops = [t for t in btn_texts if t in expected_ops]
    print(f"  操作按钮: {ops}")
    assert len(ops) == 6, f"应有 6 个操作按钮，实际 {len(ops)}"
    # 检查是否创建了居中容器（pack(anchor="center")）
    # 注意: Frame 用了 side_effect，每次返回独立 mock，
    # 需遍历所有创建过的 Frame 实例找 anchor='center'
    centered = False
    for call in tk_mock.Frame.call_args_list:
        fm = call[0] if False else None
    # 用 gc 找不到，改为直接检查源码里是否存在居中容器定义
    import inspect
    import session as _s
    src = inspect.getsource(_s.SessionWindow._build_toolbar)
    assert 'anchor="center"' in src, "工具栏应包含居中的容器"
    # 且按钮都在同一个 center 容器下（不再分 row1/row2 两行）
    assert "row2" not in src, "按钮应只排一行（不应有 row2）"
    print("  ✓ 单行 6 个按钮，整体水平居中（源码校验通过）")


if __name__ == "__main__":
    print("=" * 62)
    print("  设备详情窗口（界面壳）验证")
    print("=" * 62)
    test_window_title()
    test_action_buttons()
    test_tabs()
    test_screen_page()
    test_all_buttons_clickable()
    test_tooltip_shown()
    test_update_frame_interface()
    test_tab_autostop()
    test_single_row_center()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓  界面壳完成")
    print("=" * 62)
