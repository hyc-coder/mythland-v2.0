"""
test_logic.py - 纯逻辑验证Agent与Controller通信（TCP直连模拟局域网）
"""
import socket
import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from common import (
    encode, decode, make_hello, make_heartbeat, make_list_response,
    MSG_HEARTBEAT, MSG_LIST_REQUEST,
)

# 全局端口分配器，避免冲突
_PORT_COUNTER = [9200]

def next_port():
    _PORT_COUNTER[0] += 1
    return _PORT_COUNTER[0]


def test_protocol():
    """测试1: 协议编解码"""
    print("\n[测试1] 协议编解码")
    msg = make_hello("学生机01", "Windows 11")
    data = encode(msg)
    decoded = decode(data)
    assert decoded["type"] == "hello"
    assert decoded["name"] == "学生机01"
    print(f"  ✓ 编码->解码 正确: {decoded['name']} / {decoded['os']}")


class MockAgent:
    """模拟Agent的TCP服务"""
    def __init__(self, name, os_info, mid, port):
        self.name = name
        self.os_info = os_info
        self.mid = mid
        self.port = port
        self.tcp = None
        self._stop = False

    def start(self):
        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp.bind(("127.0.0.1", self.port))
        self.tcp.listen(5)

        def accept_loop():
            while not self._stop:
                try:
                    self.tcp.settimeout(0.5)
                    conn, addr = self.tcp.accept()
                    threading.Thread(
                        target=self.handle_client, args=(conn,), daemon=True
                    ).start()
                except socket.timeout:
                    continue
                except:
                    break

        threading.Thread(target=accept_loop, daemon=True).start()
        print(f"  [Agent] {self.name} @ 127.0.0.1:{self.port}")

    def handle_client(self, conn):
        try:
            while True:
                header = conn.recv(4)
                if not header:
                    break
                length = int.from_bytes(header, "big")
                payload = b""
                while len(payload) < length:
                    chunk = conn.recv(length - len(payload))
                    if not chunk:
                        break
                    payload += chunk

                msg = decode(header + payload)
                msg_type = msg.get("type")

                if msg_type == MSG_HEARTBEAT:
                    conn.sendall(encode(make_heartbeat()))
                elif msg_type == MSG_LIST_REQUEST:
                    info = {
                        "id": self.mid,
                        "name": self.name,
                        "os": self.os_info,
                        "status": "online",
                    }
                    conn.sendall(encode(make_list_response([info])))
        except:
            pass
        finally:
            conn.close()

    def stop(self):
        self._stop = True
        if self.tcp:
            self.tcp.close()


def request(agent, msg_dict):
    """模拟控制端发送请求并接收响应"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", agent.port))
    sock.sendall(encode(msg_dict))
    header = sock.recv(4)
    length = int.from_bytes(header, "big")
    payload = sock.recv(length)
    sock.close()
    return decode(header + payload)


def test_heartbeat():
    """测试2: 心跳"""
    print("\n[测试2] 心跳检测")
    port = next_port()
    agent = MockAgent("学生机-A", "Windows 11", "agent-aaa", port)
    agent.start()
    time.sleep(0.3)

    response = request(agent, make_heartbeat())
    assert response["type"] == MSG_HEARTBEAT
    print("  ✓ 心跳往返正常")
    agent.stop()


def test_machine_list():
    """测试3: 单台机器列表"""
    print("\n[测试3] 机器列表请求")
    port = next_port()
    agent = MockAgent("学生机-B", "Windows 10", "agent-bbb", port)
    agent.start()
    time.sleep(0.3)

    response = request(agent, {"type": MSG_LIST_REQUEST})
    assert response["type"] == "list_res"
    assert len(response["machines"]) == 1
    m = response["machines"][0]
    assert m["name"] == "学生机-B"
    print(f"  ✓ 收到: {m['name']} / {m['os']} / {m['status']}")
    agent.stop()


def test_multiple_agents():
    """测试4: 多台Agent并发（教室场景）"""
    print("\n[测试4] 多机器并发管理")

    configs = [
        ("学生机-01", "Windows 11", "id-001"),
        ("学生机-02", "Windows 10", "id-002"),
        ("学生机-03", "Windows 11", "id-003"),
        ("学生机-04", "Windows 7",  "id-004"),
        ("学生机-05", "Windows 10", "id-005"),
    ]

    agents = []
    for name, os_info, mid in configs:
        port = next_port()
        a = MockAgent(name, os_info, mid, port)
        a.start()
        agents.append(a)

    time.sleep(0.5)

    # 控制端收集所有机器信息
    results = []
    for a in agents:
        response = request(a, {"type": MSG_LIST_REQUEST})
        results.extend(response["machines"])

    assert len(results) == 5, f"期望5台，实际{len(results)}"
    for r in results:
        print(f"  ✓ {r['name']:12s} {r['os']:12s} [{r['status']}]")

    for a in agents:
        a.stop()
    print(f"  ✓ 共发现 {len(results)} 台机器")


def test_offline_detection():
    """测试5: 模拟机器离线检测逻辑"""
    print("\n[测试5] 离线检测逻辑")

    class FakeMachine:
        def __init__(self, name, last_seen_offset):
            self.name = name
            self.last_seen = time.time() - last_seen_offset
            self.status = "online"

        def check_timeout(self, timeout):
            if time.time() - self.last_seen > timeout:
                self.status = "offline"

    machines = [
        FakeMachine("在线机", 2),     # 2秒前活跃
        FakeMachine("离线机", 30),    # 30秒前，应标记为离线
        FakeMachine("在线机2", 1),    # 1秒前活跃
    ]

    TIMEOUT = 15
    for m in machines:
        m.check_timeout(TIMEOUT)

    statuses = {m.name: m.status for m in machines}
    assert statuses["离线机"] == "offline", "30秒未活跃应标记离线"
    assert statuses["在线机"] == "online"
    assert statuses["在线机2"] == "online"
    print(f"  ✓ 在线: 在线机, 在线机2")
    print(f"  ✓ 离线: 离线机 (超过{TIMEOUT}秒无心跳)")
    print("  ✓ 离线检测逻辑正确")


if __name__ == "__main__":
    print("=" * 50)
    print("  远控软件 - 通信逻辑测试")
    print("=" * 50)

    test_protocol()
    test_heartbeat()
    test_machine_list()
    test_multiple_agents()
    test_offline_detection()

    print("\n" + "=" * 50)
    print("  全部测试通过! ✓")
    print("=" * 50)
