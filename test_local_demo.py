"""
test_local_demo.py - 验证「单机多 Agent」演示方案
场景: 一台电脑上同时跑 3 个 Agent(各自不同 TCP 端口)，都广播到控制端 9000 端口。
      控制端应能发现 3 台并分别连上各自端口拉取缩略图。
这正是 VS Code 里 compound 启动配置所依赖的机制。
"""
import socket
import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from common import encode, decode, make_thumb_request, b64_decode, MSG_THUMB_RESPONSE
from agent import Agent

CTRL_PORT = 9400          # 控制端监听端口
AGENT_PORTS = [9401, 9402, 9403]


class LocalAgent(Agent):
    """只启动 TCP + 广播，不阻塞主线程"""
    def __init__(self, name, port, ctrl_port):
        super().__init__(name, "127.0.0.1", port, broadcast_port=ctrl_port)

    def start_bg(self):
        threading.Thread(target=self._run_bg, daemon=True).start()

    def _run_bg(self):
        self.start_broadcast()
        self.start_tcp_server()
        while self.running:
            time.sleep(0.5)


def fetch_thumb(ip, port) -> bytes:
    """模拟控制端: 连接 agent 自身端口请求缩略图"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    sock.connect((ip, port))
    sock.sendall(encode(make_thumb_request(160, 100)))
    header = sock.recv(4)
    length = int.from_bytes(header, "big")
    payload = sock.recv(length)
    sock.close()
    resp = decode(header + payload)
    if resp.get("type") == MSG_THUMB_RESPONSE:
        return b64_decode(resp["thumb"])
    return b""


def main():
    print("=" * 56)
    print("  单机多 Agent 演示验证 (VS Code compound 场景)")
    print("=" * 56)

    # 1. 启动 3 个 Agent，各自不同端口，都广播到 CTRL_PORT
    agents = []
    for i, p in enumerate(AGENT_PORTS, 1):
        a = LocalAgent(f"演示机-{i:02d}", p, CTRL_PORT)
        a.start_bg()
        agents.append(a)
    time.sleep(1.0)
    print(f"\n[1] 已启动 {len(agents)} 个 Agent:")
    for a in agents:
        print(f"     {a.name}  TCP监听:{a.port}  ->  广播到 127.0.0.1:{a.broadcast_port}")

    # 2. 控制端监听 CTRL_PORT，收集广播
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.bind(("0.0.0.0", CTRL_PORT))
    udp.settimeout(6)

    discovered = {}    # id -> {name, port, ip}
    deadline = time.time() + 6
    print(f"\n[2] 控制端监听 127.0.0.1:{CTRL_PORT}，等待广播...")
    while time.time() < deadline and len(discovered) < 3:
        try:
            data, addr = udp.recvfrom(65535)
            msg = decode(data)
            if msg.get("type") == "hello":
                mid = msg.get("id")
                if mid not in discovered:
                    discovered[mid] = {
                        "name": msg["name"],
                        "port": msg["port"],
                        "ip": addr[0],
                        "thumb": msg.get("thumb", ""),
                    }
        except socket.timeout:
            break
    udp.close()

    print(f"    发现 {len(discovered)} 台机器:")
    for mid, info in discovered.items():
        has_thumb = "有缩略图" if info["thumb"] else "无缩略图"
        print(f"     ✓ {info['name']}  @ {info['ip']}:{info['port']}  ({has_thumb})")

    assert len(discovered) == 3, f"应发现3台，实际{len(discovered)}"

    # 3. 控制端按各自 port 去连，拉取缩略图
    print(f"\n[3] 控制端分别连接各自端口拉取缩略图:")
    ok = 0
    for mid, info in discovered.items():
        jpeg = fetch_thumb(info["ip"], info["port"])
        if jpeg and jpeg[:2] == b"\xff\xd8":
            print(f"     ✓ {info['name']} -> JPEG {len(jpeg)} bytes (端口 {info['port']})")
            ok += 1
        else:
            print(f"     ✗ {info['name']} 拉取失败")
    assert ok == 3, f"3台都应拉到缩略图，实际{ok}"

    # 4. 验证: 各自端口不同但广播目标一致
    ports = [info["port"] for info in discovered.values()]
    assert len(set(ports)) == 3, "各自 TCP 端口应互不相同"
    print(f"\n[4] 端口隔离验证: 自身端口 {sorted(ports)} 各不相同 -> 单机可并存 ✓")

    for a in agents:
        a.shutdown()

    print("\n" + "=" * 56)
    print("  ✓ 单机多 Agent 方案可行！预览墙可显示多张卡片")
    print("=" * 56)


if __name__ == "__main__":
    main()
