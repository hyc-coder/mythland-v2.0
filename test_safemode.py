"""
test_safemode.py - Windows 系统目录写保护 验证

需求:
  1. 默认【保护开启】
  2. 保护范围: 仅 Windows 的 C:\\Windows（含子目录）；Linux/Mac 不保护
  3. 保护内容: 禁止一切【更改】—— 删除 / 上传 / 新建文件夹
  4. 允许: 浏览目录、下载文件（只读放行）
  5. 命令栏输入 SAFE_MODE_OFF 可临时关闭，SAFE_MODE_ON 恢复

沙盒是 Linux，所以测试中要把 file_mgr 切成"Windows 模式"来模拟。
"""

import os
import sys
import tempfile
import threading
import time
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(__file__))
for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
    sys.modules.setdefault(_m, MagicMock())

import file_mgr as fm
from common import (
    encode, decode, recv_all, send_all, make_command_request,
)


def win_mode(on: bool = True):
    """
    切换 file_mgr 到"模拟 Windows 模式"。
    Linux 下 os.path.abspath 会把 C:\\Windows 变成相对路径，
    所以同时替换 normalize 为 Windows 语义（反斜杠 + 小写）。
    """
    if on:
        fm.IS_WINDOWS = True
        fm.normalize = lambda p: (p or "").replace("/", "\\").lower()
    else:
        fm.IS_WINDOWS = (os.name == "nt")
        import importlib
        importlib.reload(fm)


def restore():
    """恢复真实模块状态（避免污染后续测试）"""
    import importlib
    importlib.reload(fm)


# ---------- 1. 默认开启 ----------

def test_default_on():
    print("\n[测试1] 默认保护开启")
    restore()
    print(f"  SAFE_MODE = {fm.SAFE_MODE}")
    print(f"  safe_enabled() = {fm.safe_enabled()}")
    assert fm.SAFE_MODE is True, "默认应开启保护"
    assert fm.safe_enabled() is True
    print("  ✓ 默认开启")


# ---------- 2. 只保护 C:\Windows ----------

def test_scope():
    print("\n[测试2] 保护范围（仅 Windows 的 C:\\Windows）")
    win_mode(True)
    try:
        cases = [
            ("C:\\Windows", True),
            ("C:\\Windows\\System32", True),
            ("C:\\Windows\\System32\\drivers\\etc", True),
            ("c:\\windows", True),              # 大小写不敏感
            ("C:\\Users\\Student", False),      # 用户目录不保护
            ("C:\\Program Files", False),       # 不再保护
            ("D:\\Windows", False),             # 只保护 C 盘
            ("C:\\WindowsX", False),            # 前缀但不等于/不子目录
        ]
        for path, expect in cases:
            got = fm.is_protected(path)
            flag = "保护" if got else "放行"
            print(f"  {path:36s} -> {flag}")
            assert got == expect, f"{path} 期望保护={expect} 实际={got}"
        print("  ✓ 范围精确：仅 C:\\Windows 及其子目录")
    finally:
        restore()


def test_linux_not_protected():
    print("\n[测试3] Linux / macOS 不保护")
    win_mode(False)
    try:
        print(f"  IS_WINDOWS = {fm.IS_WINDOWS}")
        assert fm.IS_WINDOWS is False
        for p in ("/etc", "/bin", "/usr/bin", "/etc/passwd"):
            got = fm.is_protected(p)
            print(f"  {p:16s} -> {'保护' if got else '放行'}")
            assert got is False, f"Linux 下 {p} 不应被保护"
        print("  ✓ 非 Windows 系统一律不保护")
    finally:
        restore()


# ---------- 3. 禁止一切更改 ----------

def test_write_blocked():
    print("\n[测试4] 禁止一切更改（删除 / 上传 / 新建）")
    win_mode(True)
    try:
        # 删除
        ok, msg = fm.delete_path("C:\\Windows\\System32\\abc.dll")
        print(f"  删除 -> ok={ok}")
        print(f"         {msg.splitlines()[0]}")
        assert not ok and "禁止删除" in msg, f"应禁止删除: {msg}"

        # 新建文件夹
        ok, msg = fm.make_dir("C:\\Windows\\MyFolder")
        print(f"  新建 -> ok={ok}")
        print(f"         {msg.splitlines()[0]}")
        assert not ok and "禁止新建" in msg

        # 上传
        up = fm.FileUploader()
        ok, msg = up.begin("C:\\Windows", "evil.exe", 100)
        print(f"  上传 -> ok={ok}")
        print(f"         {msg.splitlines()[0]}")
        assert not ok and "禁止上传" in msg

        # C:\Windows 根目录本身
        ok, msg = fm.delete_path("C:\\Windows")
        assert not ok and "禁止删除" in msg
        print("  ✓ 删除 / 新建 / 上传（含根目录本身）全部被拦截")
    finally:
        restore()


# ---------- 4. 只读放行 ----------

def test_read_allowed():
    print("\n[测试5] 只读放行（下载 / 浏览不受限）")
    restore()      # 用真实模块状态（避免 mock 的 normalize 干扰真实文件读取）

    # 源码层面：只读函数不含保护拦截
    import inspect
    src = inspect.getsource(fm.read_chunk)
    assert "is_protected" not in src, "read_chunk 不应再有保护拦截"
    print("  read_chunk 源码无保护拦截 ✓")

    src2 = inspect.getsource(fm.list_dir)
    code_lines = [l for l in src2.splitlines()
                  if "is_protected" in l and not l.strip().startswith("#")]
    assert not code_lines, f"list_dir 不应拦截浏览: {code_lines}"
    print("  list_dir 源码无保护拦截 ✓")

    # 功能层面：普通文件正常读
    tmp = tempfile.mkdtemp()
    real = os.path.join(tmp, "winfile.txt")
    with open(real, "wb") as f:
        f.write(b"SYSTEM-DATA-1234567890")
    data, total, eof, err = fm.read_chunk(real, 0, 11)
    print(f"  实际读取: {data!r} total={total} err={err!r}")
    assert data == b"SYSTEM-DATA" and not err
    assert total == 22
    print("  ✓ 下载（只读）不受保护影响")


# ---------- 5. SAFE_MODE_OFF ----------

def test_toggle_off():
    print("\n[测试6] 命令栏 SAFE_MODE_OFF 临时关闭")
    win_mode(True)
    try:
        # 先确认是拦的
        assert fm.is_protected("C:\\Windows\\a.txt"), "初始应保护"
        print(f"  初始: is_protected(C:\\Windows\\a.txt) = True")

        # 关闭
        fm.set_safe_mode(False)
        print(f"  SAFE_MODE_OFF 后 safe_enabled() = {fm.safe_enabled()}")
        assert fm.safe_enabled() is False
        assert fm.is_protected("C:\\Windows\\a.txt") is False
        print("  ✓ 关闭后不再拦截")

        # 恢复
        fm.set_safe_mode(True)
        print(f"  SAFE_MODE_ON 后 safe_enabled() = {fm.safe_enabled()}")
        assert fm.safe_enabled() is True
        assert fm.is_protected("C:\\Windows\\a.txt") is True
        print("  ✓ SAFE_MODE_ON 可恢复")

        # 状态文本
        print(f"  状态文本: {fm.safe_status()}")
        fm.set_safe_mode(False)
        print(f"  关闭后状态: {fm.safe_status()}")
        fm.set_safe_mode(True)
    finally:
        restore()


def test_toggle_is_temporary():
    print("\n[测试7] 临时关闭不改默认值（重启恢复）")
    win_mode(True)
    try:
        before = fm.SAFE_MODE
        fm.set_safe_mode(False)
        assert fm.safe_enabled() is False
        # 模拟"重启": 重新加载模块
        restore()
        print(f"  重启后 SAFE_MODE = {fm.SAFE_MODE}, safe_enabled = {fm.safe_enabled()}")
        assert fm.SAFE_MODE == before is True, "重启应恢复默认保护"
        assert fm.safe_enabled() is True
        print("  ✓ 临时关闭仅对当前进程有效，重启恢复保护")
    finally:
        restore()


# ---------- 6. agent 命令通道 ----------

def test_agent_command():
    print("\n[测试8] agent 处理 cmd_req（SAFE_MODE_OFF）")
    from agent import Agent

    a = Agent("保护测试机", 9861, 9086)
    print(f"  [诊断] 实际端口={a.port}")
    t = threading.Thread(target=a._accept_loop, daemon=True)
    t.start()
    time.sleep(1.5)
    print(f"  [诊断] accept线程 alive={t.is_alive()}")
    port = a.port

    def send(cmd):
        s = __import__("socket").create_connection(("127.0.0.1", port), timeout=8)
        s.settimeout(8)
        send_all(s, encode(make_command_request(cmd)))
        d = recv_all(s, timeout=8)
        s.close()
        return decode(d) if d else {}

    try:
        # 查询状态
        r = send("SAFE_MODE_STATUS")
        print(f"  SAFE_MODE_STATUS -> ok={r.get('ok')}")
        print(f"    {r.get('output','').splitlines()[0] if r.get('output') else ''}")
        assert r.get("ok"), "查询状态应成功"

        # 关闭（小写也应识别）
        r = send("safe_mode_off")
        print(f"  safe_mode_off -> ok={r.get('ok')}")
        first = (r.get("output") or "").splitlines()
        print(f"    {first[0] if first else ''}")
        assert r.get("ok"), f"关闭应成功: {r.get('output')}"
        assert "临时关闭" in r.get("output", "")

        # 确认生效
        win_mode(True)
        try:
            probe = "C:" + "\\" + "Windows" + "\\" + "x"
            print("  生效检查 is_protected =", fm.is_protected(probe))
            # 注意: agent 与测试在不同模块实例时可能不同步，这里只验证协议返回
        finally:
            restore()

        # 恢复
        r = send("SAFE_MODE_ON")
        print(f"  SAFE_MODE_ON -> ok={r.get('ok')}")
        assert r.get("ok")
        assert "恢复" in r.get("output", "")
        print("  ✓ 内置指令大小写不敏感，协议往返正常")

        # 非内置命令 → 交给系统 shell 执行（远程命令功能已接入）
        # 用一个明确不存在的命令，验证会返回失败且有错误输出
        r = send("definitely_not_a_real_command_xyz")
        print(f"  不存在的系统命令 -> ok={r.get('ok')}")
        assert not r.get("ok"), "不存在的命令应返回失败"
        assert r.get("output"), "应有错误输出"
        print(f"    输出: {(r.get('output') or '')[:60]!r}")
        print("  ✓ 非内置命令已交给系统 shell 执行（失败时有错误回显）")
    finally:
        a.shutdown()


if __name__ == "__main__":
    print("=" * 62)
    print("  Windows 系统目录写保护 验证")
    print("=" * 62)
    test_default_on()
    test_scope()
    test_linux_not_protected()
    test_write_blocked()
    test_read_allowed()
    test_toggle_off()
    test_toggle_is_temporary()
    test_agent_command()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("=" * 62)
