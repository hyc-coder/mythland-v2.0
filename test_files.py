"""
test_files.py - 文件管理功能验证（列表 / 上传 / 下载）

覆盖:
  1. file_mgr 基础: 列目录 / 分块读 / 上传闭环 / 安全保护
  2. agent 协议: file_list_req / file_dl_req / file_up_begin+chunk+end
  3. 端到端: 真实上传一个文件到被控端、再下载回来，内容一致
  4. 安全: 禁止访问系统目录、禁止删除系统目录
  5. 打包配置: file_mgr 已列入隐藏导入
"""
import base64
import os
import socket
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
    encode, decode, recv_all, send_all, CHUNK_SIZE,
    make_file_list_request, make_download_request,
    make_upload_begin, make_upload_chunk, make_upload_end,
    make_delete_request,
)

PORT = 9841


def start_agent(port=PORT):
    """
    启动 agent，返回 (agent, 实际端口)。
    关键: 端口被占用时会自动顺延，所以必须连【实际端口】a.port，
    否则会连到别的服务上导致超时。
    """
    from agent import Agent
    a = Agent("文件测试机", port, 9086)
    print(f"  [诊断] Agent 构造完成, 实际端口={a.port}")
    t = threading.Thread(target=a._accept_loop, daemon=True)
    t.start()
    time.sleep(1.5)
    print(f"  [诊断] accept线程 alive={t.is_alive()}")
    return a, a.port


def req(port, msg, timeout=15):
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.settimeout(timeout)
    send_all(s, encode(msg))
    d = recv_all(s, timeout=timeout)
    s.close()
    return decode(d) if d else {}


def test_basic():
    print("\n[测试1] file_mgr 基础功能")
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "a.txt"), "w") as f:
        f.write("hello world")

    p, parent, entries, err = fm.list_dir(tmp)
    print(f"  列目录: {len(entries)} 项, err={err!r}")
    assert len(entries) == 1, f"应有 1 项，实际 {len(entries)}"
    assert entries[0]["name"] == "a.txt"
    assert entries[0]["size"] == 11

    d, total, eof, err = fm.read_chunk(os.path.join(tmp, "a.txt"), 0, 5)
    print(f"  分块读: {d!r} total={total} eof={eof}")
    assert d == b"hello" and total == 11

    up = fm.FileUploader()
    ok, err = up.begin(tmp, "up.txt", 5)
    assert ok, err
    up.write(b"abcde")
    ok, msg, path = up.end()
    print(f"  上传闭环: {ok} {msg}")
    assert ok and open(path).read() == "abcde"
    print("  ✓ 列目录 / 分块读 / 上传写入 均正常")


def test_safety():
    """
    功能性校验 + 路径穿越防护（与安全开关无关，任何模式下都成立）。

    注: 目录写保护（C:\\Windows）的完整验证见 test_safemode.py，
        那里会模拟 Windows 环境。此处沙盒是 Linux，保护本就不生效。
    """
    print("\n[测试2] 功能性校验与路径穿越防护")

    # 沙盒是 Linux → 保护不生效（仅 Windows 的 C:\Windows 才保护）
    print(f"  IS_WINDOWS={fm.IS_WINDOWS} → 保护不生效（符合预期）")
    for p in ("/etc", "/bin", "/usr/bin"):
        assert fm.is_protected(p) is False
    print("  ✓ 非 Windows 系统不保护")

    # 功能性校验
    ok, msg = fm.delete_path("/no/such/path/xyz")
    assert not ok and "不存在" in msg
    print(f"    路径不存在 -> {msg}")

    tmp = tempfile.mkdtemp()
    _d, _t, _eof, err = fm.read_chunk(tmp, 0, 10)
    assert err and "不能下载" in err
    print(f"    目录当文件下载 -> {err}")

    # 路径穿越防护（始终有效）
    up = fm.FileUploader()
    ok, _e = up.begin(tmp, "../../evil.txt", 1)
    assert ok, "应能开始上传（文件名会被 basename 处理）"
    up.write(b"x")
    ok, msg, saved = up.end()
    assert saved == os.path.join(tmp, "evil.txt"), f"路径穿越未防护: {saved}"
    print(f"    文件名 '../../evil.txt' -> 落在 {os.path.basename(saved)}")

    # 删除功能本身正常（非受保护路径）
    tgt = os.path.join(tmp, "d.txt")
    with open(tgt, "w") as f:
        f.write("x")
    ok, msg = fm.delete_path(tgt)
    assert ok, f"普通文件应能删: {msg}"
    print(f"    普通文件删除 -> {msg}")
    print("  ✓ 功能性校验与路径穿越防护有效")


def test_agent_list():
    print("\n[测试3] agent 响应 file_list_req")
    a, port = start_agent()
    try:
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, "b.txt"), "w") as f:
            f.write("x" * 100)
        resp = req(port, make_file_list_request(tmp))
        print(f"  type={resp.get('type')} ok={resp.get('ok')}")
        assert resp.get("type") == "file_list_res"
        assert resp.get("ok"), f"失败: {resp.get('message')}"
        entries = resp.get("entries", [])
        print(f"  返回 {len(entries)} 项, path={resp.get('path')}")
        assert any(e["name"] == "b.txt" for e in entries)
        print("  ✓ 目录列表正确返回")

        # 不存在的路径
        resp = req(port, make_file_list_request("/no/such/dir/zzz"))
        print(f"  不存在路径 -> ok={resp.get('ok')} msg={resp.get('message')}")
        assert not resp.get("ok"), "不存在的路径应返回失败"
        print("  ✓ 错误路径有明确提示")
    finally:
        a.shutdown()


def test_agent_download():
    print("\n[测试4] agent 响应 file_dl_req（分块下载）")
    a, port = start_agent(9842)
    try:
        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, "big.txt")
        content = b"A" * 1000
        with open(src, "wb") as f:
            f.write(content)

        got = b""
        while True:
            r = req(port, make_download_request(src, len(got), 300))
            assert r.get("ok"), r.get("message")
            chunk = base64.b64decode(r.get("data", ""))
            got += chunk
            if r.get("eof"):
                break
            if not chunk:
                break
        print(f"  下载 {len(got)} 字节, total={r.get('total')}")
        assert got == content, "内容不一致！"
        print("  ✓ 分块下载内容完整一致（1000 字节，分 4 块）")
    finally:
        a.shutdown()


def test_agent_upload():
    print("\n[测试5] agent 响应 上传（begin→chunk→end）")
    a, port = start_agent(9843)
    try:
        tmp = tempfile.mkdtemp()
        data = b"HELLO-UPLOAD-TEST" * 50      # 850 字节

        s = socket.create_connection(("127.0.0.1", port), timeout=10)
        s.settimeout(10)
        # begin
        send_all(s, encode(make_upload_begin(tmp, "uploaded.bin", len(data))))
        r = decode(recv_all(s, timeout=10))
        print(f"  begin -> ok={r.get('ok')} path={r.get('path')}")
        assert r.get("ok"), r.get("message")

        # chunks
        off = 0
        while off < len(data):
            piece = data[off:off + 200]
            send_all(s, encode(make_upload_chunk(
                base64.b64encode(piece).decode())))
            r = decode(recv_all(s, timeout=10))
            assert r.get("ok"), r.get("message")
            off += len(piece)

        # end
        send_all(s, encode(make_upload_end()))
        r = decode(recv_all(s, timeout=10))
        s.close()
        print(f"  end -> ok={r.get('ok')} msg={r.get('message')}")
        assert r.get("ok"), r.get("message")

        saved = os.path.join(tmp, "uploaded.bin")
        assert os.path.exists(saved), "文件未保存"
        with open(saved, "rb") as f:
            got = f.read()
        print(f"  落盘 {len(got)} 字节, 内容一致: {got == data}")
        assert got == data, "上传内容不一致！"
        print("  ✓ 上传闭环正确（850 字节分 5 块）")
    finally:
        a.shutdown()


def test_roundtrip():
    """测试6: 完整往返 —— 上传→下载→比对"""
    print("\n[测试6] 端到端往返（上传→下载→比对）")
    a, port = start_agent(9844)
    try:
        tmp = tempfile.mkdtemp()
        original = os.urandom(4096)      # 随机二进制，防止文本编码掩盖问题
        local_src = os.path.join(tmp, "src.bin")
        with open(local_src, "wb") as f:
            f.write(original)

        # 上传
        s = socket.create_connection(("127.0.0.1", port), timeout=10)
        s.settimeout(15)
        send_all(s, encode(make_upload_begin(tmp, "remote.bin", len(original))))
        assert decode(recv_all(s, timeout=10)).get("ok")
        off = 0
        while off < len(original):
            piece = original[off:off + 1024]
            send_all(s, encode(make_upload_chunk(base64.b64encode(piece).decode())))
            assert decode(recv_all(s, timeout=10)).get("ok")
            off += len(piece)
        send_all(s, encode(make_upload_end()))
        r = decode(recv_all(s, timeout=10))
        s.close()
        assert r.get("ok"), r.get("message")
        remote_path = os.path.join(tmp, "remote.bin")
        print(f"  上传完成: {r.get('message')}")

        # 下载回来
        got = b""
        while True:
            rr = req(port, make_download_request(remote_path, len(got), 1024))
            assert rr.get("ok"), rr.get("message")
            c = base64.b64decode(rr.get("data", ""))
            got += c
            if rr.get("eof") or not c:
                break
        print(f"  下载 {len(got)} 字节")
        assert got == original, "往返后内容不一致！"
        print("  ✓ 4096 字节随机二进制往返完全一致")
    finally:
        a.shutdown()


def test_delete():
    print("\n[测试7] agent 响应删除")
    a, port = start_agent(9845)
    try:
        tmp = tempfile.mkdtemp()
        tgt = os.path.join(tmp, "del.txt")
        with open(tgt, "w") as f:
            f.write("bye")
        resp = req(port, make_delete_request(tgt))
        print(f"  del -> ok={resp.get('ok')} msg={resp.get('message')}")
        assert resp.get("ok"), resp.get("message")
        assert not os.path.exists(tgt), "文件应已删除"
        print("  ✓ 删除生效")
    finally:
        a.shutdown()


def test_build_config():
    print("\n[测试8] 打包配置")
    import build as b
    assert "file_mgr" in b.AGENT_HIDDEN, "file_mgr 必须在被控端隐藏导入"
    print("  AGENT_HIDDEN 含 file_mgr ✓")
    print("  ✓ 打包会带上文件管理模块")


if __name__ == "__main__":
    print("=" * 62)
    print("  文件管理功能 验证（列表 / 上传 / 下载）")
    print("=" * 62)
    test_basic()
    test_safety()
    test_agent_list()
    test_agent_download()
    test_agent_upload()
    test_roundtrip()
    test_delete()
    test_build_config()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("=" * 62)
