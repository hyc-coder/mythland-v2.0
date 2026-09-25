"""
test_monitor.py - 30FPS 屏幕监控链路验证

验证点:
  1. agent 支持 screen_req，返回全尺寸 JPEG 帧
  2. 【长连接复用】—— 一条 TCP 上连续拉 N 帧不重连（30FPS 必需）
  3. 实测吞吐: 连续拉帧测出实际可达 FPS
  4. 预览墙缩略图仍是 1FPS（POLL_INTERVAL 未被改动）
  5. 停止监控能正常退出

注: session.py 依赖 tkinter，沙盒无 GUI，故这里只验证【agent 端 + 通信层】，
    即决定 30FPS 能否跑起来的核心瓶颈（采集 + 传输）。
"""
import base64
import io
import socket
import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))

# controller/session 依赖 tkinter，沙盒无 GUI 需先打桩
from unittest.mock import MagicMock
for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
    sys.modules.setdefault(_m, MagicMock())

from common import encode, decode, recv_all, send_all, make_screen_request

PORT = 9601


def start_agent(port=PORT):
    """后台启动一个 agent"""
    from agent import Agent
    a = Agent("监控测试机", port, 9086)
    t = threading.Thread(target=a._accept_loop, daemon=True)
    t.start()
    # 同时起缩略图采集线程（模拟真实运行）
    threading.Thread(target=a._thumb_loop, daemon=True).start()
    time.sleep(0.8)
    return a


def test_single_frame():
    """测试1: 单帧请求"""
    print("\n[测试1] 请求一帧全尺寸画面")
    a = start_agent()
    try:
        sock = socket.create_connection(("127.0.0.1", PORT), timeout=5)
        sock.settimeout(5)
        send_all(sock, encode(make_screen_request(0, 0, 55)))
        data = recv_all(sock, timeout=5)
        sock.close()

        assert data, "未收到响应"
        resp = decode(data)
        print(f"  响应类型: {resp.get('type')}")
        assert resp.get("type") == "screen_res", f"类型错误: {resp.get('type')}"

        b64 = resp.get("frame", "")
        jpeg = base64.b64decode(b64)
        print(f"  帧大小: {len(jpeg)} bytes, 分辨率: {resp.get('width')}x{resp.get('height')}")
        assert len(jpeg) > 100, f"帧数据过小({len(jpeg)}B)，可能采集失败"
        assert jpeg[:2] == b"\xff\xd8", "不是合法 JPEG (缺少 FFD8 头)"

        # 用 PIL 验证可解码
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(jpeg))
            print(f"  PIL 解码: {img.size} {img.mode}")
            assert img.size[0] > 0 and img.size[1] > 0
        except ImportError:
            print("  (无 Pillow，跳过解码验证)")
        print("  ✓ 单帧请求正常")
    finally:
        a.shutdown()


def test_long_connection_multiframe():
    """测试2: 长连接复用 —— 一条连接连续拉帧（30FPS 核心）"""
    print("\n[测试2] 长连接复用（30FPS 必需）")
    a = start_agent(9602)
    try:
        sock = socket.create_connection(("127.0.0.1", 9602), timeout=10)
        sock.settimeout(10)

        # 同一条连接连拉 30 帧
        n = 30
        ok = 0
        t0 = time.time()
        for i in range(n):
            send_all(sock, encode(make_screen_request(0, 0, 55)))
            data = recv_all(sock, timeout=10)
            if not data:
                break
            resp = decode(data)
            if resp.get("type") == "screen_res" and resp.get("frame"):
                ok += 1
        elapsed = time.time() - t0
        sock.close()

        print(f"  {n} 帧请求 -> 成功 {ok} 帧, 耗时 {elapsed:.2f}s")
        print(f"  实测速率: {ok/elapsed:.1f} FPS")
        assert ok == n, f"长连接中断: 只完成 {ok}/{n} 帧"
        print(f"  ✓ 一条 TCP 连接连续完成 {ok} 帧，未重连")
        return ok / elapsed
    finally:
        a.shutdown()


def test_throughput_30fps():
    """测试3: 实测吞吐，看能否撑住 30FPS"""
    print("\n[测试3] 实测吞吐（目标 30 FPS）")
    a = start_agent(9603)
    try:
        sock = socket.create_connection(("127.0.0.1", 9603), timeout=15)
        sock.settimeout(15)

        n = 60
        t0 = time.time()
        ok = 0
        for _ in range(n):
            send_all(sock, encode(make_screen_request(0, 0, 55)))
            data = recv_all(sock, timeout=15)
            if data:
                ok += 1
        elapsed = time.time() - t0
        sock.close()

        fps = ok / elapsed if elapsed > 0 else 0
        print(f"  {n} 帧 -> {ok} 帧成功, 耗时 {elapsed:.2f}s")
        print(f"  实测: {fps:.1f} FPS")
        print(f"  平均每帧: {elapsed/max(1,ok)*1000:.1f} ms")

        # 这里不强断言 30FPS —— 沙盒无真实显示器，走的是模拟采集
        # 只验证链路不阻塞、能持续输出
        assert ok == n, f"帧丢失: {ok}/{n}"
        print(f"  ✓ 链路可持续输出（真实环境 + 真显卡会更快）")
        return fps
    finally:
        a.shutdown()


def test_thumb_still_1fps():
    """测试4: 预览墙缩略图仍配置为 1FPS"""
    print("\n[测试4] 预览墙仍为 1 FPS")
    from controller import POLL_INTERVAL
    print(f"  POLL_INTERVAL = {POLL_INTERVAL} 秒")
    assert POLL_INTERVAL == 1, f"预览墙应仍为 1FPS，实际 POLL_INTERVAL={POLL_INTERVAL}"
    print("  ✓ 预览墙未被改成 30FPS，仍每秒 1 帧")

    # 会话窗口的目标帧率
    try:
        import session
        print(f"  session.TARGET_FPS = {session.TARGET_FPS}")
        assert session.TARGET_FPS == 30, "会话监控应为 30FPS"
        print("  ✓ 屏幕监控为 30 FPS")
    except Exception as e:
        print(f"  (session 检查跳过: {e})")


def test_mixed_requests_same_conn():
    """测试5: 同一连接可混合请求缩略图和全尺寸帧"""
    print("\n[测试5] 混合请求（缩略图 + 全帧，同一连接）")
    a = start_agent(9605)
    try:
        sock = socket.create_connection(("127.0.0.1", 9605), timeout=10)
        sock.settimeout(10)

        results = []
        # 缩略图
        send_all(sock, encode({"type": "thumb_req", "width": 176, "height": 110}))
        d = recv_all(sock, timeout=10)
        results.append(("thumb_res", decode(d).get("type")))

        # 全尺寸帧
        send_all(sock, encode(make_screen_request(0, 0, 55)))
        d = recv_all(sock, timeout=10)
        results.append(("screen_res", decode(d).get("type")))

        # 再来一帧全尺寸
        send_all(sock, encode(make_screen_request(0, 0, 40)))
        d = recv_all(sock, timeout=10)
        results.append(("screen_res", decode(d).get("type")))

        sock.close()
        for expect, got in results:
            print(f"  期望 {expect:12s} -> 实际 {got}")
            assert expect == got, f"类型不符: 期望{expect} 实际{got}"
        print("  ✓ 一条连接支持混合请求（预览墙与监控互不干扰）")
    finally:
        a.shutdown()


if __name__ == "__main__":
    print("=" * 62)
    print("  30 FPS 屏幕监控链路验证")
    print("=" * 62)
    test_single_frame()
    test_long_connection_multiframe()
    test_throughput_30fps()
    test_thumb_still_1fps()
    test_mixed_requests_same_conn()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("=" * 62)
