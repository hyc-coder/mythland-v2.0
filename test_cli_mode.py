"""
test_cli_mode.py - 验证 controller.py 的 CLI 探测模式
在同一进程内: 启动 agent 线程广播 -> 跑 cli_main 监听 -> 应能发现机器
(避免沙盒后台常驻进程问题)
"""
import socket
import threading
import time
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(__file__))

# 沙盒/CI 环境常无 tkinter，给 controller 的 GUI 依赖打桩
# （cli_main 本身不碰 GUI，桩只为让模块能被 import）
for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
    sys.modules.setdefault(_m, MagicMock())

from agent import Agent
from controller import cli_main

CTRL_PORT = 9700


class LocalAgent(Agent):
    """线程内运行的 agent（不阻塞）"""
    def __init__(self, name, port, ctrl_port):
        super().__init__(name, "127.0.0.1", port, broadcast_port=ctrl_port)

    def start_bg(self):
        threading.Thread(target=self._run_bg, daemon=True).start()

    def _run_bg(self):
        self.start_broadcast()
        self.start_tcp_server()
        while self.running:
            time.sleep(0.5)


def main():
    print("=" * 60)
    print("  CLI 探测模式验证")
    print("=" * 60)

    # 启动 2 个 agent（各自不同端口，都广播到 CTRL_PORT）
    agents = [
        LocalAgent("演示机-01", 9701, CTRL_PORT),
        LocalAgent("演示机-02", 9702, CTRL_PORT),
    ]
    for a in agents:
        a.start_bg()
    time.sleep(1.5)
    print(f"\n已启动 {len(agents)} 个 agent，均广播到 127.0.0.1:{CTRL_PORT}\n")

    # 跑 CLI 探测（8 秒）
    print("-" * 60)
    cli_main(CTRL_PORT, duration=8)
    print("-" * 60)

    for a in agents:
        a.shutdown()

    print("\n[结论] 若上面显示'共发现 2 台'，CLI 模式工作正常 ✓")
    print("       用户可用 `python controller.py --cli` 确认链路是否连通")


if __name__ == "__main__":
    main()
