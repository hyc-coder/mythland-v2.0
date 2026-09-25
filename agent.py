"""
agent.py - 被控端 (零配置)
用法:
    python agent.py                  # 单机 / 局域网都能自动发现
    python agent.py --name 学生机-01  # 可选：指定名称

设计:
- 自动推算本机局域网 IP
- 向 多个广播地址 + 组播 发送上线通告 (绕过防火墙拦截)
- 响应控制端的 "who_is_there" 主动喊话
- 屏幕采集走 screen.py (真实截图优先，失败则模拟)
"""

import argparse
import base64
import json
import os
import platform
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid

from common import (
    make_udp_socket, recv_all, send_all, encode, decode, MULTICAST_PORT,
    setup_headless_logging, enable_file_logging,
    CHUNK_SIZE,
    make_file_list_response, make_file_list_error,
    make_download_response, make_download_error,
    make_upload_response, make_delete_response,
    make_command_response,
    CMD_SAFE_MODE_OFF, CMD_SAFE_MODE_ON, CMD_SAFE_STATUS,
    CMD_TIMEOUT, CMD_MAX_TIMEOUT,
)
from file_mgr import FileUploader
import screen

BEACON_INTERVAL = 5.0      # 秒
DISCOVERY_PORT = 9086       # 与 controller 约定的发现端口
LOG_NAME = "agent.log"      # 常驻日志文件名（写在程序同目录）
LOG_PATH = None             # 实际日志路径（main 中赋值，供远程查看）

IS_WINDOWS = platform.system() == "Windows"


def _no_window_flags():
    """Windows 下隐藏子进程窗口（被控端静默运行必需）"""
    if not IS_WINDOWS:
        return 0
    try:
        return subprocess.CREATE_NO_WINDOW      # type: ignore[attr-defined]
    except Exception:
        return 0


def read_log_tail(lines: int = 200) -> str:
    """
    读取 agent.log 末尾 N 行（供控制端远程查看）。
    文件不存在 / 打不开时返回友好提示，绝不抛异常。
    """
    import os
    path = LOG_PATH
    if not path or not os.path.exists(path):
        return "(暂无日志文件 —— 被控端可能未以日志模式启动)"

    try:
        # 二进制读，避免编码问题；只读尾部，大文件也快
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            # 粗略估算尾部字节数（每行按 100 字节算，多读一些）
            want = min(size, lines * 200 + 4096)
            f.seek(max(0, size - want))
            data = f.read()

        text = data.decode("utf-8", errors="replace")
        all_lines = text.splitlines()
        tail = all_lines[-lines:] if len(all_lines) > lines else all_lines

        header = f"=== {path} (末尾 {len(tail)} 行) ===\n"
        return header + "\n".join(tail)
    except Exception as e:
        return f"(读取日志失败: {e})"


def get_local_ip() -> str:
    """获取本机在局域网中的 IP（用于推算网段）"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_broadcast_addresses() -> list[str]:
    """生成要广播的地址列表：组播 + 网段广播 + 受限广播"""
    addrs = ["224.0.0.1", "255.255.255.255"]
    local = get_local_ip()
    if local and local != "127.0.0.1":
        parts = local.split(".")
        if len(parts) == 4:
            addrs.append(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
    # 去重
    seen = set()
    out = []
    for a in addrs:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


class Agent:
    def __init__(self, name: str, port: int, broadcast_port: int):
        # 远程命令的当前工作目录（cd 会持久生效，shell 每次是新进程）
        try:
            self._cwd = os.getcwd()
        except Exception:
            self._cwd = os.path.expanduser("~")
        self.machine_id = str(uuid.uuid4())[:8]
        self.name = name
        self.port = port
        self.broadcast_port = broadcast_port
        self.ip = get_local_ip()
        self.capturer = screen.ScreenCapturer(name)
        self.thumb_lock = threading.Lock()
        self._last_thumb = self.capturer.capture_jpeg()
        self._full_size = (0, 0)      # 最近一帧原始分辨率 (w, h)
        self._running = True

        self.udp = make_udp_socket()
        try:
            self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception:
            pass

        # TCP 监听: 端口被占用时自动顺延（9001→9002→...）
        # 解决两个实际问题:
        #   1. 学生机重复双击被控端 → 不会静默崩溃，而是起第二个实例
        #   2. 端口被别的程序占用 → 自动避让
        self.tcp, self.port = self._bind_tcp(self.port)

    def _bind_tcp(self, start_port: int, max_tries: int = 20):
        """
        绑定 TCP 监听端口，被占用则自动顺延。
        返回 (socket, 实际端口)
        """
        last_err = None
        for p in range(start_port, start_port + max_tries):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", p))
                s.listen(5)
                if p != start_port:
                    print(f"[Agent] 端口 {start_port} 被占用，已改用 {p}")
                return s, p
            except OSError as e:
                last_err = e
                try:
                    s.close()
                except Exception:
                    pass
                continue
        raise RuntimeError(
            f"端口 {start_port}~{start_port + max_tries - 1} 均被占用，无法启动。\n"
            f"最后错误: {last_err}"
        )

    # ---------- 缩略图 (独立线程，固定 1FPS 采集) ----------

    def _thumb_loop(self):
        while self._running:
            try:
                data = self.capturer.capture_jpeg()
                with self.thumb_lock:
                    self._last_thumb = data
            except Exception as e:
                print(f"[Agent] 采集异常: {e}")
            time.sleep(1.0)   # 1 FPS

    def get_thumb(self) -> bytes:
        with self.thumb_lock:
            return self._last_thumb

    # ---------- 上线通告 ----------

    def _beacon_loop(self):
        addrs = get_broadcast_addresses()
        print(f"[Agent] 广播目标: {addrs}")
        while self._running:
            for addr in addrs:
                try:
                    payload = encode({
                        "type": "hello",
                        "id": self.machine_id,
                        "name": self.name,
                        "os": self.capturer.os_name,
                        "ip": self.ip,
                        "port": self.port,
                        "thumb": b64encode(self.get_thumb()),
                    })
                    self.udp.sendto(payload, (addr, DISCOVERY_PORT))
                except Exception as e:
                    print(f"[Agent] 广播失败 ({addr}): {e}")
            print(f"[Agent] 广播上线: {self.name} -> {addrs} (自身TCP:{self.port})")
            time.sleep(BEACON_INTERVAL)

    # ---------- TCP 控制服务 ----------

    def _handle(self, conn: socket.socket, addr):
        """
        处理一个控制端连接。
        关键: 支持【长连接多帧】—— 一个连接上连续处理多条消息。
        30FPS 屏幕监控必须复用同一条 TCP，否则每帧都握手，延迟和开销都受不了。
        """
        uploader = None          # 当前连接的上传会话（分块写入用）
        try:
            while self._running:
                data = recv_all(conn, timeout=30.0)
                if not data:
                    break          # 对端关闭
                try:
                    msg = decode(data)
                except Exception as e:
                    print(f"[Agent] 消息解析失败: {e}")
                    break

                mtype = msg.get("type")

                if mtype == "thumb_req":
                    # 缩略图（预览墙用，低频）
                    send_all(conn, encode({
                        "type": "thumb_res",
                        "id": self.machine_id,
                        "thumb": b64encode(self.get_thumb()),
                    }))

                elif mtype == "screen_req":
                    # 全尺寸实时帧（屏幕监控用，高频 30FPS）
                    w = int(msg.get("width", 0) or 0)
                    h = int(msg.get("height", 0) or 0)
                    q = int(msg.get("quality", 55) or 55)
                    q = max(10, min(95, q))
                    try:
                        if w > 0 and h > 0:
                            jpeg = self.capturer.capture_jpeg(w, h, q)
                            rw, rh = w, h
                        else:
                            # 原始分辨率
                            jpeg = self._capture_full(q)
                            rw, rh = self._full_size
                    except Exception as e:
                        print(f"[Agent] 采集失败: {e}")
                        jpeg, rw, rh = b"", 0, 0
                    send_all(conn, encode({
                        "type": "screen_res",
                        "frame": b64encode(jpeg),
                        "width": rw,
                        "height": rh,
                    }))

                elif mtype == "list_req":
                    send_all(conn, encode({
                        "type": "list_res",
                        "machines": [{
                            "id": self.machine_id,
                            "name": self.name,
                            "os": self.capturer.os_name,
                            "ip": self.ip,
                            "port": self.port,
                            "thumb": b64encode(self.get_thumb()),
                        }],
                    }))

                elif mtype == "log_req":
                    # 控制端远程查看日志: 返回末尾 N 行
                    n = int(msg.get("lines", 200) or 200)
                    n = max(1, min(n, 5000))
                    send_all(conn, encode({
                        "type": "log_res",
                        "log": read_log_tail(n),
                        "path": LOG_PATH or "",
                    }))

                elif mtype == "proc_list_req":
                    # 进程列表（进程管理页）
                    try:
                        from process_mgr import get_process_list
                        procs, backend = get_process_list()
                    except Exception as e:
                        procs, backend = [], f"error: {e}"
                    send_all(conn, encode({
                        "type": "proc_list_res",
                        "procs": procs,
                        "backend": backend,
                        "count": len(procs),
                    }))

                elif mtype == "proc_kill_req":
                    # 结束进程
                    pid = int(msg.get("pid", 0) or 0)
                    force = bool(msg.get("force", False))
                    try:
                        from process_mgr import kill_process
                        ok, message = kill_process(pid, force)
                    except Exception as e:
                        ok, message = False, f"{type(e).__name__}: {e}"
                    print(f"[Agent] 结束进程 PID {pid}: {message}")
                    send_all(conn, encode({
                        "type": "proc_kill_res",
                        "pid": pid,
                        "ok": ok,
                        "message": message,
                    }))

                elif mtype == "file_list_req":
                    # 文件浏览：列目录
                    req_path = msg.get("path", "") or ""
                    try:
                        from file_mgr import list_dir
                        p, parent, entries, err = list_dir(req_path)
                    except Exception as e:
                        p, parent, entries, err = req_path, "", [], f"{type(e).__name__}: {e}"
                    if err:
                        send_all(conn, encode(make_file_list_error(err)))
                    else:
                        send_all(conn, encode(
                            make_file_list_response(p, entries, parent)))

                elif mtype == "file_dl_req":
                    # 下载：读一个分块
                    fpath = msg.get("path", "")
                    offset = int(msg.get("offset", 0) or 0)
                    size = int(msg.get("size", CHUNK_SIZE) or CHUNK_SIZE)
                    try:
                        from file_mgr import read_chunk
                        data, total, eof, err = read_chunk(fpath, offset, size)
                    except Exception as e:
                        data, total, eof, err = b"", 0, True, f"{type(e).__name__}: {e}"
                    if err:
                        send_all(conn, encode(make_download_error(err)))
                    else:
                        send_all(conn, encode(make_download_response(
                            b64encode(data), offset, total, eof)))

                elif mtype == "file_up_begin":
                    # 上传开始：准备写文件
                    d = msg.get("path", "")
                    name = msg.get("name", "")
                    size = int(msg.get("size", 0) or 0)
                    uploader = FileUploader()
                    ok, err = uploader.begin(d, name, size)
                    if ok:
                        send_all(conn, encode(
                            make_upload_response(True, "ready", uploader._path)))
                    else:
                        uploader = None
                        send_all(conn, encode(make_upload_response(False, err)))

                elif mtype == "file_up_chunk":
                    # 上传数据块
                    if uploader is None:
                        send_all(conn, encode(
                            make_upload_response(False, "未开始上传")))
                    else:
                        b64 = msg.get("data", "")
                        try:
                            raw = base64.b64decode(b64)
                        except Exception as e:
                            raw = b""
                        ok, err = uploader.write(raw)
                        send_all(conn, encode(
                            make_upload_response(ok, err, uploader._path if ok else "")))

                elif mtype == "file_up_end":
                    # 上传结束
                    if uploader is None:
                        send_all(conn, encode(
                            make_upload_response(False, "未开始上传")))
                    else:
                        ok, message, saved = uploader.end()
                        print(f"[Agent] 接收文件: {message} -> {saved}")
                        send_all(conn, encode(
                            make_upload_response(ok, message, saved)))
                        uploader = None

                elif mtype == "file_mkdir_req":
                    try:
                        from file_mgr import make_dir
                        ok, message = make_dir(msg.get("path", ""))
                    except Exception as e:
                        ok, message = False, f"{type(e).__name__}: {e}"
                    send_all(conn, encode(make_upload_response(ok, message)))

                elif mtype == "file_del_req":
                    try:
                        from file_mgr import delete_path
                        ok, message = delete_path(msg.get("path", ""))
                    except Exception as e:
                        ok, message = False, f"{type(e).__name__}: {e}"
                    print(f"[Agent] 删除: {message}")
                    send_all(conn, encode(make_delete_response(ok, message)))

                elif mtype == "cmd_req":
                    # 命令执行：先认内置指令，其余留给后续扩展
                    cmd = (msg.get("cmd", "") or "").strip()
                    timeout = float(msg.get("timeout", 0) or 0)
                    ok, output, builtin = self._run_command(cmd, timeout)
                    send_all(conn, encode(make_command_response(
                        ok, output, builtin,
                        cwd=self._cwd,
                        exit_code=0 if ok else 1,
                    )))

                elif mtype == "open_url_req":
                    # 在被控端默认浏览器打开网址
                    url = msg.get("url", "")
                    browser = msg.get("browser", "")
                    try:
                        from url_opener import open_url
                        ok, message, used = open_url(url, browser)
                    except Exception as e:
                        ok, message, used = False, f"{type(e).__name__}: {e}", ""
                    print(f"[Agent] 打开网址: {message}")
                    send_all(conn, encode({
                        "type": "open_url_res",
                        "ok": ok, "message": message, "browser": used,
                    }))

                elif mtype == "msg_send_req":
                    # 发送消息：在被控端右下角弹出通知
                    title = msg.get("title", "") or "消息"
                    text = msg.get("text", "")
                    sender = msg.get("sender", "")
                    timeout = float(msg.get("timeout", 8) or 0)
                    level = msg.get("level", "info")
                    try:
                        from notifier import notify
                        shown = notify(title, text, sender=sender,
                                       timeout=timeout, level=level)
                        print(f"[Agent] 弹出通知: {title}")
                        ok = bool(shown)
                        message = "已弹出通知" if ok else "弹窗不可用（无显示环境）"
                    except Exception as e:
                        ok, shown = False, False
                        message = f"弹出失败: {type(e).__name__}: {e}"
                    send_all(conn, encode({
                        "type": "msg_send_res",
                        "ok": ok, "message": message, "shown": shown,
                    }))

                elif mtype == "runcmd_req":
                    # 发送命令：执行 + 可选弹窗通知
                    cmd = (msg.get("cmd", "") or "").strip()
                    timeout = float(msg.get("timeout", 0) or 0)
                    want_notify = bool(msg.get("notify", False))
                    ntitle = msg.get("title", "") or "远程命令"

                    if not cmd:
                        send_all(conn, encode({
                            "type": "runcmd_res", "ok": False,
                            "output": "空命令", "exit_code": 1,
                            "cwd": self._cwd, "notified": False}))
                    else:
                        ok, output, builtin = self._run_command(cmd, timeout)
                        notified = False
                        if want_notify:
                            try:
                                from notifier import notify
                                brief = output[:120].replace("\n", " ")
                                notified = notify(
                                    ntitle, brief, sender="控制端",
                                    timeout=6, level="info")
                            except Exception:
                                notified = False
                        print(f"[Agent] 执行命令(对话框): {cmd}")
                        send_all(conn, encode({
                            "type": "runcmd_res", "ok": ok, "output": output,
                            "exit_code": 0 if ok else 1, "cwd": self._cwd,
                            "notified": notified}))

                elif mtype == "bc_start_req":
                    # 屏幕广播（主控端 → 我）: 打开不可关闭的窗口接收画面
                    host = msg.get("host", "")
                    port = int(msg.get("port", 0) or 0)
                    title = msg.get("title", "") or "屏幕广播"
                    try:
                        from viewer import get_viewer
                        v = get_viewer()
                        ok = v.start(host, port, title)
                        message = ("已开始接收广播" if ok
                                   else f"无法显示: {v.last_error() or '环境不支持'}")
                    except Exception as e:
                        ok = False
                        message = f"启动失败: {type(e).__name__}: {e}"
                    print(f"[Agent] 屏幕广播: {message}")
                    send_all(conn, encode({
                        "type": "bc_start_res", "ok": bool(ok),
                        "message": message}))

                elif mtype == "bc_stop_req":
                    # 结束广播: 关闭窗口（唯一合法的关闭途径）
                    try:
                        from viewer import get_viewer
                        get_viewer().stop()
                        ok = True
                        message = "已结束广播"
                    except Exception as e:
                        ok = False
                        message = f"结束失败: {type(e).__name__}: {e}"
                    print(f"[Agent] 屏幕广播: {message}")
                    send_all(conn, encode({
                        "type": "bc_stop_res", "ok": bool(ok),
                        "message": message}))

                elif mtype == "input_event":
                    # 键鼠远程控制: 注入后【不回响应】。
                    # 控制端用独立连接专门发这类事件（fire-and-forget），
                    # 高频输入时不必等回包，延迟更低，也不干扰 30FPS 拉帧。
                    self._inject_input(msg)

                elif mtype == "bye":
                    break

                else:
                    send_all(conn, encode({"type": "ok"}))

        except socket.timeout:
            pass
        except Exception as e:
            print(f"[Agent] 处理异常 {addr}: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _inject_input(self, msg: dict):
        """把一个输入事件注入本机（鼠标/键盘）"""
        try:
            from input_inject import get_injector
            inj = get_injector()
            if not inj.available:
                return

            evt = msg.get("event")
            x = int(msg.get("x", 0) or 0)
            y = int(msg.get("y", 0) or 0)
            button = msg.get("button", "left")
            delta = int(msg.get("delta", 0) or 0)
            key = msg.get("key", "")

            if evt == "mouse_move":
                inj.move_to(x, y)
            elif evt == "mouse_down":
                inj.mouse_down(x, y, button)
            elif evt == "mouse_up":
                inj.mouse_up(x, y, button)
            elif evt == "mouse_click":
                inj.click(x, y, button)
            elif evt == "mouse_wheel":
                inj.scroll(x, y, delta)
            elif evt == "key_down":
                inj.key_down(key)
            elif evt == "key_up":
                inj.key_up(key)
            elif evt == "key_press":
                inj.key_press(key)
        except Exception as e:
            print(f"[Agent] 输入注入异常: {e}")

    # ---------- 远程命令执行 ----------

    def _do_cd(self, cmd: str):
        """
        切换工作目录。
        shell 每次调用都是新进程，cd 不会持久，所以得在 agent 侧记住 cwd。
        """
        parts = cmd.split(None, 1)
        target = parts[1].strip().strip('"') if len(parts) > 1 else ""

        # 无参数 → 回到家目录（Windows 下 cd 无参是显示当前目录，这里兼容两者）
        if not target or target == "~":
            target = os.path.expanduser("~")

        # 相对路径 → 基于当前 cwd 解析
        if not os.path.isabs(target):
            target = os.path.join(self._cwd, target)
        target = os.path.normpath(target)

        if not os.path.exists(target):
            return False, f"目录不存在: {target}", True
        if not os.path.isdir(target):
            return False, f"不是目录: {target}", True

        self._cwd = target
        print(f"[Agent] 工作目录切换为: {self._cwd}")
        return True, self._cwd, True

    def _do_shell(self, cmd: str, timeout: float = 0):
        """
        真正执行一条系统命令。

        返回 (ok, output, builtin=False)
        ok 取决于进程退出码是否为 0。
        """
        import subprocess

        # 超时钳制，防止控制端传个超大值把连接拖死
        if not timeout or timeout <= 0:
            timeout = CMD_TIMEOUT
        timeout = max(1.0, min(float(timeout), CMD_MAX_TIMEOUT))

        # 始终走 shell:
        #   Windows → cmd.exe（支持 dir / ipconfig 等内建命令）
        #   Linux/Mac → /bin/sh（支持 echo / ls / 管道等）
        # 不加 shell 的话 "echo xxx" 会被当成可执行文件路径而报 No such file。
        creationflags = _no_window_flags()

        try:
            p = subprocess.run(
                cmd,
                shell=True,
                cwd=self._cwd,
                capture_output=True,
                timeout=timeout,
                creationflags=creationflags,
            )
        except subprocess.TimeoutExpired:
            return False, (
                f"命令执行超时（>{timeout:.0f} 秒），已终止。\n"
                f"默认超时 {CMD_TIMEOUT:.0f} 秒，最长 {CMD_MAX_TIMEOUT:.0f} 秒。\n"
                f"提示: 后台运行的命令请在末尾加 & （Linux）或用 start （Windows）。"
            ), False
        except FileNotFoundError as e:
            return False, f"执行失败: {e}", False
        except Exception as e:
            return False, f"{type(e).__name__}: {e}", False

        out, err = p.stdout, p.stderr
        # Windows 中文环境输出是 GBK，Linux 是 UTF-8
        enc = "gbk" if IS_WINDOWS else "utf-8"
        try:
            text_out = out.decode(enc, errors="replace")
            text_err = err.decode(enc, errors="replace")
        except Exception:
            text_out = out.decode("utf-8", errors="replace")
            text_err = err.decode("utf-8", errors="replace")

        parts = []
        if text_out:
            parts.append(text_out.rstrip("\r\n"))
        if text_err:
            parts.append(text_err.rstrip("\r\n"))
        if not parts:
            parts.append(f"(无输出，退出码 {p.returncode})")

        return (p.returncode == 0), "\n".join(parts), False

    def _run_command(self, cmd: str, timeout: float = 0):
        """
        执行命令。返回 (ok, output, builtin)

        内置指令（不区分大小写）:
          SAFE_MODE_OFF    临时关闭 C:\\Windows 写保护（本次进程有效）
          SAFE_MODE_ON     恢复写保护
          SAFE_MODE_STATUS 查询保护状态
          cd <目录>        切换工作目录（持久生效）
          pwd / cwd        显示当前工作目录

        其余命令交给系统 shell 执行（默认 30 秒超时）。
        """
        if not cmd:
            return False, "空命令", True

        upper = cmd.upper()

        if upper == CMD_SAFE_MODE_OFF:
            try:
                from file_mgr import set_safe_mode, safe_status
                set_safe_mode(False)
                print(f"[Agent] 保护已临时关闭（由控制端命令）")
                return True, f"✓ 已临时关闭 C:\\Windows 写保护\n" \
                             f"  当前状态: {safe_status()}\n" \
                             f"  输入 SAFE_MODE_ON 可恢复；被控端重启后自动恢复保护。", True
            except Exception as e:
                return False, f"切换失败: {type(e).__name__}: {e}", True

        if upper == CMD_SAFE_MODE_ON:
            try:
                from file_mgr import set_safe_mode, safe_status
                set_safe_mode(True)
                print(f"[Agent] 保护已恢复（由控制端命令）")
                return True, f"✓ 已恢复 C:\\Windows 写保护\n" \
                             f"  当前状态: {safe_status()}", True
            except Exception as e:
                return False, f"切换失败: {type(e).__name__}: {e}", True

        if upper == CMD_SAFE_STATUS:
            try:
                from file_mgr import safe_status, SAFE_MODE
                return True, f"保护状态: {safe_status()}\n" \
                             f"（默认配置 SAFE_MODE={SAFE_MODE}，" \
                             f"重启被控端后回到该值）", True
            except Exception as e:
                return False, f"查询失败: {e}", True

        # ---- cd: 切换工作目录（shell=True 时 cd 不会持久，必须自己维护） ----
        if upper == "CD" or upper.startswith("CD ") or upper == "CHDIR" \
                or upper.startswith("CHDIR "):
            return self._do_cd(cmd)

        # ---- 内置: 显示当前工作目录 ----
        if upper in ("PWD", "CWD"):
            return True, self._cwd, True

        # ---- 其余: 交给系统 shell 执行 ----
        return self._do_shell(cmd, timeout)

    def _capture_full(self, quality: int) -> bytes:
        """
        采集原始分辨率的一帧。
        优先用 mss 直出全屏 JPEG；不可用时退回 ScreenCapturer。
        """
        import io
        try:
            import mss
            from PIL import Image
            with mss.mss() as sct:
                mon = sct.monitors[1]          # 主显示器
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.rgb)
                self._full_size = (img.width, img.height)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality)
                return buf.getvalue()
        except Exception:
            # 降级: 用 ScreenCapturer 的默认尺寸
            try:
                jpeg = self.capturer.capture_jpeg(960, 540, quality)
                self._full_size = (960, 540)
                return jpeg
            except Exception:
                self._full_size = (0, 0)
                return b""

    def _accept_loop(self):
        print(f"[Agent] TCP服务启动，监听端口 {self.port}")
        self.tcp.settimeout(1.0)
        while self._running:
            try:
                conn, addr = self.tcp.accept()
                threading.Thread(target=self._handle, args=(conn, addr), daemon=True).start()
                print(f"[Agent] 控制端连接: {addr}")
            except socket.timeout:
                continue
            except Exception:
                break

    def run(self):
        print(f"[Agent] 启动: {self.name} ({self.capturer.os_name})")
        print(f"[Agent] 本机IP: {self.ip}, 监听端口: {self.port}")
        threading.Thread(target=self._thumb_loop, daemon=True).start()
        threading.Thread(target=self._beacon_loop, daemon=True).start()
        self._accept_loop()

    def shutdown(self):
        self._running = False
        try:
            self.udp.close()
        except Exception:
            pass
        try:
            self.tcp.close()
        except Exception:
            pass


def b64encode(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")


def parse_args():
    p = argparse.ArgumentParser(description="被控端 (零配置)")
    p.add_argument("--name", default=None, help="机器名称 (默认自动生成)")
    p.add_argument("--port", type=int, default=9001, help="本机TCP监听端口")
    p.add_argument("--broadcast-port", type=int, default=9000, help="控制端监听端口")
    return p.parse_args()


def main():
    # 常驻日志: 无论有没有控制台，都写到【程序同目录】的 agent.log
    # （--windowed 打包后无控制台，print 会崩，这一步同时解决该问题）
    global LOG_PATH
    LOG_PATH = enable_file_logging(LOG_NAME)

    args = parse_args()
    if not args.name:
        import platform
        # 零配置: 就用电脑名，不带端口后缀（真实部署每台机器一个 agent）
        args.name = platform.node() or f"PC-{args.port}"

    agent = Agent(args.name, args.port, args.broadcast_port)
    agent.log_path = LOG_PATH
    if LOG_PATH:
        print(f"[Agent] 日志文件: {LOG_PATH}")
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n[Agent] 退出中...")
        agent.shutdown()


if __name__ == "__main__":
    main()
