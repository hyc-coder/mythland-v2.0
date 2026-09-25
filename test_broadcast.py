"""
test_broadcast.py - 屏幕广播 验证

需求:
  主控端(教师机)把自己的屏幕广播给所有被控端(学生机)，像直播一样。
  被控端窗口【可调整大小】，但【不能关闭】，只能由主控端结束广播。

沙盒无显示器:
  - BroadcastServer 的采集会降级为占位画面，但推流链路可完整验证
  - viewer 的 Tk 窗口创建会失败，降级返回 False（协议仍要正确）
  因此本测试分两类:
    A. 链路与协议（真实跑通）
    B. 窗口约束（源码层面校验: resizable=True / 拦截关闭 / 拦截Alt+F4）
"""

import base64
import inspect
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))

from common import (
    encode, decode, recv_all, send_all,
    make_bc_start_request, make_bc_stop_request,
    make_bc_frame, make_bc_quit,
    MSG_BC_FRAME, MSG_BC_QUIT,
    BC_DEFAULT_FPS, BC_DEFAULT_WIDTH,
)


# ============ A. 链路与协议 ============

def test_protocol():
    print("\n[测试1] 协议构造")
    m = make_bc_start_request("192.168.1.7", 9100, "教师机演示", fps=8, width=1280)
    print(f"  start: host={m['host']} port={m['port']} fps={m['fps']} width={m['width']}")
    assert m["type"] == "bc_start_req"
    assert m["host"] == "192.168.1.7" and m["port"] == 9100

    s = make_bc_stop_request()
    assert s["type"] == "bc_stop_req"
    print(f"  stop : type={s['type']}")

    f = make_bc_frame(1920, 1080, "BASE64", 7)
    assert f["type"] == MSG_BC_FRAME and f["seq"] == 7
    print(f"  frame: type={f['type']} {f['w']}x{f['h']} seq={f['seq']}")

    q = make_bc_quit()
    assert q["type"] == MSG_BC_QUIT
    print("  ✓ 四种消息类型字段正确")


def test_server_push():
    print("\n[测试2] 广播服务: 采集 → 推流 → 客户端收帧")
    from broadcast import BroadcastServer

    srv = BroadcastServer(port=0, fps=10, width=640, title="测试广播")
    port = srv.start()
    print(f"  服务端口: {port}")
    assert port > 0

    # 客户端连上来
    c = socket.create_connection(("127.0.0.1", port), timeout=10)
    c.settimeout(10)
    # 等服务端 accept
    for _ in range(50):
        if srv.client_count() > 0:
            break
        time.sleep(0.1)
    print(f"  服务端看到客户端数: {srv.client_count()}")
    assert srv.client_count() == 1, "服务端应记录 1 个客户端"

    # 收帧
    frames = 0
    first = None
    t0 = time.time()
    while frames < 3 and time.time() - t0 < 8:
        try:
            data = recv_all(c, timeout=5)
        except Exception:
            break
        if not data:
            break
        msg = decode(data)
        if msg.get("type") == MSG_BC_FRAME:
            frames += 1
            if first is None:
                first = msg

    print(f"  收到帧数: {frames}")
    assert frames >= 3, f"应收到多帧，实际 {frames}"

    jpeg = base64.b64decode(first["data"])
    w, h = first["w"], first["h"]
    print(f"  首帧: {w}x{h}, JPEG {len(jpeg)} bytes, seq={first.get('seq')}")
    assert len(jpeg) > 100, "JPEG 数据不应为空"
    assert jpeg[:2] == b"\xff\xd8", "应为合法 JPEG（FFD8 开头）"
    print(f"  JPEG 魔数: {jpeg[:2].hex()} ✓")

    # 帧率大致符合（10FPS → 3 帧约 0.3s 起，这里只验证能持续推）
    print(f"  推流持续正常（{frames} 帧）")
    print("  ✓ 采集→推流→接收 链路完整")

    c.close()
    srv.stop()
    print("  ✓ 服务已停止")


def test_server_quit():
    print("\n[测试3] 结束广播: 客户端收到 bc_quit")
    from broadcast import BroadcastServer

    srv = BroadcastServer(port=0, fps=5, width=320)
    port = srv.start()
    c = socket.create_connection(("127.0.0.1", port), timeout=10)
    c.settimeout(10)
    for _ in range(50):
        if srv.client_count() > 0:
            break
        time.sleep(0.1)
    assert srv.client_count() == 1

    time.sleep(0.6)          # 让它推几帧
    srv.stop()               # 结束广播

    # 客户端应收到 bc_quit（可能夹在几帧后面）
    got_quit = False
    t0 = time.time()
    while time.time() - t0 < 5:
        try:
            data = recv_all(c, timeout=3)
        except Exception:
            break
        if not data:
            break
        try:
            msg = decode(data)
        except Exception:
            break
        if msg.get("type") == MSG_BC_QUIT:
            got_quit = True
            break

    print(f"  收到 bc_quit: {got_quit}")
    assert got_quit, "结束广播时客户端应收到 bc_quit（否则学生机窗口关不掉）"
    print("  ✓ 主控端结束 → 客户端收到关闭指令")
    c.close()


def test_agent_handles_bc():
    print("\n[测试4] agent 响应广播指令")
    from agent import Agent

    a = Agent("广播测试机", 9911, 9086)
    t = threading.Thread(target=a._accept_loop, daemon=True)
    t.start()
    time.sleep(1.8)
    port = a.port
    print(f"  agent 端口: {port}")

    def send(req, timeout=12):
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.settimeout(timeout)
        send_all(s, encode(req))
        d = recv_all(s, timeout=timeout)
        s.close()
        return decode(d) if d else {}

    try:
        # 沙盒无显示器 → viewer 创建失败，但协议必须完整、不能崩
        r = send(make_bc_start_request("127.0.0.1", 9100, "教师机演示"))
        print(f"  bc_start -> type={r.get('type')} ok={r.get('ok')}")
        print(f"     message={r.get('message')!r}")
        assert r.get("type") == "bc_start_res"
        for k in ("ok", "message"):
            assert k in r, f"缺字段 {k}"
        print("  ✓ 无显示环境时安全降级（有明确 message，未崩溃）")

        r = send(make_bc_stop_request())
        print(f"  bc_stop  -> ok={r.get('ok')} message={r.get('message')!r}")
        assert r.get("type") == "bc_stop_res"
        assert r.get("ok"), "停止指令应成功"
        print("  ✓ 结束指令正常")
    finally:
        a.shutdown()


# ============ B. 窗口约束（源码校验） ============

def test_viewer_window_rules():
    """
    核心需求: 可调整大小 + 不能关闭。
    无显示器无法真跑 Tk，改为校验源码里的关键设置。
    """
    print("\n[测试5] 被控端窗口约束（可调整大小 / 禁止关闭）")
    import viewer

    src = inspect.getsource(viewer.BroadcastViewer)

    # 1. 允许调整大小
    assert "resizable(True, True)" in src, "窗口必须允许调整大小"
    print("  resizable(True, True) ✓ 可调整大小")

    # 2. 拦截关闭
    assert "WM_DELETE_WINDOW" in src, "必须拦截窗口关闭协议"
    assert "_on_close_attempt" in src, "关闭时应给提示而不是关掉"
    print("  protocol('WM_DELETE_WINDOW') → _on_close_attempt ✓ 拦截 ✕")

    # 3. 拦截 Alt+F4（Windows 最常见的强关）
    assert 'Alt-F4' in src, "必须拦截 Alt+F4"
    print("  bind('<Alt-F4>') → break ✓ 拦截 Alt+F4")

    # 4. Escape / Ctrl+W 也拦（防止误触）
    print(f"  Escape/Ctrl+W 拦截: {'Escape' in src}")

    # 5. 关闭尝试的实现：只改提示，不 destroy
    body = inspect.getsource(viewer.BroadcastViewer._on_close_attempt)
    assert "destroy" not in body, "关闭尝试里不应真的销毁窗口"
    print("  _on_close_attempt 不含 destroy ✓ 只提示不关闭")

    # 6. 唯一合法关闭途径：bc_quit / stop()
    assert "MSG_BC_QUIT" in src, "收到 bc_quit 才关闭"
    print("  收到 MSG_BC_QUIT 才关闭 ✓ 只能由主控端结束")
    print("  ✓ 窗口约束全部满足")


def test_viewer_receive_logic():
    print("\n[测试6] 画面接收逻辑（只显示最新帧，防堆积）")
    import viewer
    src = inspect.getsource(viewer.BroadcastViewer)

    assert "queue.Queue(maxsize=2)" in src, "队列应限长，避免延迟累积"
    print("  帧队列 maxsize=2 ✓")

    # 队列满时丢弃最旧
    body = inspect.getsource(viewer.BroadcastViewer._recv_loop)
    assert "get_nowait()" in body and "full()" in body, "满了应丢旧的"
    print("  队列满时丢弃旧帧 ✓")

    # UI 用 after 在主线程更新（Tk 线程安全）
    assert "after(33" in src or "after(33," in src, "UI 应由 after 驱动"
    print("  after(33) 驱动 UI 刷新 ✓")
    print("  ✓ 不会堆积延迟，Tk 线程安全")


def test_controller_has_button():
    print("\n[测试7] 主控端有「屏幕广播」按钮")
    path = os.path.join(os.path.dirname(__file__), "controller.py")
    src = open(path, encoding="utf-8").read()

    assert "屏幕广播" in src, "工具栏应有屏幕广播按钮"
    assert "def toggle_broadcast" in src, "缺 toggle_broadcast"
    assert "def stop_broadcast" in src, "缺 stop_broadcast"
    assert "def broadcast_dialog" in src, "缺广播配置对话框"
    print("  按钮 + toggle_broadcast / stop_broadcast / broadcast_dialog ✓")

    # 结束时会通知所有目标（双保险）
    body = src[src.index("def stop_broadcast"):]
    body = body[:body.index("def control_selected")]
    assert "make_bc_stop_request" in body, "结束时应通知被控端"
    assert "srv.stop()" in body, "应先停服务（发 bc_quit）"
    print("  结束流程: 先 srv.stop() 发 bc_quit，再补发 stop 指令 ✓")
    print("  ✓ 主控端控制完整")


def test_build_config():
    print("\n[测试8] 打包配置")
    import build as b
    for mod in ("broadcast", "viewer"):
        assert mod in b.AGENT_HIDDEN or mod in b.CONTROLLER_HIDDEN, \
            f"{mod} 必须在打包隐藏导入里"
        where = "AGENT" if mod in b.AGENT_HIDDEN else "CONTROLLER"
        print(f"  {mod} 在 {where}_HIDDEN ✓")
    print("  ✓ 打包会带上广播模块")


def test_viewer_quit_behavior():
    """
    用模拟 Tk 真跑一遍:
      - 收到 bc_quit → 置停止标志 + 销毁窗口（主控端结束 = 唯一合法关闭途径）
      - 连接断开   → 也关闭（主控端崩溃时不会留下孤儿窗口）
      - 学生点关闭 → 只提示，不销毁
    """
    print("\n[测试9] 窗口关闭行为（模拟 Tk 真实调用）")
    from unittest.mock import MagicMock, patch
    import importlib
    import queue as _q

    # 让 viewer 认为有 tkinter
    sys.modules["tkinter"] = MagicMock()
    import viewer
    importlib.reload(viewer)
    print(f"  reload 后 HAS_TK={viewer.HAS_TK}")

    # ---- 1. 收到 bc_quit ----
    v = viewer.BroadcastViewer()
    v._root = MagicMock()
    v._frames = _q.Queue(maxsize=2)
    v._stop_flag = threading.Event()
    with patch.object(viewer.socket, "create_connection") as cc, \
            patch.object(viewer, "recv_all",
                         side_effect=[encode(make_bc_quit())]):
        cc.return_value = MagicMock()
        v._recv_loop("127.0.0.1", 9100)

    assert v._stop_flag.is_set(), "收到 bc_quit 后应置停止标志"
    print("  收到 bc_quit → 停止标志已置 ✓")
    v._root.after.assert_called(), "应通知 Tk 线程销毁窗口"
    print("  已安排 Tk 销毁窗口 ✓")

    # ---- 2. 连接断开（主控端没了） ----
    v2 = viewer.BroadcastViewer()
    v2._root = MagicMock()
    v2._frames = _q.Queue(maxsize=2)
    v2._stop_flag = threading.Event()
    with patch.object(viewer.socket, "create_connection") as cc, \
            patch.object(viewer, "recv_all", return_value=b""):
        cc.return_value = MagicMock()
        v2._recv_loop("127.0.0.1", 9100)
    assert v2._stop_flag.is_set(), "连接断开后应关闭窗口"
    print("  连接断开 → 自动关闭（不留孤儿窗口）✓")

    # ---- 3. 学生点 ✕：只提示，不销毁 ----
    v3 = viewer.BroadcastViewer()
    v3._root = MagicMock()
    v3.status = MagicMock()
    v3._on_close_attempt()
    v3._root.destroy.assert_not_called()
    print("  学生点 ✕ → destroy 未被调用 ✓ 窗口还在")
    assert v3.status.config.called, "应给出'无法关闭'提示"
    print("  ✓ 只能由主控端结束，学生关不掉")


if __name__ == "__main__":
    print("=" * 62)
    print("  屏幕广播 验证")
    print("=" * 62)
    test_protocol()
    test_server_push()
    test_server_quit()
    test_agent_handles_bc()
    test_viewer_window_rules()
    test_viewer_receive_logic()
    test_controller_has_button()
    test_build_config()
    test_viewer_quit_behavior()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("  （真实画面与窗口需在 Windows 教室机上验证：沙盒无显示器）")
    print("=" * 62)
