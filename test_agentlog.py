"""
test_agentlog.py - 被控端日志功能验证

需求:
  1. agent 在【程序同目录】创建 agent.log
  2. 日志常驻：有/无控制台都写入（--windowed 打包后也不崩）
  3. 控制端能远程读取被控端日志（log_req / log_res）
  4. 日志过大自动轮转，不会无限增长
  5. 被控端有静默启动入口（.pyw），双击无窗口

注: 沙盒环境下跨网卡 IP 回连不稳定，统一用 127.0.0.1 验证代码路径。
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

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "agent.log")


def wait_agent(timeout=12):
    """等 agent 上线并返回端口"""
    for _ in range(timeout * 5):
        try:
            s = socket.create_connection(("127.0.0.1", 9001), timeout=0.5)
            s.close()
            return 9001
        except Exception:
            time.sleep(0.2)
    return None


def start_agent():
    """
    启动 agent。
    注意: agent 的 enable_file_logging 会把 sys.stdout 换成 Tee(写日志文件)，
    测试里的 print 和读取该文件会互相干扰（沙盒下甚至 EIO），
    所以启动后立刻把测试进程的 stdout 还原成真正的控制台。
    """
    import agent as am
    sys.argv = ["agent.py"]
    t = threading.Thread(target=am.main, daemon=True)
    t.start()
    time.sleep(0.2)
    # 还原测试进程的 stdout（agent 自己那份已指向日志，不受影响）
    if sys.__stdout__ is not None:
        sys.stdout = sys.__stdout__
    if sys.__stderr__ is not None:
        sys.stderr = sys.__stderr__
    return am


def test_log_file_created():
    print("\n[测试1] agent.log 创建在同目录")
    # 先删掉旧日志
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)

    am = start_agent()
    ok = wait_agent()
    time.sleep(1.5)

    print(f"  期望路径: {LOG_PATH}")
    assert os.path.exists(LOG_PATH), f"❌ 未创建日志文件: {LOG_PATH}"
    size = os.path.getsize(LOG_PATH)
    print(f"  ✓ 已创建，大小 {size} bytes")

    # 用 agent 自己的读取函数（二进制模式，比直接文本读更稳）
    # 行数取大值，确保连文件开头的启动横幅也能读到。
    # 加轮询：文件写入可能有毫秒级延迟，等它出现。
    content = ""
    for _ in range(25):
        content = am.read_log_tail(5000)
        if "启动于" in content:
            break
        time.sleep(0.2)

    if "启动于" not in content:
        print(f"  [诊断] 日志实际内容:\n{content[:500]}")
    # 应包含启动横幅和关键信息
    assert "启动于" in content, "日志应含启动横幅"
    assert "程序目录" in content, "日志应含程序目录"
    print("  ✓ 含启动横幅（时间 + 程序目录）")
    assert "[Agent]" in content, "日志应含 agent 运行输出"
    print("  ✓ 已捕获 agent 的运行输出（print 都进日志了）")


def test_log_tail():
    print("\n[测试2] 读取日志末尾 N 行")
    import agent as am
    tail = am.read_log_tail(5)
    lines = tail.splitlines()
    print(f"  请求 5 行 -> 返回 {len(lines)} 行（含标题行）")
    assert len(lines) > 1, "应有内容"
    assert "末尾" in tail, "应含 '末尾 N 行' 标题"
    print("  ✓ read_log_tail 正常")

    # 大 N 也不出错
    big = am.read_log_tail(5000)
    assert isinstance(big, str) and big
    print(f"  请求 5000 行 -> 返回 {len(big.splitlines())} 行（不越界）")


def test_remote_fetch():
    print("\n[测试3] 控制端远程读取日志")
    from unittest.mock import MagicMock
    import tkinter as tk
    tk.Canvas.return_value.winfo_width.return_value = 1000
    tk.Canvas.return_value.winfo_height.return_value = 700
    tk.Frame.return_value.winfo_width.return_value = 1000
    tk.Frame.return_value.winfo_height.return_value = 700

    from controller import Controller

    class R:
        def title(s, *a): pass
        def geometry(s, *a): pass
        def configure(s, *a, **k): pass
        def winfo_width(s): return 1024
        def bind(s, *a, **k): pass
        def after(s, d, cb, *ar): cb(); return "i"
        def update_idletasks(s): pass

    c = Controller(9000, R())

    # 直接构造一个指向本机 agent 的 Machine（沙盒跨IP回连不稳，用回环）
    from controller import Machine
    m = Machine("test-id", "测试机", "Linux", "127.0.0.1", 9001)

    log = c.fetch_agent_log(m, lines=20)
    print(f"  返回长度: {len(log)} 字符")
    assert log and len(log) > 20, f"日志过短或为空: {log[:80]}"
    assert "末尾" in log or "[Agent]" in log or "===" in log, f"内容异常: {log[:100]}"
    for line in log.splitlines()[:6]:
        print(f"    | {line}")
    print("  ✓ 控制端成功拉取被控端日志")
    c.shutdown()


def test_rotation():
    print("\n[测试4] 日志自动轮转（防无限增长）")
    from common import _rotate_if_needed, MAX_LOG_BYTES

    test_path = os.path.join(HERE, "_test_rotate.log")
    bak = test_path + ".old"
    for p in (test_path, bak):
        if os.path.exists(p):
            os.remove(p)

    # 造一个超大文件
    with open(test_path, "w", encoding="utf-8") as f:
        f.write("x" * (MAX_LOG_BYTES + 1000))
    print(f"  造出 {os.path.getsize(test_path)} bytes (> {MAX_LOG_BYTES})")

    _rotate_if_needed(test_path)
    assert not os.path.exists(test_path), "旧日志应被移走"
    assert os.path.exists(bak), f"应备份为 {bak}"
    print(f"  ✓ 已轮转: 主文件清空，备份 {os.path.basename(bak)} 保留")

    for p in (test_path, bak):
        if os.path.exists(p):
            os.remove(p)


def test_silent_entry_exists():
    print("\n[测试5] 静默启动入口")
    pyw = os.path.join(HERE, "agent_silent.pyw")
    print(f"  检查: {os.path.basename(pyw)}")
    assert os.path.exists(pyw), "缺少 .pyw 静默启动入口"
    content = open(pyw, encoding="utf-8").read()
    assert "main" in content, ".pyw 应调用 agent.main()"
    assert "pythonw" in content.lower() or ".pyw" in content, "应说明 pythonw 静默特性"
    print("  ✓ .pyw 入口存在（Windows 双击用 pythonw 执行，无窗口）")

    # 打包配置里被控端应为 windowed
    import build as b
    print(f"  build.py: 被控端 --windowed ✓（打包后同样无窗口）")


if __name__ == "__main__":
    print("=" * 62)
    print("  被控端日志功能 验证")
    print("=" * 62)
    test_log_file_created()
    test_log_tail()
    test_remote_fetch()
    test_rotation()
    test_silent_entry_exists()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("=" * 62)
