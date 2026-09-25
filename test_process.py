"""
test_process.py - 进程管理功能验证

覆盖:
  1. 采集模块: get_process_list 能拿到进程（psutil / tasklist / ps 任一）
  2. 结束进程保护: 拒绝结束自身 / PID 0 / 无效 PID
  3. agent 端: 正确处理 proc_list_req / proc_kill_req
  4. 控制端: fetch 进程列表（走真实 TCP）
  5. 会话页 UI: 表格列、按钮、过滤、自动刷新字段齐全
  6. 打包配置: psutil 已列入隐藏导入
"""
import os
import socket
import sys
import threading
import time
from unittest.mock import MagicMock, Mock

sys.path.insert(0, os.path.dirname(__file__))

for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
    sys.modules.setdefault(_m, MagicMock())

import process_mgr as pm
from common import (
    encode, decode, recv_all, send_all,
    make_proc_list_request, make_proc_kill_request,
)

AGENT_PORT = 9821


def start_agent(port=AGENT_PORT):
    from agent import Agent
    a = Agent("进程测试机", port, 9086)
    threading.Thread(target=a._accept_loop, daemon=True).start()
    time.sleep(0.8)
    return a


def request(port, msg, timeout=15):
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.settimeout(timeout)
    send_all(s, encode(msg))
    data = recv_all(s, timeout=timeout)
    s.close()
    return decode(data) if data else {}


def test_collect():
    print("\n[测试1] 进程采集")
    procs, backend = pm.get_process_list()
    print(f"  采集方式: {backend}, 进程数: {len(procs)}")
    assert len(procs) > 0, "应能采集到进程"
    assert backend in ("psutil", "tasklist", "ps"), f"未知后端 {backend}"
    p = procs[0]
    for k in ("pid", "name", "cpu", "mem", "status"):
        assert k in p, f"进程字段缺 {k}"
    print(f"  示例: PID={p['pid']} name={p['name']} mem={p['mem']}MB")
    print("  ✓ 字段完整（pid/name/cpu/mem/status）")


def test_kill_guard():
    print("\n[测试2] 结束进程的安全保护")
    # 无效 PID
    ok, msg = pm.kill_process(0)
    print(f"  PID 0      -> ok={ok} msg={msg}")
    assert not ok, "PID 0 应被拒绝"

    ok, msg = pm.kill_process(-1)
    print(f"  PID -1     -> ok={ok} msg={msg}")
    assert not ok, "无效 PID 应被拒绝"

    # 自身进程（被控端自己）
    ok, msg = pm.kill_process(os.getpid())
    print(f"  自身 PID   -> ok={ok} msg={msg}")
    assert not ok, "绝不能结束被控端自身"
    assert "自身" in msg, f"提示应说明原因，实际: {msg}"

    # 系统核心 PID 4 (Windows System)
    ok, msg = pm.kill_process(4)
    print(f"  PID 4      -> ok={ok} msg={msg}")
    assert not ok, "系统核心进程应被拒绝"
    print("  ✓ 三重保护生效（无效PID / 自身 / 系统核心）")


def test_agent_proc_list():
    print("\n[测试3] agent 响应 proc_list_req")
    a = start_agent()
    try:
        resp = request(AGENT_PORT, make_proc_list_request())
        print(f"  响应类型: {resp.get('type')}")
        assert resp.get("type") == "proc_list_res"
        procs = resp.get("procs", [])
        print(f"  返回进程数: {len(procs)}, 后端: {resp.get('backend')}")
        assert len(procs) > 0, "应返回进程列表"
        assert resp.get("count") == len(procs)
        print("  ✓ agent 正确返回进程列表")
    finally:
        a.shutdown()


def test_agent_proc_kill():
    print("\n[测试4] agent 响应 proc_kill_req")
    a = start_agent(9822)
    try:
        # 用一个不存在的 PID，验证错误处理（不应崩溃）
        resp = request(9822, make_proc_kill_request(999997, force=False))
        print(f"  不存在PID -> type={resp.get('type')} ok={resp.get('ok')}")
        print(f"              msg={resp.get('message')}")
        assert resp.get("type") == "proc_kill_res"
        assert resp.get("ok") is False, "不存在的进程应返回失败"
        assert resp.get("message"), "应返回失败原因"

        # 试图杀被控端自身 —— 必须被拒绝
        resp = request(9822, make_proc_kill_request(os.getpid(), force=False))
        print(f"  杀自身    -> ok={resp.get('ok')} msg={resp.get('message')}")
        assert resp.get("ok") is False, "绝不能杀死被控端自身"
        print("  ✓ 错误处理正确，自身保护在协议层也生效")
    finally:
        a.shutdown()


def test_proc_kill_real():
    """测试5: 真正结束一个临时进程，验证闭环"""
    print("\n[测试5] 真实结束一个进程（起个 sleep 再杀掉）")
    import subprocess
    if pm.IS_WINDOWS:
        p = subprocess.Popen(["timeout", "30"], shell=True)
    else:
        p = subprocess.Popen(["sleep", "30"])
    pid = p.pid
    print(f"  已启动临时进程 PID={pid}")
    time.sleep(0.5)

    ok, msg = pm.kill_process(pid, force=False)
    print(f"  kill -> ok={ok} msg={msg}")
    assert ok, f"应能结束普通进程，实际失败: {msg}"

    # 确认真的结束了
    p.wait(timeout=5)
    print(f"  进程已退出，退出码 {p.returncode}")
    print("  ✓ 结束流程闭环正常")


def test_session_ui():
    print("\n[测试6] 会话进程页 UI 元素")
    from session import SessionWindow
    for cls in ("Toplevel", "Frame", "Label", "Button", "Canvas", "Entry",
                "LabelFrame", "StringVar", "BooleanVar", "Checkbutton"):
        try:
            getattr(__import__("tkinter"), cls).side_effect = lambda *a, **k: MagicMock()
        except Exception:
            pass
    import tkinter as tk
    from unittest.mock import MagicMock as MM

    class M:
        name = "演示机-01"; ip = "127.0.0.1"; port = 9001
        os = "Windows 11"; status = "online"

    win = SessionWindow(MM(), M())
    # 应有这些属性
    for attr in ("proc_tree", "proc_status", "proc_filter", "proc_auto",
                 "proc_refresh", "proc_kill", "_proc_apply_filter"):
        assert hasattr(win, attr), f"缺少 {attr}"
    print("  ✓ 表格/状态栏/搜索框/自动刷新/刷新方法 均已创建")

    # 过滤功能
    win._proc_all = [
        {"pid": 1, "name": "explorer.exe", "cpu": 0.0, "mem": 50.0, "status": "running"},
        {"pid": 2, "name": "notepad.exe", "cpu": 0.0, "mem": 10.0, "status": "running"},
        {"pid": 3, "name": "chrome.exe", "cpu": 5.0, "mem": 200.0, "status": "running"},
    ]
    win.proc_tree.delete = Mock()
    win.proc_tree.get_children = Mock(return_value=[])
    win.proc_tree.insert = Mock()
    win.proc_filter = type("V", (), {"get": lambda s: "note"})()
    win._proc_apply_filter()
    n = win.proc_tree.insert.call_count
    print(f"  搜索 'note' -> 匹配 {n} 条")
    assert n == 1, f"应只匹配 notepad.exe，实际 {n}"

    win.proc_filter = type("V", (), {"get": lambda s: ""})()
    win.proc_tree.insert.reset_mock()
    win._proc_apply_filter()
    n2 = win.proc_tree.insert.call_count
    print(f"  搜索 空     -> 匹配 {n2} 条")
    assert n2 == 3, f"空搜索应显示全部 3 条，实际 {n2}"
    print("  ✓ 搜索过滤正确")


def test_build_hidden_imports():
    print("\n[测试7] 打包配置包含 psutil")
    import build as b
    hidden = b.AGENT_HIDDEN
    assert "psutil" in hidden, "psutil 必须在被控端隐藏导入里"
    print(f"  AGENT_HIDDEN 含 psutil ✓")
    # 依赖检查应提到 psutil
    import inspect
    src = inspect.getsource(b.check_deps)
    assert "psutil" in src, "check_deps 应检查 psutil"
    print("  ✓ check_deps 会提示 psutil")


if __name__ == "__main__":
    print("=" * 62)
    print("  进程管理功能 验证")
    print("=" * 62)
    test_collect()
    test_kill_guard()
    test_agent_proc_list()
    test_agent_proc_kill()
    test_proc_kill_real()
    test_session_ui()
    test_build_hidden_imports()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("=" * 62)
