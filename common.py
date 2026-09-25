"""
common.py - 共享通信协议
所有消息格式: [4字节长度前缀 BigEndian][JSON字符串]

第二版新增: 屏幕缩略图（用于预览墙），以 base64 编码的 JPEG 承载。
"""

import json
import struct
import base64
import socket

# ============ 消息类型常量 ============
MSG_HELLO = "hello"           # Agent 上线通告（v2: 可携带首帧缩略图）
MSG_HEARTBEAT = "heartbeat"   # 心跳
MSG_LIST_REQUEST = "list_req" # 控制端请求机器列表
MSG_LIST_RESPONSE = "list_res" # 返回机器列表
MSG_BYE = "bye"               # 下线
# ---- v2 新增 ----
MSG_THUMB_REQUEST = "thumb_req"   # 控制端请求缩略图
MSG_THUMB_RESPONSE = "thumb_res"  # Agent 返回缩略图(jpeg base64)
MSG_SCREEN_REQUEST = "screen_req" # 请求一帧完整画面（预留）
MSG_SCREEN_RESPONSE = "screen_res"
MSG_INPUT_EVENT = "input_event"   # 键鼠远程控制事件
# ---- v3 零配置自动发现 ----
MSG_WHO_IS_THERE = "who_is_there" # 控制端喊话: 谁在线?（Agent 收到立刻回 hello）
MSG_I_AM_HERE = "i_am_here"       # Agent 应答

# ============ 零配置自动发现 ============
# 组播地址: 不依赖网段推算，交换机通常直接转发，比 255 广播更可靠
MULTICAST_GROUP = "239.168.86.86"
MULTICAST_PORT = 9086
MULTICAST_TTL = 2          # 允许跨一个路由器(局域网内够用)
BROADCAST_PORT = 9086      # 默认发现端口（与 MULTICAST_PORT 一致）


def get_local_ip() -> str:
    """获取本机在局域网中的 IP（不改路由表，纯 UDP 探测）"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def guess_broadcast_addrs() -> list:
    """
    自动推算所有可能的广播地址（零配置核心）。
    返回候选列表，Agent 挨个发，总有一个能到。
    """
    addrs = [MULTICAST_GROUP]          # 组播优先（最可靠）
    try:
        ip = get_local_ip()
        if ip and ip != "127.0.0.1":
            parts = ip.split(".")
            addrs.append(".".join(parts[:3]) + ".255")   # 本网段广播
        addrs.append("255.255.255.255")                  # 受限广播(兜底)
    except Exception:
        pass
    return addrs

# ============ 编解码 ============

def encode(msg_dict: dict) -> bytes:
    """把字典编码为网络字节流: 4字节长度 + JSON"""
    payload = json.dumps(msg_dict, ensure_ascii=False).encode("utf-8")
    header = struct.pack(">I", len(payload))  # 大端4字节
    return header + payload


def decode(data: bytes) -> dict:
    """把接收到的字节流解码为字典"""
    if len(data) < 4:
        raise ValueError("数据太短，无法解析长度头")
    length = struct.unpack(">I", data[:4])[0]
    payload = data[4:4 + length]
    return json.loads(payload.decode("utf-8"))


# ============ base64 包装（缩略图用） ============

def b64_encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64_decode(s: str) -> bytes:
    return base64.b64decode(s)


# ============ 消息构造 ============

def make_hello(name: str, os_info: str, thumb_b64: str = "") -> dict:
    """构造上线通告消息（v2: 可携带首帧缩略图）"""
    msg = {"type": MSG_HELLO, "name": name, "os": os_info}
    if thumb_b64:
        msg["thumb"] = thumb_b64
    return msg


def make_heartbeat() -> dict:
    return {"type": MSG_HEARTBEAT}


def make_list_request() -> dict:
    return {"type": MSG_LIST_REQUEST}


def make_list_response(machines: list) -> dict:
    """machines: [{"ip":..., "name":..., "os":..., "status":..., "thumb":...}, ...]"""
    return {"type": MSG_LIST_RESPONSE, "machines": machines}


def make_bye() -> dict:
    return {"type": MSG_BYE}


def make_thumb_request(width: int = 160, height: int = 100) -> dict:
    """请求缩略图，可指定目标尺寸"""
    return {"type": MSG_THUMB_REQUEST, "width": width, "height": height}


def make_thumb_response(thumb_b64: str, width: int, height: int) -> dict:
    return {
        "type": MSG_THUMB_RESPONSE,
        "thumb": thumb_b64,
        "width": width,
        "height": height,
    }


def make_who_is_there() -> dict:
    """控制端主动喊话（零配置发现：无需 agent 先广播）"""
    return {"type": MSG_WHO_IS_THERE}


# ============ 屏幕监控（全尺寸帧，30FPS） ============

def make_screen_request(width: int = 0, height: int = 0, quality: int = 55) -> dict:
    """
    请求一帧完整画面。
    width/height 为 0 或负数 → 使用被控端原始分辨率（不缩放）。
    quality: JPEG 质量 1-95，30FPS 场景建议 40-60（省带宽）。
    """
    return {
        "type": MSG_SCREEN_REQUEST,
        "width": int(width),
        "height": int(height),
        "quality": int(quality),
    }


def make_screen_response(thumb_b64: str, width: int, height: int) -> dict:
    return {
        "type": MSG_SCREEN_RESPONSE,
        "frame": thumb_b64,     # 字段名用 frame，便于与缩略图区分
        "width": width,
        "height": height,
    }


# ============ 键鼠远程控制 ============

# 事件类型
EVT_MOUSE_MOVE = "mouse_move"     # 移动: x, y (绝对坐标)
EVT_MOUSE_DOWN = "mouse_down"     # 按下: x, y, button(left/right/middle)
EVT_MOUSE_UP = "mouse_up"         # 抬起: x, y, button
EVT_MOUSE_CLICK = "mouse_click"   # 单击: x, y, button
EVT_MOUSE_WHEEL = "mouse_wheel"   # 滚轮: x, y, delta
EVT_KEY_DOWN = "key_down"         # 按键按下: key
EVT_KEY_UP = "key_up"             # 按键抬起: key
EVT_KEY_PRESS = "key_press"       # 完整按键(按下+抬起): key


def make_input_event(event_type: str, **kwargs) -> dict:
    """
    构造一个输入事件。
    make_input_event(EVT_MOUSE_MOVE, x=100, y=200)
    make_input_event(EVT_MOUSE_CLICK, x=100, y=200, button="left")
    make_input_event(EVT_KEY_PRESS, key="a")
    """
    msg = {"type": MSG_INPUT_EVENT, "event": event_type}
    msg.update(kwargs)
    return msg


# ============ 打包成 exe（--windowed）后的输出保护 ============

def setup_headless_logging(log_name: str = "run.log"):
    """
    PyInstaller 打包成 --windowed（无控制台）时，sys.stdout / sys.stderr 会是 None，
    任何 print() 都会抛 AttributeError 导致程序直接崩溃退出。

    这里把输出重定向到日志文件；若连文件都打不开，就丢弃输出（至少不崩）。

    返回日志文件路径（没有重定向则返回 None）。
    """
    import sys as _sys
    import os as _os

    if _sys.stdout is not None and _sys.stderr is not None:
        return None                      # 有控制台，无需处理

    try:
        if getattr(_sys, "frozen", False):
            base = _os.path.dirname(_sys.executable)   # 打包后：exe 所在目录
        else:
            base = _os.path.dirname(_os.path.abspath(__file__))
        path = _os.path.join(base, log_name)
        f = open(path, "a", encoding="utf-8", buffering=1)
        if _sys.stdout is None:
            _sys.stdout = f
        if _sys.stderr is None:
            _sys.stderr = f
        return path
    except Exception:
        class _Null:
            def write(self, *a, **k):
                pass

            def flush(self):
                pass

        if _sys.stdout is None:
            _sys.stdout = _Null()
        if _sys.stderr is None:
            _sys.stderr = _Null()
        return None


MAX_LOG_BYTES = 2 * 1024 * 1024   # 日志超过 2MB 自动轮转，防止无限增长


class _Tee:
    """同时写【原输出流】和【日志文件】（原流为 None 时只写文件）"""

    def __init__(self, stream, file):
        self._stream = stream
        self._file = file

    def write(self, s):
        try:
            if self._stream is not None:
                self._stream.write(s)
        except Exception:
            pass
        try:
            self._file.write(s)
        except Exception:
            pass
        return len(s) if s else 0

    def flush(self):
        for t in (self._stream, self._file):
            try:
                if t is not None:
                    t.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def _app_dir() -> str:
    """程序所在目录（打包后取 exe 目录，源码运行取脚本目录）"""
    import sys as _sys
    import os as _os
    if getattr(_sys, "frozen", False):
        return _os.path.dirname(_sys.executable)
    return _os.path.dirname(_os.path.abspath(_sys.argv[0] or __file__))


def _rotate_if_needed(path: str, max_bytes: int = MAX_LOG_BYTES):
    """日志过大时把旧的改名备份，只保留一份"""
    import os as _os
    try:
        if _os.path.exists(path) and _os.path.getsize(path) > max_bytes:
            bak = path + ".old"
            if _os.path.exists(bak):
                _os.remove(bak)
            _os.rename(path, bak)
    except Exception:
        pass


def enable_file_logging(log_name: str):
    """
    常驻日志: 无论有没有控制台，都把 print / 异常输出写入【程序同目录】的日志文件。

    - --windowed 打包后无控制台: sys.stdout 为 None → 全部进日志（否则 print 会崩）
    - 有控制台时: 两边都写（控制台照常看，日志同步留存）

    返回日志文件绝对路径（失败返回 None）。
    """
    import sys as _sys
    import os as _os
    from datetime import datetime

    try:
        path = _os.path.join(_app_dir(), log_name)
        _rotate_if_needed(path)
        f = open(path, "a", encoding="utf-8", buffering=1)
        f.write("\n" + "=" * 56 + "\n")
        f.write(f"  启动于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  程序目录: {_app_dir()}\n")
        f.write("=" * 56 + "\n")
        _sys.stdout = _Tee(_sys.stdout, f)
        _sys.stderr = _Tee(_sys.stderr, f)
        return path
    except Exception:
        # 连日志都开不了也不能崩：无输出直接丢弃
        class _Null:
            def write(self, *a, **k):
                pass

            def flush(self):
                pass

        if _sys.stdout is None:
            _sys.stdout = _Null()
        if _sys.stderr is None:
            _sys.stderr = _Null()
        return None


# ============ 日志查看协议（控制端远程读取被控端日志） ============

MSG_LOG_REQUEST = "log_req"    # 控制端请求日志: lines=要读取的末尾行数
MSG_LOG_RESPONSE = "log_res"


# ============ 进程管理 ============

MSG_PROC_LIST_REQUEST = "proc_list_req"   # 请求进程列表
MSG_PROC_LIST_RESPONSE = "proc_list_res"
MSG_PROC_KILL_REQUEST = "proc_kill_req"   # 结束进程: pid, force
MSG_PROC_KILL_RESPONSE = "proc_kill_res"


def make_proc_list_request() -> dict:
    """请求被控端进程列表"""
    return {"type": MSG_PROC_LIST_REQUEST}


def make_proc_list_response(procs: list, backend: str = "") -> dict:
    """
    procs: [{pid, name, cpu, mem, status, exe}, ...]
    backend: 采集方式（psutil / tasklist / ps），便于排查
    """
    return {
        "type": MSG_PROC_LIST_RESPONSE,
        "procs": procs,
        "backend": backend,
        "count": len(procs),
    }


def make_proc_kill_request(pid: int, force: bool = False) -> dict:
    """请求结束进程。force=True 用 SIGKILL / taskkill /F"""
    return {"type": MSG_PROC_KILL_REQUEST, "pid": int(pid), "force": bool(force)}


def make_proc_kill_response(pid: int, ok: bool, message: str = "") -> dict:
    return {
        "type": MSG_PROC_KILL_RESPONSE,
        "pid": int(pid),
        "ok": bool(ok),
        "message": message,
    }


# ============ 文件管理（列表 / 上传 / 下载） ============

MSG_FILE_LIST_REQUEST = "file_list_req"       # {path}
MSG_FILE_LIST_RESPONSE = "file_list_res"
MSG_FILE_DOWNLOAD_REQUEST = "file_dl_req"     # {path, offset, size}
MSG_FILE_DOWNLOAD_RESPONSE = "file_dl_res"
MSG_FILE_UPLOAD_BEGIN = "file_up_begin"       # {path, name, size}
MSG_FILE_UPLOAD_CHUNK = "file_up_chunk"       # {data_b64}
MSG_FILE_UPLOAD_END = "file_up_end"           # {}
MSG_FILE_UPLOAD_RESPONSE = "file_up_res"      # {ok, message}
MSG_FILE_MKDIR_REQUEST = "file_mkdir_req"     # {path}
MSG_FILE_DELETE_REQUEST = "file_del_req"      # {path}
MSG_FILE_DELETE_RESPONSE = "file_del_res"

CHUNK_SIZE = 256 * 1024      # 分块大小 256KB，避免单条消息过大


def make_file_list_request(path: str = "") -> dict:
    """请求目录列表。path 为空 → 返回被控端根目录（Windows 是盘符列表）"""
    return {"type": MSG_FILE_LIST_REQUEST, "path": path}


def make_file_list_response(path: str, entries: list, parent: str = "") -> dict:
    """
    entries: [{name, path, is_dir, size, mtime}, ...]
    parent: 上级目录路径
    """
    return {
        "type": MSG_FILE_LIST_RESPONSE,
        "path": path,
        "entries": entries,
        "parent": parent,
        "ok": True,
    }


def make_file_list_error(message: str) -> dict:
    return {"type": MSG_FILE_LIST_RESPONSE, "ok": False,
            "message": message, "entries": [], "path": ""}


def make_download_request(path: str, offset: int = 0, size: int = CHUNK_SIZE) -> dict:
    return {"type": MSG_FILE_DOWNLOAD_REQUEST,
            "path": path, "offset": int(offset), "size": int(size)}


def make_download_response(data_b64: str, offset: int, total: int, eof: bool,
                           message: str = "") -> dict:
    return {
        "type": MSG_FILE_DOWNLOAD_RESPONSE,
        "data": data_b64,
        "offset": int(offset),
        "total": int(total),
        "eof": bool(eof),
        "ok": True,
        "message": message,
    }


def make_download_error(message: str) -> dict:
    return {"type": MSG_FILE_DOWNLOAD_RESPONSE, "ok": False,
            "message": message, "data": "", "eof": True}


def make_upload_begin(path: str, name: str, size: int) -> dict:
    """开始上传：path 是【远端目录】，name 是文件名"""
    return {"type": MSG_FILE_UPLOAD_BEGIN,
            "path": path, "name": name, "size": int(size)}


def make_upload_chunk(data_b64: str) -> dict:
    return {"type": MSG_FILE_UPLOAD_CHUNK, "data": data_b64}


def make_upload_end() -> dict:
    return {"type": MSG_FILE_UPLOAD_END}


def make_upload_response(ok: bool, message: str = "", path: str = "") -> dict:
    return {"type": MSG_FILE_UPLOAD_RESPONSE,
            "ok": bool(ok), "message": message, "path": path}


def make_mkdir_request(path: str) -> dict:
    return {"type": MSG_FILE_MKDIR_REQUEST, "path": path}


def make_delete_request(path: str) -> dict:
    return {"type": MSG_FILE_DELETE_REQUEST, "path": path}


def make_delete_response(ok: bool, message: str = "") -> dict:
    return {"type": MSG_FILE_DELETE_RESPONSE, "ok": bool(ok), "message": message}


# ============ 命令执行（内置指令 / 系统命令） ============

MSG_COMMAND_REQUEST = "cmd_req"       # {cmd}
MSG_COMMAND_RESPONSE = "cmd_res"      # {ok, output}

# 内置指令（由 agent 直接处理，不执行系统命令）
CMD_SAFE_MODE_OFF = "SAFE_MODE_OFF"   # 临时关闭 C:\Windows 写保护
CMD_SAFE_MODE_ON = "SAFE_MODE_ON"     # 恢复写保护
CMD_SAFE_STATUS = "SAFE_MODE_STATUS"  # 查询保护状态


def make_command_request(cmd: str, timeout: float = 0) -> dict:
    """timeout=0 表示用被控端默认超时"""
    return {"type": MSG_COMMAND_REQUEST, "cmd": cmd, "timeout": float(timeout)}


def make_command_response(ok: bool, output: str = "", builtin: bool = False,
                          cwd: str = "", exit_code: int = 0) -> dict:
    return {"type": MSG_COMMAND_RESPONSE,
            "ok": bool(ok), "output": output, "builtin": bool(builtin),
            "cwd": cwd, "exit_code": int(exit_code)}


# 命令执行默认超时（秒）。长时间命令可让控制端传更大的 timeout。
CMD_TIMEOUT = 30.0
CMD_MAX_TIMEOUT = 300.0


# ============ 打开网址（在被控端浏览器打开） ============

MSG_OPEN_URL_REQUEST = "open_url_req"     # {url, browser}
MSG_OPEN_URL_RESPONSE = "open_url_res"    # {ok, message, browser}


def make_open_url_request(url: str, browser: str = "") -> dict:
    """
    url:     要打开的网址
    browser: 指定浏览器名（可选）。空 = 系统默认浏览器
             常见值: "chrome" / "edge" / "firefox" / "ie"
    """
    return {"type": MSG_OPEN_URL_REQUEST,
            "url": url, "browser": (browser or "").strip()}


def make_open_url_response(ok: bool, message: str = "", browser: str = "") -> dict:
    return {"type": MSG_OPEN_URL_RESPONSE,
            "ok": bool(ok), "message": message, "browser": browser}


# ============ 发送消息（被控端右下角弹窗通知） ============

MSG_MESSAGE_REQUEST = "msg_send_req"      # {title, text, sender, timeout, level}
MSG_MESSAGE_RESPONSE = "msg_send_res"     # {ok, message, shown}

MSG_LEVELS = ("info", "warn", "error")    # 弹窗级别（标题栏颜色不同）


def make_message_request(title: str, text: str, sender: str = "",
                         timeout: float = 8.0, level: str = "info") -> dict:
    """
    title:   弹窗标题
    text:    正文
    sender:  发送方（显示在弹窗右下角）
    timeout: 停留秒数，0 = 不自动消失（需手动点掉）
    level:   info(蓝) / warn(橙) / error(红)
    """
    if level not in MSG_LEVELS:
        level = "info"
    return {
        "type": MSG_MESSAGE_REQUEST,
        "title": title, "text": text, "sender": sender,
        "timeout": float(timeout or 0), "level": level,
    }


def make_message_response(ok: bool, message: str = "", shown: bool = False) -> dict:
    return {"type": MSG_MESSAGE_RESPONSE,
            "ok": bool(ok), "message": message, "shown": bool(shown)}


# ============ 发送命令（对话框方式发送，区别于命令栏直接执行） ============

MSG_RUNCMD_REQUEST = "runcmd_req"    # {cmd, timeout, notify, title}
MSG_RUNCMD_RESPONSE = "runcmd_res"   # {ok, output, exit_code, cwd, notified}


def make_runcmd_request(cmd: str, timeout: float = 0, notify: bool = False,
                        title: str = "") -> dict:
    """
    cmd:     要执行的命令
    timeout: 超时秒数（0 = 用被控端默认）
    notify:  执行完后是否也在被控端弹个通知
    title:   弹窗标题（notify=True 时有效）
    """
    return {
        "type": MSG_RUNCMD_REQUEST,
        "cmd": cmd, "timeout": float(timeout or 0),
        "notify": bool(notify), "title": title or "",
    }


def make_runcmd_response(ok: bool, output: str = "", exit_code: int = 0,
                         cwd: str = "", notified: bool = False) -> dict:
    return {"type": MSG_RUNCMD_RESPONSE,
            "ok": bool(ok), "output": output,
            "exit_code": int(exit_code), "cwd": cwd,
            "notified": bool(notified)}


# ============ 屏幕广播（主控端 → 所有被控端，直播式） ============
#
# 方向: 主控端(教师机)采集自己的屏幕 → 推给被控端(学生机)显示
# 与"屏幕监控"相反: 监控是控制端看被控端，广播是主控端给大家看。
#
# 流程:
#   1. 主控端启动 BroadcastServer(监听某端口)
#   2. 主控端给每个目标 agent 发 bc_start_req（带上自己的 host:port）
#   3. agent 收到后启动 BroadcastViewer 连上来，接收 bc_frame 显示
#   4. 主控端结束: 发 bc_quit 帧 + bc_stop_req → agent 关闭窗口
#
# 被控端窗口: 可调整大小，但【不能关闭】（拦截 WM_DELETE_WINDOW / Alt+F4），
#             只能由主控端结束广播。

MSG_BC_START_REQ = "bc_start_req"    # {host, port, title, fps, width}
MSG_BC_START_RES = "bc_start_res"    # {ok, message}
MSG_BC_STOP_REQ = "bc_stop_req"      # {}
MSG_BC_STOP_RES = "bc_stop_res"      # {ok, message}

# 广播流（服务端 → 客户端），走广播专用连接
MSG_BC_FRAME = "bc_frame"            # {w, h, data, seq}
MSG_BC_QUIT = "bc_quit"              # {}  服务端通知客户端结束


def make_bc_start_request(host: str, port: int, title: str = "屏幕广播",
                          fps: float = 8.0, width: int = 1280) -> dict:
    return {"type": MSG_BC_START_REQ, "host": host, "port": int(port),
            "title": title, "fps": float(fps), "width": int(width)}


def make_bc_start_response(ok: bool, message: str = "") -> dict:
    return {"type": MSG_BC_START_RES, "ok": bool(ok), "message": message}


def make_bc_stop_request() -> dict:
    return {"type": MSG_BC_STOP_REQ}


def make_bc_stop_response(ok: bool, message: str = "") -> dict:
    return {"type": MSG_BC_STOP_RES, "ok": bool(ok), "message": message}


def make_bc_frame(w: int, h: int, data_b64: str, seq: int = 0) -> dict:
    return {"type": MSG_BC_FRAME, "w": int(w), "h": int(h),
            "data": data_b64, "seq": int(seq)}


def make_bc_quit() -> dict:
    return {"type": MSG_BC_QUIT}


# 广播默认参数（可调）
BC_DEFAULT_FPS = 8.0        # 教学广播不需要 30FPS，省带宽
BC_DEFAULT_WIDTH = 1280     # 画面宽度上限（等比缩放）
BC_DEFAULT_QUALITY = 60     # JPEG 质量
BC_MAX_CLIENTS = 256        # 最多同时广播给多少台


def make_log_request(lines: int = 200) -> dict:
    return {"type": MSG_LOG_REQUEST, "lines": int(lines)}


def make_log_response(content: str, path: str = "") -> dict:
    return {"type": MSG_LOG_RESPONSE, "log": content, "path": path}


# ============ 通用 socket 工具（agent.py 依赖） ============

def make_udp_socket(ttl: int = 1):
    """创建用于发现/广播的 UDP socket"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL,
                     struct.pack("b", ttl))
    except Exception:
        pass
    return s


def recv_all(conn: socket.socket, timeout: float = 5.0) -> bytes:
    """
    读取一条完整消息: 4字节大端长度前缀 + 负载。
    （与 encode() 配套使用）
    """
    conn.settimeout(timeout)
    header = b""
    while len(header) < 4:
        chunk = conn.recv(4 - len(header))
        if not chunk:
            return b""
        header += chunk
    length = struct.unpack(">I", header)[0]
    payload = b""
    while len(payload) < length:
        chunk = conn.recv(length - len(payload))
        if not chunk:
            break
        payload += chunk
    return header + payload


def send_all(conn: socket.socket, data: bytes):
    """发送一条完整消息（conn 需已连接）"""
    conn.sendall(data)
