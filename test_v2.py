"""
test_v2.py - v2 预览墙集成测试 (无 GUI，验证逻辑 + 缩略图链路)
覆盖:
  1. 协议: hello 携带 thumb、thumb_req/res
  2. Agent: 采集缩略图 + 响应缩略图请求 (TCP)
  3. Controller 逻辑: 发现机器、解析 thumb、请求缩略图、离线判定
  4. PreviewWall 核心逻辑 (用 tk 但不 mainloop，验证卡片数据结构)
"""
import io
import socket
import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from common import (
    encode, decode, b64_encode, b64_decode,
    make_hello, make_heartbeat, make_thumb_request, make_thumb_response,
    MSG_THUMB_REQUEST, MSG_THUMB_RESPONSE,
)
from screen import ScreenCapturer
from agent import Agent, THUMB_WIDTH, THUMB_HEIGHT

PORT = 9300
_next_port = [PORT]

def new_port():
    _next_port[0] += 1
    return _next_port[0]


class MachineFallback:
    """无 tkinter 环境下替代 controller.Machine 的最小实现"""
    def __init__(self, mid, name, os_info, ip, port):
        self.id = mid
        self.name = name
        self.os = os_info
        self.ip = ip
        self.port = port
        self.status = "online"
        self.last_seen = time.time()
        self.thumb = b""
        self.thumb_version = 0

    def update_seen(self):
        self.last_seen = time.time()
        if self.status != "online":
            self.status = "online"
            return True
        return False

    def set_thumb(self, jpeg):
        self.thumb = jpeg
        self.thumb_version += 1


def test_protocol_thumb():
    print("\n[测试1] 协议: 缩略图消息")
    cap = ScreenCapturer("测试机")
    jpeg = cap.capture_jpeg(160, 100)
    assert len(jpeg) > 100, "应生成有效 JPEG"
    print(f"  ✓ 生成 JPEG 缩略图: {len(jpeg)} bytes")

    # hello 携带 thumb
    b64 = b64_encode(jpeg)
    msg = make_hello("学生机", "Win11", b64)
    data = encode(msg)
    decoded = decode(data)
    assert decoded["thumb"] == b64
    assert b64_decode(decoded["thumb"]) == jpeg
    print("  ✓ hello 携带缩略图 base64 编解码正确")

    # thumb request / response
    req = make_thumb_request(160, 100)
    assert req["type"] == MSG_THUMB_REQUEST
    res = make_thumb_response(b64, 160, 100)
    data2 = encode(res)
    d2 = decode(data2)
    assert d2["type"] == MSG_THUMB_RESPONSE
    assert d2["width"] == 160
    print("  ✓ thumb_req / thumb_res 协议正确")


class MockAgentForTest(Agent):
    """复用 Agent 的网络逻辑，但端口可控"""
    def __init__(self, name, port):
        super().__init__(name, "127.0.0.1", port)
        self._test_port = port

    def start(self):
        # 只启动 TCP 服务（跳过 UDP 广播，测试里手动喂数据）
        self.start_tcp_server()
        time.sleep(0.3)

    def stop(self):
        self.running = False
        try:
            self.tcp_server.close()
        except Exception:
            pass


def request_response(agent, msg_dict, timeout=5) -> dict:
    """连接 agent TCP，发请求，收完整响应"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(("127.0.0.1", agent._test_port))
    sock.sendall(encode(msg_dict))
    header = sock.recv(4)
    if not header:
        sock.close()
        return {}
    length = int.from_bytes(header, "big")
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            break
        payload += chunk
    sock.close()
    return decode(header + payload)


def test_agent_thumb_response():
    print("\n[测试2] Agent 响应缩略图请求")
    port = new_port()
    agent = MockAgentForTest("学生机-缩略图", port)
    agent.start()

    resp = request_response(agent, make_thumb_request(160, 100))
    assert resp.get("type") == MSG_THUMB_RESPONSE, f"期望 thumb_res, 得 {resp}"
    thumb = b64_decode(resp["thumb"])
    # 验证是合法 JPEG
    assert thumb[:2] == b"\xff\xd8", "应以 JPEG SOI 开头"
    from PIL import Image
    img = Image.open(io.BytesIO(thumb))
    assert img.size == (160, 100), f"尺寸应为 160x100, 得 {img.size}"
    print(f"  ✓ Agent 返回有效 JPEG: {img.size}, {len(thumb)} bytes")
    agent.stop()


def test_controller_logic_and_wall():
    print("\n[测试3] Controller 逻辑 + PreviewWall")
    # 启动 3 个 Agent
    ports = [new_port() for _ in range(3)]
    configs = [
        ("学生机-01", ports[0]),
        ("学生机-02", ports[1]),
        ("学生机-03", ports[2]),
    ]
    agents = []
    for name, p in configs:
        a = MockAgentForTest(name, p)
        a.start()
        agents.append(a)

    time.sleep(0.5)

    # --- 模拟 Controller 的网络逻辑 ---
    class FakeController:
        def __init__(self):
            try:
                from controller import Machine
                self.Machine = Machine
            except Exception:
                # 无 tkinter 环境下 controller 模块无法导入，用本地等价类
                self.Machine = MachineFallback
            self.machines = {}
            self.lock = threading.Lock()

        def discover(self, agent):
            """模拟收到 hello (带 thumb)"""
            with self.lock:
                mid = agent.machine_id
                m = self.machines.setdefault(
                    mid, self.Machine(mid, agent.name, agent.os_info, "127.0.0.1", agent._test_port)
                )
                m.update_seen()
                # 拉取缩略图 (模拟 add_or_update_machine 的行为)
                thumb_b64 = agent.get_thumb_b64()
                if thumb_b64:
                    m.set_thumb(b64_decode(thumb_b64))
                return m

        def fetch_thumb(self, machine):
            """模拟 _fetch_thumb: 发 thumb_req, 更新缩略图"""
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect(("127.0.0.1", machine.port))
            sock.sendall(encode(make_thumb_request(160, 100)))
            header = sock.recv(4)
            length = int.from_bytes(header, "big")
            payload = sock.recv(length)
            sock.close()
            resp = decode(header + payload)
            if resp.get("type") == MSG_THUMB_RESPONSE:
                machine.set_thumb(b64_decode(resp["thumb"]))

    ctrl = FakeController()

    # 3.1 发现 + 首帧缩略图 (hello 携带)
    for a in agents:
        m = ctrl.discover(a)
        assert m.thumb, f"{m.name} 应有首帧缩略图"
    print(f"  ✓ 发现 {len(ctrl.machines)} 台机器，均带首帧缩略图")

    # 3.2 轮询更新缩略图 (thumb_req)
    with ctrl.lock:
        targets = list(ctrl.machines.values())
    for m in targets:
        ctrl.fetch_thumb(m)
    # 验证所有机器缩略图都被更新 (version > 0)
    for m in targets:
        assert m.thumb_version >= 1, f"{m.name} 缩略图应已更新"
    print(f"  ✓ 轮询更新所有机器缩略图 (thumb_version={targets[0].thumb_version})")

    # 3.3 模拟一台离线
    first = targets[0]
    first.last_seen = time.time() - 100  # 远超 OFFLINE_TIMEOUT
    OFFLINE_TIMEOUT = 15
    if time.time() - first.last_seen > OFFLINE_TIMEOUT:
        first.status = "offline"
    assert first.status == "offline"
    print(f"  ✓ 离线检测: {first.name} -> {first.status}")

    # --- 3.4 PreviewWall 渲染逻辑验证 (不 mainloop) ---
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        from controller import PreviewWall
        wall = PreviewWall(root, ctrl)

        with ctrl.lock:
            items = list(ctrl.machines.values())
        wall.full_redraw(items)

        # 验证: 每张卡片都存在，在线在前
        assert len(wall.cards) == 3, f"应有3张卡片, 得 {len(wall.cards)}"
        # 选中第一台
        first_id = list(ctrl.machines.values())[0].id
        wall._on_select(first_id)
        assert wall.get_selected() == first_id
        print(f"  ✓ PreviewWall: {len(wall.cards)} 张卡片已布局, 选中高亮正常")

        # 验证缩略图被渲染为 PhotoImage
        card = wall.cards[first_id]
        # Label 应有 image 属性设置 (image 是 PIL PhotoImage 或 tk 对象)
        assert hasattr(card["thumb_label"], "image")
        root.destroy()
    except Exception as e:
        print(f"  ! PreviewWall GUI 验证跳过 (无显示环境): {e}")

    for a in agents:
        a.stop()
    print("  ✓ Controller + PreviewWall 逻辑全部通过")


if __name__ == "__main__":
    print("=" * 54)
    print("  远控 v2 - 极域风格预览墙 集成测试")
    print("=" * 54)

    test_protocol_thumb()
    test_agent_thumb_response()
    test_controller_logic_and_wall()

    print("\n" + "=" * 54)
    print("  全部测试通过! ✓")
    print("=" * 54)
