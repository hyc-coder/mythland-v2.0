"""
test_deploy.py - 一键部署 验证

jcc.exe 是 Windows 程序，沙盒跑不了真的。
因此用一个【模拟 jcc 脚本】替代，验证:
  1. IP 解析: 单个 / 范围简写 / 范围全写 / 混合 / 非法输入
  2. HTTP 服务: 起得来、能下载到原文件、其它路径 404
  3. jcc 调用: 参数拼装正确（-ip / -c）、命令含正确 URL 与远程路径
  4. 部署流程: 成功路径(3 步) / 失败路径(中途失败即停)
  5. 并发: 多台同时部署
  6. 取消: cancel() 后不再继续
  7. 文件探测: find_jcc / find_agent_exe
  8. UI: 主控端有「一键部署」按钮 + DeployDialog 类存在
  9. 打包配置含 deploy / deploy_ui / http.server
"""

import os
import socket
import stat
import sys
import tempfile
import time
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(__file__))
for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.filedialog"):
    sys.modules.setdefault(_m, MagicMock())

from deploy import (
    Deployer, DeployResult, parse_ip_spec, summarize,
    DEFAULT_REMOTE_DIR,
)

TMP = tempfile.mkdtemp(prefix="deploytest_")


def make_mock_jcc(fail_ips=()):
    """造一个模拟 jcc 脚本（Linux 下可执行的 shell 脚本）"""
    path = os.path.join(TMP, "jcc")
    fail_list = " ".join(f'"{x}"' for x in fail_ips)
    script = f"""#!/bin/bash
IP=""; CMD=""
while [ $# -gt 0 ]; do
  case "$1" in
    -ip) IP="$2"; shift 2;;
    -c)  CMD="$2"; shift 2;;
    *)   shift;;
  esac
done
echo "$IP\\t$CMD" >> "{TMP}/jcc_calls.log"
for f in {fail_list}; do
  if [ "$IP" = "$f" ]; then
    echo "ERROR: host unreachable" >&2
    exit 1
  fi
done
echo "OK ip=$IP"
exit 0
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def make_fake_exe(name="agent.exe", size=4096):
    path = os.path.join(TMP, name)
    with open(path, "wb") as f:
        f.write(os.urandom(size))
    return path


def raw_http_get(port, path="/agent.exe"):
    """裸 socket 发 HTTP GET（绕开沙盒代理，代理会拦 urllib）"""
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(f"GET {path} HTTP/1.0\r\nHost: x\r\n\r\n".encode())
    buf = b""
    while True:
        c = s.recv(65536)
        if not c:
            break
        buf += c
    head, _, body = buf.partition(b"\r\n\r\n")
    code = head.split()[1].decode() if len(head.split()) > 1 else "?"
    return code, body


# ---------------- 1. IP 解析 ----------------

def test_ip_parse():
    print("\n[测试1] IP 解析")
    cases = [
        ("192.168.80.12", 1),
        ("192.168.80.10-56", 47),
        ("192.168.80.10-192.168.80.56", 47),
        ("192.168.80.12, 192.168.80.20-22", 4),
        ("192.168.1.5;192.168.1.7", 2),
        ("192.168.80.10-56\n192.168.80.100", 48),
        ("192.168.80.20-10", 11),          # 倒序自动交换
    ]
    for spec, expect in cases:
        ips, errs = parse_ip_spec(spec)
        print(f"  {spec!r:36s} -> {len(ips):3d} 个" + (f"  错误{errs}" if errs else ""))
        assert len(ips) == expect, f"{spec!r} 期望 {expect} 个，实际 {len(ips)}"
        assert not errs, f"{spec!r} 不该有错误: {errs}"

    # 非法输入应当报错而不是静默通过
    for bad in ("999.1.1.1", "abc", "192.168.80.300", "192.168.80.1-"):
        ips, errs = parse_ip_spec(bad)
        print(f"  非法 {bad!r:20s} -> ip={len(ips)} 错误={len(errs)}")
        assert len(ips) == 0 and errs, f"{bad!r} 应报错"

    # 空输入
    assert parse_ip_spec("") == ([], [])
    print("  ✓ 单IP/范围/混合/非法 全部正确")


# ---------------- 2. HTTP 服务 ----------------

def test_http_server():
    print("\n[测试2] 临时 HTTP 服务")
    exe = make_fake_exe()
    d = Deployer(exe_path=exe, jcc_path=make_mock_jcc())
    url = d.start_http()
    print(f"  URL: {url}")
    assert "/agent.exe" in url

    code, body = raw_http_get(d.http_port, "/agent.exe")
    print(f"  GET /agent.exe -> {code}, {len(body)} bytes")
    assert code == "200"
    assert body == open(exe, "rb").read(), "下载内容应与原文件一致"

    # 其它路径应 404（只暴露这一个文件）
    code2, body2 = raw_http_get(d.http_port, "/secret.txt")
    print(f"  GET /secret.txt -> {code2}（应为 404）")
    assert code2 == "404"

    d.stop_http()
    print("  ✓ 只提供指定文件，其它路径 404")


# ---------------- 3. jcc 参数拼装 ----------------

def test_jcc_args():
    print("\n[测试3] jcc 调用参数")
    log = os.path.join(TMP, "jcc_calls.log")
    if os.path.exists(log):
        os.remove(log)

    exe = make_fake_exe()
    jcc = make_mock_jcc()
    d = Deployer(exe_path=exe, jcc_path=jcc,
                 remote_dir=r"C:\ProgramData\RemoteAgent",
                 auto_start=True)
    d.start_http()

    ok, out = d.run_jcc("192.168.80.12", 'echo HELLO')
    print(f"  单条执行 -> ok={ok} out={out.strip()[:40]}")
    assert ok, "模拟 jcc 应成功"

    with open(log, encoding="utf-8") as f:
        line = f.readline().strip()
    print(f"  日志记录: {line[:70]}")
    assert line.startswith("192.168.80.12"), "日志应记录 -ip 参数"

    # 步骤命令：应含 URL 与远程路径
    steps = d.build_steps()
    print("  步骤命令:")
    for stage, cmd in steps:
        print(f"    [{stage}] {cmd}")
    joined = " ".join(c for _, c in steps)
    assert d.http_url in joined, "命令应含主控端 HTTP 地址"
    assert r"C:\ProgramData\RemoteAgent\agent.exe" in joined, "应含远程路径"
    assert any("certutil" in c for _, c in steps), "应有下载命令"
    assert any("start" in c for _, c in steps), "应有启动命令"

    d.stop_http()
    print("  ✓ -ip/-c 参数正确，命令含 URL 与远程路径")


# ---------------- 4. 部署流程 ----------------

def test_deploy_flow():
    print("\n[测试4] 部署流程（成功 + 失败）")
    exe = make_fake_exe()
    jcc = make_mock_jcc(fail_ips=["192.168.80.66"])
    d = Deployer(exe_path=exe, jcc_path=jcc,
                 remote_dir=r"C:\ProgramData\RA",
                 timeout=20, workers=3)
    d.start_http()

    ips, _ = parse_ip_spec("192.168.80.10-12, 192.168.80.66")
    print(f"  目标: {ips}")
    results = d.deploy_all(ips)
    d.stop_http()

    ok_ips = [r.ip for r in results if r.ok]
    fail_ips = [r.ip for r in results if not r.ok]
    print(f"  成功: {ok_ips}")
    print(f"  失败: {fail_ips}")
    assert len(ok_ips) == 3, "3 台应成功"
    assert fail_ips == ["192.168.80.66"], "只有 .66 应失败"

    # 成功的是 3 步都走完
    for r in results:
        if r.ok:
            stages = [s for s, _, _ in r.steps]
            print(f"    {r.ip}: {' → '.join(stages)}")
            assert stages == ["建目录", "下载", "启动"], "应完成 3 步"

    # 失败的应【中途即停】，不继续后续步骤
    bad = [r for r in results if not r.ok][0]
    print(f"  {bad.ip} 停在: {bad.stage}，只执行了 {len(bad.steps)} 步")
    assert len(bad.steps) == 1, "失败后应立刻停止，不再执行后续步骤"

    print("  ✓ 成功走完 3 步，失败中途即停")


def test_no_autostart():
    print("\n[测试5] 不勾选「部署后启动」")
    exe = make_fake_exe()
    d = Deployer(exe_path=exe, jcc_path=make_mock_jcc(),
                 auto_start=False, timeout=15)
    steps = d.build_steps()
    names = [s for s, _ in steps]
    print(f"  步骤: {names}")
    assert "启动" not in names, "auto_start=False 时不应有启动步骤"
    assert len(names) == 2, "应只有建目录 + 下载"
    print("  ✓ 步骤随选项变化")


# ---------------- 6. 并发 ----------------

def test_concurrent():
    print("\n[测试6] 并发部署")
    exe = make_fake_exe()
    d = Deployer(exe_path=exe, jcc_path=make_mock_jcc(),
                 timeout=20, workers=6)
    d.start_http()
    ips, _ = parse_ip_spec("192.168.80.20-31")   # 12 台
    t0 = time.time()
    results = d.deploy_all(ips)
    cost = time.time() - t0
    d.stop_http()
    ok = sum(1 for r in results if r.ok)
    print(f"  {len(ips)} 台，成功 {ok}，耗时 {cost:.2f}s（并发 6）")
    assert ok == len(ips), "应全部成功"
    # 12 台 × 3 步，若串行会明显更久
    print("  ✓ 并发执行，全部成功")


# ---------------- 7. 取消 ----------------

def test_cancel():
    """
    模拟真实场景: 部署【进行中】点停止。
    预期: 已开始的这台会跑完（不半途而废），后续未开始的标记为「取消」。
    """
    print("\n[测试7] 部署中途取消")
    exe = make_fake_exe()
    d = Deployer(exe_path=exe, jcc_path=make_mock_jcc(),
                 timeout=20, workers=1)      # 并发 1，保证顺序执行
    d.start_http()

    ips, _ = parse_ip_spec("192.168.80.40-49")   # 10 台
    done = {"n": 0}

    def on_progress(r):
        done["n"] += 1
        if done["n"] == 2:          # 第 2 台完成后点「停止」
            print(f"  → 第 {done['n']} 台完成，触发 cancel()")
            d.cancel()

    results = d.deploy_all(ips, on_progress=on_progress)
    d.stop_http()

    stages = [r.stage for r in results]
    n_ok = sum(1 for r in results if r.ok)
    n_cancel = sum(1 for r in results if r.stage == "取消")
    print(f"  完成 {n_ok} 台，取消 {n_cancel} 台，共 {len(results)} 台")
    print(f"  各台状态: {stages}")

    assert n_cancel > 0, "取消后应有机器被标记为取消"
    assert n_ok < len(ips), "不应全部完成（取消生效了）"
    # 已开始的会跑完 → 前两台应是成功的
    assert results[0].ok and results[1].ok, "已开始的这台应跑完，不半途而废"
    print("  ✓ 已开始的跑完，后续被取消")


# ---------------- 8. 异常处理 ----------------

def test_missing_files():
    print("\n[测试8] 缺文件时的报错")
    exe = make_fake_exe()

    # jcc 不存在
    d = Deployer(exe_path=exe, jcc_path=os.path.join(TMP, "no_such_jcc"))
    ok, out = d.run_jcc("192.168.80.1", "echo x")
    print(f"  jcc 不存在 -> ok={ok} out={out[:50]}")
    assert not ok and "找不到" in out

    # exe 不存在 → start_http 抛异常
    d2 = Deployer(exe_path=os.path.join(TMP, "no_such_exe"),
                  jcc_path=make_mock_jcc())
    try:
        d2.start_http()
        raise AssertionError("应抛 FileNotFoundError")
    except FileNotFoundError as e:
        print(f"  exe 不存在 -> {e}")

    print("  ✓ 缺文件时有明确提示，不静默失败")


def test_find_files():
    print("\n[测试9] 文件探测")
    exe = make_fake_exe("agent.exe")
    jcc = make_mock_jcc()
    found_exe = Deployer.find_agent_exe(exe)
    found_jcc = Deployer.find_jcc(jcc)
    print(f"  find_agent_exe -> {found_exe}")
    print(f"  find_jcc       -> {found_jcc}")
    assert found_exe and os.path.isfile(found_exe)
    assert found_jcc and os.path.isfile(found_jcc)
    print("  ✓ 能在同目录找到 agent.exe 与 jcc")


def test_summarize():
    print("\n[测试10] 结果汇总")
    rs = [DeployResult("1.1.1.1"), DeployResult("1.1.1.2"),
          DeployResult("1.1.1.3")]
    rs[0].ok = True
    rs[1].ok = True
    rs[2].stage, rs[2].detail = "失败", "下载失败: timeout"
    s = summarize(rs)
    print("  " + s.replace("\n", "\n  "))
    assert "成功 2" in s and "失败 1" in s
    assert "1.1.1.3" in s
    print("  ✓ 汇总文案正确")


# ---------------- 9. UI 与打包 ----------------

def test_ui_and_build():
    print("\n[测试11] UI 与打包配置")
    path = os.path.join(os.path.dirname(__file__), "controller.py")
    src = open(path, encoding="utf-8").read()
    assert "一键部署" in src, "工具栏应有一键部署按钮"
    assert "def open_deploy" in src, "缺 open_deploy"
    print("  controller.py: 按钮 + open_deploy ✓")

    import deploy_ui
    assert hasattr(deploy_ui, "DeployDialog"), "缺 DeployDialog"
    assert hasattr(deploy_ui, "open_deploy_dialog"), "缺 open_deploy_dialog"
    print("  deploy_ui.py: DeployDialog + open_deploy_dialog ✓")

    import build as b
    for mod in ("deploy", "deploy_ui", "http.server"):
        assert mod in b.CONTROLLER_HIDDEN or mod in b.AGENT_HIDDEN, \
            f"{mod} 应在打包隐藏导入里"
    print("  打包配置含 deploy / deploy_ui / http.server ✓")
    print("  ✓ UI 与打包就绪")


if __name__ == "__main__":
    print("=" * 62)
    print("  一键部署 验证（用模拟 jcc.exe）")
    print("=" * 62)
    test_ip_parse()
    test_http_server()
    test_jcc_args()
    test_deploy_flow()
    test_no_autostart()
    test_concurrent()
    test_cancel()
    test_missing_files()
    test_find_files()
    test_summarize()
    test_ui_and_build()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("  （真实部署需在 Windows 上配合真正的 jcc.exe 验证）")
    print("=" * 62)
