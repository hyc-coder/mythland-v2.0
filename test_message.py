"""
test_message.py - 发送消息 / 发送命令 验证

覆盖:
  1. 协议构造: 字段与级别校验（level 非法值回落 info）
  2. agent 响应 msg_send_req / runcmd_req
  3. 发送命令能真执行（echo / 多行 / 超时）
  4. 「执行完弹窗」选项被正确传递与回传 notified 字段
  5. notifier 在【无 tkinter 环境】下安全降级（不崩、返回 False）
  6. 界面: 不再有占位 _todo，两个按钮有真实实现
  7. act_upload_file 只有一份（曾因重复定义被占位版覆盖）
  8. 打包配置含 notifier

弹窗动画本身需要真实显示环境，沙盒无法验证；
这里重点保证【逻辑正确 + 无环境时安全降级】。
"""

import inspect
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
    make_message_request, make_runcmd_request,
    CMD_TIMEOUT, CMD_MAX_TIMEOUT,
)


def start_agent(port=9901):
    from agent import Agent
    a = Agent("消息测试机", port, 9086)
    print(f"  [诊断] 实际端口={a.port}")
    t = threading.Thread(target=a._accept_loop, daemon=True)
    t.start()
    time.sleep(1.8)
    print(f"  [诊断] accept线程 alive={t.is_alive()}")
    return a, a.port


# ---------- 1. 协议构造 ----------

def test_protocol_build():
    print("\n[测试1] 协议构造")
    m = make_message_request("标题", "内容", sender="控制端",
                             timeout=5, level="warn")
    print(f"  msg: type={m['type']} level={m['level']} timeout={m['timeout']}")
    assert m["type"] == "msg_send_req"
    assert m["level"] == "warn" and m["timeout"] == 5.0
    assert m["sender"] == "控制端"

    # 非法 level 回落 info
    m2 = make_message_request("t", "x", level="evil")
    print(f"  非法 level 'evil' -> {m2['level']}")
    assert m2["level"] == "info", "非法级别应回落 info"

    r = make_runcmd_request("echo hi", timeout=15, notify=True, title="T")
    print(f"  runcmd: timeout={r['timeout']} notify={r['notify']} title={r['title']}")
    assert r["type"] == "runcmd_req" and r["notify"] is True
    print("  ✓ 字段正确，非法值有回落")


# ---------- 2. agent 响应 ----------

def test_agent_message():
    print("\n[测试2] agent 响应 msg_send_req")
    a, port = start_agent(9902)

    def send(req, timeout=10):
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.settimeout(timeout)
        send_all(s, encode(req))
        d = recv_all(s, timeout=timeout)
        s.close()
        return decode(d) if d else {}

    try:
        # 沙盒无 tkinter → shown=False，但必须有 ok/message/shown 字段且不崩
        r = send(make_message_request("课堂提醒", "请注意纪律",
                                      sender="教师机", timeout=8))
        print(f"  -> type={r.get('type')} ok={r.get('ok')} shown={r.get('shown')}")
        print(f"     message={r.get('message')!r}")
        for k in ("type", "ok", "message", "shown"):
            assert k in r, f"响应缺字段 {k}"
        assert r.get("type") == "msg_send_res"
        print("  ✓ 字段完整，无显示环境时安全降级（未崩溃）")
    finally:
        a.shutdown()


# ---------- 3. 发送命令真执行 ----------

def test_agent_runcmd():
    print("\n[测试3] agent 响应 runcmd_req（真执行）")
    a, port = start_agent(9903)

    def send(req, timeout=20):
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.settimeout(timeout)
        send_all(s, encode(req))
        d = recv_all(s, timeout=timeout)
        s.close()
        return decode(d) if d else {}

    try:
        r = send(make_runcmd_request("echo RUNCMD-OK"))
        print(f"  echo -> ok={r.get('ok')} out={r.get('output')!r}")
        assert r.get("ok"), "echo 应成功"
        assert "RUNCMD-OK" in r.get("output", "")
        assert r.get("cwd"), "应回传 cwd"

        # 空命令
        r = send(make_runcmd_request(""))
        print(f"  空命令 -> ok={r.get('ok')} out={r.get('output')!r}")
        assert not r.get("ok"), "空命令应失败"

        # 多行命令（shell 会按行依次执行）
        r = send(make_runcmd_request("echo LINE1\necho LINE2"))
        out = r.get("output", "")
        print(f"  多行 -> ok={r.get('ok')} out={out!r}")
        assert "LINE1" in out and "LINE2" in out, "两行都应执行"

        # notify 字段回传（沙盒无 tkinter → notified=False，但字段要存在）
        r = send(make_runcmd_request("echo NOTIFY-TEST", notify=True))
        print(f"  notify=True -> notified={r.get('notified')} (沙盒无GUI故False)")
        assert "notified" in r, "应回传 notified 字段"
        print("  ✓ 执行/空命令/多行/notify 回传 均正常")
    finally:
        a.shutdown()


def test_runcmd_timeout():
    print("\n[测试4] runcmd 超时保护")
    a, port = start_agent(9904)

    def send(req, timeout=30):
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.settimeout(timeout)
        send_all(s, encode(req))
        d = recv_all(s, timeout=timeout)
        s.close()
        return decode(d) if d else {}

    try:
        t0 = time.time()
        r = send(make_runcmd_request("sleep 30", timeout=2), timeout=30)
        cost = time.time() - t0
        print(f"  sleep 30 / timeout=2 -> 耗时 {cost:.1f}s ok={r.get('ok')}")
        assert cost < 12, f"应很快返回，实际 {cost:.1f}s"
        assert not r.get("ok") and "超时" in r.get("output", "")

        # 超时后仍可用
        r = send(make_runcmd_request("echo AFTER-TIMEOUT"))
        print(f"  超时后再执行 -> {r.get('output')!r}")
        assert r.get("ok")
        print("  ✓ 超时生效且不影响后续")
    finally:
        a.shutdown()


# ---------- 5. 无环境降级 ----------

def test_notifier_degrade():
    print("\n[测试5] notifier 环境适配（关键：不能让被控端崩溃）")
    import notifier
    print(f"  HAS_TK={notifier.HAS_TK}  notify_available()={notifier.notify_available()}")

    # 不管有没有 tkinter / 有没有显示器，notify() 都必须:
    #   1) 不抛异常
    #   2) 立即返回（不阻塞网络线程）
    t0 = time.time()
    try:
        ok = notifier.notify("标题", "内容", sender="控制端", timeout=1)
    except Exception as e:
        raise AssertionError(f"notify() 抛异常了: {type(e).__name__}: {e}")
    cost = time.time() - t0
    print(f"  notify() -> {ok}，耗时 {cost*1000:.1f}ms")
    assert cost < 1.0, f"notify 不应阻塞（实际 {cost:.2f}s）"

    if notifier.HAS_TK:
        print("  有 tkinter: 返回 True 表示已投递到弹窗线程")
        assert ok is True
    else:
        print("  无 tkinter: 返回 False（降级为日志输出）")
        assert ok is False
    print("  ✓ 任何环境下都不崩溃、不阻塞")


# ---------- 6. 界面实现 ----------

def test_ui_implemented():
    print("\n[测试6] 两个按钮已真实实现（无占位）")
    import session as S
    src = inspect.getsource(S.SessionWindow)

    assert "_todo" not in src or src.count("self._todo(") == 0, \
        "不应再有 _todo 占位调用"
    print("  无 self._todo( 调用 ✓")

    for fn in ("act_send_command", "act_send_message"):
        body = inspect.getsource(getattr(S.SessionWindow, fn))
        assert "_todo" not in body, f"{fn} 仍是占位"
        print(f"  {fn} 已实现（{len(body.splitlines())} 行）")

    # 发送命令应有工作线程
    assert hasattr(S.SessionWindow, "_runcmd_worker"), "缺 _runcmd_worker"
    assert hasattr(S.SessionWindow, "_send_msg_worker"), "缺 _send_msg_worker"
    print("  _runcmd_worker / _send_msg_worker 均存在 ✓")
    print("  ✓ 两个按钮都是真实功能")


def test_no_duplicate_upload():
    print("\n[测试7] act_upload_file 只有一份")
    import session as S

    path = os.path.join(os.path.dirname(__file__), "session.py")
    src = open(path, encoding="utf-8").read()
    n = src.count("def act_upload_file(")
    print(f"  def act_upload_file( 出现 {n} 次")
    assert n == 1, f"有 {n} 份定义，占位版会覆盖真实版（旧 bug）"

    body = inspect.getsource(S.SessionWindow.act_upload_file)
    assert "_todo" not in body, "上传文件按钮仍是占位（会被真实版覆盖）"
    print("  ✓ 只有真实实现，按钮点击会真的上传")


def test_all_actions_real():
    print("\n[测试8] 6 个按钮全部有真实实现")
    import session as S
    actions = {
        "发送命令": "act_send_command",
        "发送消息": "act_send_message",
        "上传文件": "act_upload_file",
        "进程管理": "act_process_manage",
        "查看日志": "act_view_log",
        "打开网址": "act_open_url",
    }
    for label, fn in actions.items():
        body = inspect.getsource(getattr(S.SessionWindow, fn))
        assert "_todo" not in body, f"「{label}」仍是占位"
        assert len(body.splitlines()) > 3, f"「{label}」实现过短"
        print(f"  {label:8s} -> {fn}  ✓")
    print("  ✓ 无剩余占位功能")


def test_build_config():
    print("\n[测试9] 打包配置")
    import build as b
    assert "notifier" in b.AGENT_HIDDEN, "notifier 必须在被控端隐藏导入"
    print("  AGENT_HIDDEN 含 notifier ✓")
    print("  ✓ 打包会带上弹窗模块")


if __name__ == "__main__":
    print("=" * 62)
    print("  发送消息 / 发送命令 验证")
    print("=" * 62)
    test_protocol_build()
    test_agent_message()
    test_agent_runcmd()
    test_runcmd_timeout()
    test_notifier_degrade()
    test_ui_implemented()
    test_no_duplicate_upload()
    test_all_actions_real()
    test_build_config()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("  （弹窗动画需在 Windows 教室机上验证：沙盒无显示环境）")
    print("=" * 62)
