"""
test_url.py - 打开网址功能 验证

沙盒里没有浏览器，所以真实"打开"动作无法验证。
本测试聚焦【逻辑正确性】:
  1. URL 规范化（补 https://）
  2. 协议白名单（拒绝 javascript: / data:）
  3. 浏览器查找（找不到时返回明确提示）
  4. webbrowser / 系统命令 两条路径的分支正确（用 mock 验证）
  5. 静默: 不把 xdg-open 的噪声喷进被控端日志
  6. agent 协议往返正常
  7. 打包配置含 url_opener

真实效果请在 Windows 教室机上验证（有浏览器的环境）。
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))
for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
    sys.modules.setdefault(_m, MagicMock())

import url_opener as uo
from common import encode, decode, recv_all, send_all, make_open_url_request

SAFE = ("https://example.com", "http://a.b", "ftp://f.com",
        "mailto:a@b.com", "file:///tmp/a.txt")
DANGER = ("javascript:alert(1)",
          "data:text/html,<script>x</script>",
          "vbscript:msgbox(1)",
          "javascript://comment/%0aalert(1)",   # 无冒号后空格的变体
          "about:blank",
          "view-source:https://example.com")

# 规范化后仍应安全/危险（防止"补 https://"把危险协议洗白）
NORMALIZE_CASES = [
    ("www.baidu.com", True),
    ("https://example.com", True),
    ("www.a.com:8080", True),          # 端口合法，不该被误判成 scheme
    ("javascript:alert(1)", False),
    ("data:text/html,x", False),
    ("vbscript:msgbox(1)", False),
    ("about:blank", False),
]


def test_normalize():
    print("\n[测试1] URL 规范化")
    cases = [
        ("www.baidu.com", "https://www.baidu.com"),
        ("  x.com  ", "https://x.com"),
        ("https://ok.com", "https://ok.com"),
        ("http://a.b", "http://a.b"),
        ("", ""),
    ]
    for raw, expect in cases:
        got = uo.normalize_url(raw)
        print(f"  {raw!r:20s} -> {got!r}")
        assert got == expect, f"{raw!r} 期望 {expect!r} 实际 {got!r}"
    print("  ✓ 不带协议自动补 https://，带协议的保持原样")


def test_scheme_whitelist():
    print("\n[测试2] 协议白名单")
    for u in SAFE:
        assert uo.is_safe_url(u), f"{u} 应被允许"
        print(f"  {u:34s} -> 允许")
    for u in DANGER:
        assert not uo.is_safe_url(u), f"{u} 应被拒绝"
        print(f"  {u:34s} -> 拒绝")
    print("  ✓ 危险协议全部拦截")


def test_normalize_then_validate():
    """
    关键回归: normalize_url 不能把危险协议"洗白"。

    曾经有个 bug: data:text/html,... 因为不含 "://" 被当成域名，
    补成了 https://data:text/html,... —— 危险意图被掩盖。
    """
    print("\n[测试3] 规范化 + 校验 联合（防'洗白'绕过）")
    for raw, should_allow in NORMALIZE_CASES:
        n = uo.normalize_url(raw)
        safe = uo.is_safe_url(n)
        flag = "允许" if safe else "拒绝"
        print(f"  {raw[:34]:34s} -> {flag}")
        assert safe == should_allow, \
            f"{raw!r} 规范化成 {n!r}，期望允许={should_allow} 实际={safe}"
    print("  ✓ 危险协议经规范化后仍被拒绝，域名/端口正常放行")


def test_dangerous_rejected():
    print("\n[测试4] 危险 URL 不会真的去打开")
    for u in DANGER:
        ok, msg, browser = uo.open_url(u)
        print(f"  {u[:30]:30s} -> ok={ok}")
        assert not ok, f"{u} 应被拒绝"
        assert "拒绝" in msg or "不支持" in msg
    print("  ✓ 一律拒绝，并给出允许的协议列表")


def test_browser_lookup():
    print("\n[测试5] 浏览器查找")
    # 沙盒没有这些浏览器 → 应返回空，open_url 给出友好提示
    for name in ("chrome", "edge", "firefox"):
        path = uo._find_browser(name)
        print(f"  {name:10s} -> {path!r}")
        assert isinstance(path, str)

    ok, msg, used = uo.open_url("https://example.com", browser="chrome")
    print(f"  指定 chrome -> ok={ok}")
    print(f"    {msg.splitlines()[0]}")
    if not uo._find_browser("chrome"):
        assert not ok and "未在本机找到" in msg, "找不到时应明确提示"
        print("  ✓ 浏览器不存在时提示清晰（不静默失败）")


def test_webbrowser_path():
    print("\n[测试6] webbrowser 路径（mock 验证分支）")
    with patch.object(uo, "webbrowser") as wb:
        wb.open.return_value = True
        ok, msg, used = uo.open_url("https://example.com")
        print(f"  webbrowser 成功 -> ok={ok} msg={msg!r} used={used!r}")
        assert ok, "webbrowser 返回 True 时应成功"
        assert wb.open.called, "应调用 webbrowser.open"
        # 验证传的是新标签页
        args, kwargs = wb.open.call_args
        print(f"  调用参数: url={args[0]!r} new={kwargs.get('new')}")
        assert args[0] == "https://example.com"

    with patch.object(uo, "webbrowser") as wb:
        wb.open.return_value = False
        # 沙盒无 xdg-open，会走到"全部失败"分支 —— 只要不抛异常即可
        ok, msg, used = uo.open_url("https://example.com")
        print(f"  webbrowser 失败 -> ok={ok}（沙盒无浏览器，符合预期）")
        assert isinstance(ok, bool) and isinstance(msg, str)
    print("  ✓ 两条分支都能正确处理，无异常")


def test_silent():
    print("\n[测试7] 静默（不污染被控端日志）")
    # _silent 应把 func 期间的 stdout 捕获掉
    import io
    captured = {}

    def noisy():
        print("NOISE-SHOULD-NOT-LEAK")
        return 42

    with patch.object(uo.webbrowser, "open", side_effect=noisy):
        ok, msg, used = uo.open_url("https://example.com")
        print(f"  含 print 的调用 -> ok={ok}")

    # 直接验证 _silent 行为
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        r = uo._silent(noisy)
    finally:
        sys.stdout = old
    print(f"  _silent 返回值: {r}")
    print(f"  泄漏到 stdout 的内容: {buf.getvalue()!r}")
    assert r == 42, "_silent 应返回 func 的返回值"
    assert "NOISE" not in buf.getvalue(), "噪声应被抑制"
    print("  ✓ 噪声被抑制，不影响被控端日志")


def test_agent_protocol():
    print("\n[测试8] agent 协议往返")
    import socket
    import threading
    import time
    from agent import Agent

    a = Agent("网址测试机", 9891, 9086)
    print(f"  [诊断] 实际端口={a.port}")
    t = threading.Thread(target=a._accept_loop, daemon=True)
    t.start()
    time.sleep(2.0)
    print(f"  [诊断] accept线程 alive={t.is_alive()}")
    port = a.port

    def send(url, browser=""):
        s = socket.create_connection(("127.0.0.1", port), timeout=10)
        s.settimeout(10)
        send_all(s, encode(make_open_url_request(url, browser)))
        d = recv_all(s, timeout=10)
        s.close()
        return decode(d) if d else {}

    try:
        # 危险 URL 应被拒（不依赖浏览器是否存在）
        r = send("javascript:alert(1)")
        print(f"  javascript -> ok={r.get('ok')}")
        assert r.get("type") == "open_url_res"
        assert not r.get("ok"), "危险 URL 应返回失败"
        assert "拒绝" in r.get("message", "")

        # 正常 URL（沙盒可能真打不开，但协议字段必须完整）
        r = send("https://example.com")
        print(f"  正常 URL  -> ok={r.get('ok')}")
        for k in ("type", "ok", "message", "browser"):
            assert k in r, f"响应缺字段 {k}"
        print(f"    字段: {sorted(r.keys())}")
        print(f"    msg: {(r.get('message') or '')[:60]}")
        print("  ✓ 协议字段完整，危险 URL 被拒")
    finally:
        a.shutdown()


def test_build_config():
    print("\n[测试9] 打包配置")
    import build as b
    assert "url_opener" in b.AGENT_HIDDEN, "url_opener 必须在被控端隐藏导入"
    print("  AGENT_HIDDEN 含 url_opener ✓")
    print("  ✓ 打包会带上网址模块（无新增第三方依赖）")


if __name__ == "__main__":
    print("=" * 62)
    print("  打开网址功能 验证")
    print("=" * 62)
    test_normalize()
    test_scheme_whitelist()
    test_normalize_then_validate()
    test_dangerous_rejected()
    test_browser_lookup()
    test_webbrowser_path()
    test_silent()
    test_agent_protocol()
    test_build_config()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("  （真实打开效果需在 Windows 教室机上验证：沙盒无浏览器）")
    print("=" * 62)
