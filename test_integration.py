"""
test_integration.py - 模拟一个Agent，向本地广播端口发送hello，验证Controller能发现
（不启动GUI，仅验证逻辑）
"""
import socket
import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from common import encode, make_hello

PORT = 9000

def mock_agent():
    """模拟被控端发送UDP广播"""
    time.sleep(1)  # 等controller先启动监听
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    msg = make_hello("模拟学生机", "Windows 11")
    msg["id"] = "test-001"
    msg["port"] = PORT
    data = encode(msg)
    # 发送到本地回环的广播
    udp.sendto(data, ("127.0.0.1", PORT))
    print("[MockAgent] 已发送hello广播")
    udp.close()

def main():
    from controller import Controller, Machine
    import tkinter as tk

    # 启动mock agent线程
    threading.Thread(target=mock_agent, daemon=True).start()

    # 创建controller（无GUI模式，直接调用逻辑）
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    ctrl = Controller(PORT, root)

    # 等待接收
    time.sleep(3)

    # 检查结果
    with ctrl.lock:
        machines = list(ctrl.machines.values())

    print(f"\n[结果] 发现的机器数: {len(machines)}")
    for m in machines:
        print(f"  - {m.name} @ {m.ip} ({m.os}) [{m.status}]")

    assert len(machines) >= 1, "应该至少发现1台机器"
    assert machines[0].name == "模拟学生机"
    print("\n[通过] Controller成功发现Agent! ✓")

    ctrl.shutdown()
    root.destroy()

if __name__ == "__main__":
    main()
