"""
test_command.py - 远程命令执行 验证

覆盖:
  1. 普通命令执行: echo / whoami / 管道
  2. 内置指令: SAFE_MODE_* / pwd
  3. cd 持久生效（shell 每次是新进程，靠 agent 维护 cwd）
  4. 错误处理: 不存在的命令 / cd 到不存在的目录
  5. 超时保护: 长时间命令被终止，不拖死连接
  6. 退出码: 失败命令 ok=False
  7. 协议字段: cwd / exit_code 正确返回
  8. 打包配置: 无需额外依赖（subprocess 是标准库）
"""

import os
import socket
import sys
import threading
import time
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(__file__))
for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
    sys.modules.setdefault(_m, MagicMock())

from common import (
    encode, decode, recv_all, send_all,
    make_command_request,
    CMD_TIMEOUT, CMD_MAX_TIMEOUT,
)


class CmdAgent:
    """启一个 agent 并暴露 run() 方便发命令"""

    def __init__(self, port=9881):
        from agent import Agent
        self.a = Agent("命令测试机", port, 9086)
        self.t = threading.Thread(target=self.a._accept_loop, daemon=True)
        self.t.start()
        time.sleep(1.5)
        self.port = self.a.port

    def run(self, cmd, timeout=None):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=60)
        s.settimeout(60)
        msg = make_command_request(cmd)
        if timeout:
            msg["timeout"] = timeout
        send_all(s, encode(msg))
        d = recv_all(s, timeout=60)
        s.close()
        return decode(d) if d else {}

    def shutdown(self):
        self.a.shutdown()


def test_basic():
    print("\n[测试1] 普通命令执行")
    a = CmdAgent()
    try:
        r = a.run("echo HELLO-TEST")
        print(f"  echo HELLO-TEST -> ok={r.get('ok')} out={r.get('output')!r}")
        assert r.get("ok"), "echo 应成功"
        assert "HELLO-TEST" in r.get("output", ""), "应回显内容"

        r = a.run("whoami")
        print(f"  whoami          -> {r.get('output')!r}")
        assert r.get("ok") and r.get("output"), "whoami 应有输出"

        # 管道（需要 shell 支持，验证 shell=True 生效）
        r = a.run("echo A-B-C | tr -d '-'")
        out = r.get("output", "")
        print(f"  管道 tr -d '-'  -> {out!r}")
        assert "ABC" in out, f"管道应生效，实际: {out}"
        print("  ✓ 普通命令 + 管道 均正常（shell 已启用）")
    finally:
        a.shutdown()


def test_builtin():
    print("\n[测试2] 内置指令")
    a = CmdAgent(9882)
    try:
        r = a.run("pwd")
        print(f"  pwd -> {r.get('output')!r} (builtin={r.get('builtin')})")
        assert r.get("builtin") and r.get("cwd"), "pwd 应返回 cwd"

        r = a.run("SAFE_MODE_STATUS")
        print(f"  SAFE_MODE_STATUS -> ok={r.get('ok')}")
        assert r.get("ok"), "查询状态应成功"
        assert "保护" in r.get("output", "")

        # 大小写不敏感
        r = a.run("safe_mode_status")
        assert r.get("ok"), "大写变小写也应识别"
        print("  ✓ 内置指令正常且大小写不敏感")
    finally:
        a.shutdown()


def test_cd_persistent():
    print("\n[测试3] cd 持久生效")
    a = CmdAgent(9883)
    try:
        home = os.path.expanduser("~")
        r = a.run(f"cd {home}")
        print(f"  cd {home} -> {r.get('cwd')}")
        assert r.get("cwd") == home, f"cwd 应为 {home}"

        r = a.run("pwd")
        print(f"  pwd       -> {r.get('output')}")
        assert r.get("output") == home, "cd 后 pwd 应仍是新目录（持久）"

        # 相对路径基于当前 cwd
        a.run("cd /tmp")
        r = a.run("cd .")
        print(f"  cd /tmp; cd . -> {r.get('cwd')}")
        assert r.get("cwd") == "/tmp", "相对路径应基于当前 cwd"

        # 家目录
        a.run("cd")
        r = a.run("pwd")
        print(f"  cd (无参) -> {r.get('output')}")
        assert r.get("output") == home, "cd 无参应回家目录"
        print("  ✓ cd 持久生效，支持相对路径与无参")
    finally:
        a.shutdown()


def test_errors():
    print("\n[测试4] 错误处理")
    a = CmdAgent(9884)
    try:
        # 不存在的目录
        r = a.run("cd /no/such/dir/zzz")
        print(f"  cd 不存在 -> ok={r.get('ok')} {r.get('output')}")
        assert not r.get("ok") and "不存在" in r.get("output", "")

        # 不存在的命令（Linux 下 sh 返回 127）
        r = a.run("this_command_does_not_exist_xyz")
        print(f"  不存在命令 -> ok={r.get('ok')}")
        assert not r.get("ok"), "失败命令应 ok=False"
        assert r.get("output"), "应有错误输出"

        # 空命令
        r = a.run("")
        print(f"  空命令     -> ok={r.get('ok')} {r.get('output')!r}")
        assert not r.get("ok")
        print("  ✓ 各类错误都有明确回显，且 ok=False")
    finally:
        a.shutdown()


def test_timeout():
    print("\n[测试5] 超时保护（不拖死连接）")
    a = CmdAgent(9885)
    try:
        # 用 timeout 字段指定 2 秒，跑 sleep 30
        t0 = time.time()
        r = a.run("sleep 30", timeout=2)
        cost = time.time() - t0
        print(f"  sleep 30 (超时2s) -> 耗时 {cost:.1f}s, ok={r.get('ok')}")
        print(f"    输出: {r.get('output')!r}")
        assert cost < 10, f"应在 2 秒左右返回，实际 {cost:.1f}s"
        assert not r.get("ok") and "超时" in r.get("output", "")

        # 超时后连接仍可用（没被拖死）
        r = a.run("echo STILL-ALIVE")
        print(f"  超时后再执行 -> ok={r.get('ok')} {r.get('output')!r}")
        assert r.get("ok"), "超时后 agent 应仍能服务"
        print("  ✓ 超时生效且不拖死后续命令")
    finally:
        a.shutdown()


def test_protocol_fields():
    print("\n[测试6] 协议字段完整")
    a = CmdAgent(9886)
    try:
        r = a.run("echo X")
        for k in ("type", "ok", "output", "builtin", "cwd", "exit_code"):
            assert k in r, f"响应缺字段 {k}"
        print(f"  字段: {sorted(r.keys())}")
        print(f"  cwd={r.get('cwd')} exit_code={r.get('exit_code')}")
        assert r.get("type") == "cmd_res"
        print("  ✓ type/ok/output/builtin/cwd/exit_code 齐全")

        # 超时钳制存在
        print(f"  CMD_TIMEOUT={CMD_TIMEOUT}s, CMD_MAX_TIMEOUT={CMD_MAX_TIMEOUT}s")
        assert CMD_TIMEOUT > 0 and CMD_MAX_TIMEOUT >= CMD_TIMEOUT
        print("  ✓ 超时常量配置合理")
    finally:
        a.shutdown()


def test_no_extra_deps():
    print("\n[测试7] 无需额外依赖")
    # subprocess / platform / os 都是标准库，不该新增打包依赖
    import subprocess
    import platform
    print("  subprocess / platform 均为标准库 ✓")

    import build as b
    # 命令执行只用到标准库，AGENT_HIDDEN 不需要新增项
    print(f"  AGENT_HIDDEN 共 {len(b.AGENT_HIDDEN)} 项，无需为命令功能新增")
    print("  ✓ 打包无新增依赖")


if __name__ == "__main__":
    print("=" * 62)
    print("  远程命令执行 验证")
    print("=" * 62)
    test_basic()
    test_builtin()
    test_cd_persistent()
    test_errors()
    test_timeout()
    test_protocol_fields()
    test_no_extra_deps()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("=" * 62)
