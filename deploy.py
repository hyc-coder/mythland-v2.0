"""
deploy.py - 一键部署（主控端）

作用: 把同目录下的被控端 exe（agent.exe / 被控端.exe）
     批量装到指定 IP 的电脑上并启动，全程通过外部工具 jcc.exe 完成远程执行。

jcc.exe 用法（用户提供）:
    jcc.exe -ip [ip] -c [command]
    [ip] 可以是:
        单个 IP   192.168.80.12
        IP 范围   192.168.80.10-56

部署思路（jcc.exe 只能执行命令，不能直接传文件）:
    1. 主控端在本机起一个【临时 HTTP 服务】，只对外提供那一个 exe 文件
    2. 用 jcc.exe 让目标机执行命令，把 exe 从主控端 HTTP 拉下来（certutil / powershell）
    3. 再用 jcc.exe 让目标机启动它（start / powershell Start-Process）

这样不需要开 SMB 共享、不需要目标机开共享目录，只要能 HTTP 通 + jcc 能执行即可。

用法:
    from deploy import Deployer, parse_ip_spec
    ips = parse_ip_spec("192.168.80.10-56, 192.168.80.100")
    d = Deployer(exe_path="agent.exe", jcc_path="jcc.exe")
    port = d.start_http()                       # 起临时 HTTP
    results = d.deploy_all(ips, on_progress=fn) # 批量部署
    d.stop_http()

设计要点:
  - 并发部署（默认 10 线程），一台失败不影响其它
  - 每步单独执行（建目录 / 下载 / 启动），进度可见、便于排查
  - 全程可取消（stop_event）
  - jcc.exe 不存在 / exe 不存在，都要给出明确提示，而不是默默失败
"""

import os
import platform
import queue
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

IS_WINDOWS = platform.system() == "Windows"

# ---- 默认配置 ----
DEFAULT_REMOTE_DIR = r"C:\ProgramData\RemoteAgent"
DEFAULT_TARGET_NAME = "agent.exe"
DEFAULT_TIMEOUT = 60          # 单条命令超时（秒）
DEFAULT_WORKERS = 10          # 并发数

# jcc.exe 可能的名字（Windows 上带 .exe，其它平台也尝试同名）
JCC_CANDIDATES = ["jcc.exe", "jcc"] if IS_WINDOWS else ["jcc.exe", "jcc", "jcc.sh"]

# 被控端 exe 的候选名（按优先级）
AGENT_CANDIDATES = [
    "agent.exe", "被控端.exe", "agent.py",
] if IS_WINDOWS else ["agent.exe", "被控端.exe"]


def get_local_ip(target: str = "8.8.8.8") -> str:
    """本机局域网 IP（借路由表判断出口网卡，不真发包）"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect((target, 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def local_subnet_prefix() -> str:
    """本机网段前缀，如 '192.168.80.'（给 UI 做默认值）"""
    ip = get_local_ip()
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3]) + "."
    return "192.168.1."


# ============================================================
# IP 解析
# ============================================================

_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _valid_octet(n: int) -> bool:
    return 0 <= n <= 255


def parse_ip_spec(spec: str) -> tuple[list[str], list[str]]:
    """
    解析 IP 规格，支持:
        192.168.80.12              单个
        192.168.80.10-56           范围（简写，最后一段）
        192.168.80.10-192.168.80.56  范围（全写）
        多个用 逗号 / 分号 / 换行 / 空格 分隔

    返回 (ip_list, error_list)
    """
    if not spec or not spec.strip():
        return [], []

    # 统一分隔符
    raw = re.split(r"[,\s;]+", spec.strip())
    ips, errors = [], []
    seen = set()

    for token in raw:
        token = token.strip()
        if not token:
            continue

        try:
            expanded = _expand_one(token)
        except ValueError as e:
            errors.append(str(e))
            continue

        for ip in expanded:
            if ip not in seen:
                seen.add(ip)
                ips.append(ip)

    return ips, errors


def _expand_one(token: str) -> list[str]:
    """展开一个 token（单个 IP 或范围）"""
    if "-" not in token:
        if not _IP_RE.match(token):
            raise ValueError(f"不是合法 IP: {token}")
        if not all(_valid_octet(int(x)) for x in token.split(".")):
            raise ValueError(f"IP 段超出范围: {token}")
        return [token]

    # 含 '-'
    left, right = token.split("-", 1)
    left, right = left.strip(), right.strip()

    # 形式 A: 192.168.80.10-192.168.80.56
    if _IP_RE.match(left) and _IP_RE.match(right):
        a = [int(x) for x in left.split(".")]
        b = [int(x) for x in right.split(".")]
        if a[:3] != b[:3]:
            raise ValueError(f"范围必须同网段: {token}")
        lo, hi = a[3], b[3]
    # 形式 B: 192.168.80.10-56
    else:
        m = re.match(r"^(\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d{1,3})$", left)
        if not m:
            raise ValueError(f"无法解析范围: {token}")
        prefix = m.group(1)
        if not all(_valid_octet(int(x)) for x in prefix.split(".")):
            raise ValueError(f"网段不合法: {token}")
        lo = int(m.group(2))
        if not re.match(r"^\d{1,3}$", right):
            raise ValueError(f"范围结束值不合法: {token}")
        hi = int(right)
        # 校验完整 IP 合法性
        for n in (lo, hi):
            if not _valid_octet(n):
                raise ValueError(f"IP 段超出范围: {token}")

    if lo > hi:
        lo, hi = hi, lo
    if hi - lo > 1000:
        raise ValueError(f"范围过大（{hi - lo + 1} 个），请缩小: {token}")

    base = left.rsplit(".", 1)[0] if _IP_RE.match(left) else \
        re.match(r"^(\d{1,3}\.\d{1,3}\.\d{1,3})\.", left).group(1)
    return [f"{base}.{n}" for n in range(lo, hi + 1)]


# ============================================================
# 临时 HTTP 服务（只提供一个文件）
# ============================================================

class _SingleFileHandler:
    """极简 HTTP 处理器：只响应指定文件，其它一律 404"""

    def __init__(self, file_path: str, serve_name: str):
        self.file_path = file_path
        self.serve_name = serve_name


def _make_server(file_path: str, serve_name: str, port: int = 0):
    """
    起一个只提供单个文件的 HTTP 服务。
    返回 (httpd, actual_port)
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    size = os.path.getsize(file_path)
    holder = {"path": file_path, "name": serve_name}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass          # 静默，别把日志刷满

        def _send(self, body: bool):
            # 只认文件名，路径无关的其它请求一律 404
            req = self.path.split("?")[0].lstrip("/")
            if req != holder["name"]:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            if body:
                try:
                    with open(holder["path"], "rb") as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                except Exception:
                    pass

        def do_GET(self):
            self._send(True)

        def do_HEAD(self):
            self._send(False)

    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    return httpd, httpd.server_address[1]


# ============================================================
# 部署器
# ============================================================

class DeployResult:
    """一台机器的部署结果"""

    def __init__(self, ip: str):
        self.ip = ip
        self.ok = False
        self.stage = "待部署"        # 待部署/建目录/下载/启动/完成/失败/取消
        self.detail = ""
        self.steps: list[tuple[str, bool, str]] = []   # (阶段, 成功, 输出)

    def __repr__(self):
        return f"<DeployResult {self.ip} ok={self.ok} stage={self.stage}>"


class Deployer:
    """
    一键部署器

    典型流程:
        d = Deployer(exe_path, jcc_path)
        d.start_http()
        for r in d.deploy_all(ips, on_progress=cb): ...
        d.stop_http()
    """

    def __init__(self, exe_path: str, jcc_path: str | None = None,
                 remote_dir: str = DEFAULT_REMOTE_DIR,
                 target_name: str = DEFAULT_TARGET_NAME,
                 timeout: float = DEFAULT_TIMEOUT,
                 workers: int = DEFAULT_WORKERS,
                 auto_start: bool = True):
        self.exe_path = exe_path
        self.jcc_path = jcc_path or self.find_jcc(exe_path)
        self.remote_dir = remote_dir.rstrip("\\").rstrip("/")
        self.target_name = target_name
        self.timeout = float(timeout)
        self.workers = max(1, int(workers))
        self.auto_start = auto_start

        self.httpd = None
        self.http_port = 0
        self.http_url = ""
        self._progress_q: queue.Queue = queue.Queue()
        self._stop = threading.Event()

    # ---- 查找文件 ----

    @staticmethod
    def find_jcc(near_path: str = "") -> str | None:
        """在 exe 同目录 / 当前目录找 jcc.exe"""
        dirs = []
        if near_path:
            dirs.append(os.path.dirname(os.path.abspath(near_path)))
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
        dirs.append(os.getcwd())
        for d in dirs:
            for name in JCC_CANDIDATES:
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    return p
        return None

    @staticmethod
    def find_agent_exe(near_path: str = "") -> str | None:
        """找被控端 exe"""
        dirs = []
        if near_path:
            dirs.append(os.path.dirname(os.path.abspath(near_path)))
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
        dirs.append(os.getcwd())
        for d in dirs:
            for name in AGENT_CANDIDATES:
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    return p
        return None

    # ---- HTTP ----

    def start_http(self) -> str:
        """起临时 HTTP 服务，返回可下载 URL"""
        if not self.exe_path or not os.path.isfile(self.exe_path):
            raise FileNotFoundError(f"找不到要部署的文件: {self.exe_path}")

        self.httpd, self.http_port = _make_server(
            self.exe_path, self.target_name, port=0)
        threading.Thread(target=self.httpd.serve_forever,
                         daemon=True, name="部署HTTP").start()
        host = get_local_ip()
        self.http_url = f"http://{host}:{self.http_port}/{self.target_name}"
        print(f"[部署] HTTP 服务已启动: {self.http_url}")
        return self.http_url

    def stop_http(self):
        try:
            if self.httpd:
                self.httpd.shutdown()
                self.httpd.server_close()
        except Exception:
            pass
        self.httpd = None
        print("[部署] HTTP 服务已停止")

    # ---- jcc ----

    def run_jcc(self, ip: str, command: str) -> tuple[bool, str]:
        """
        调 jcc.exe 在指定 IP 执行命令。
        返回 (ok, output)
        """
        if not self.jcc_path or not os.path.isfile(self.jcc_path):
            return False, f"找不到 jcc.exe（期望在同目录: {self.jcc_path}）"

        cmd = [self.jcc_path, "-ip", ip, "-c", command]
        creationflags = 0
        if IS_WINDOWS:
            try:
                creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore
            except Exception:
                creationflags = 0

        try:
            p = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.timeout,
                creationflags=creationflags,
                cwd=os.path.dirname(os.path.abspath(self.jcc_path)) or None,
            )
        except subprocess.TimeoutExpired:
            return False, f"超时（>{self.timeout:.0f}s）"
        except FileNotFoundError:
            return False, f"无法执行 jcc: {self.jcc_path}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

        enc = "gbk" if IS_WINDOWS else "utf-8"
        out = (p.stdout or b"").decode(enc, errors="replace")
        err = (p.stderr or b"").decode(enc, errors="replace")
        text = (out + ("\n" + err if err.strip() else "")).strip()
        # 成功判定: 退出码 0。jcc 输出格式未知，故不做关键字匹配。
        return (p.returncode == 0), (text or f"(无输出，退出码 {p.returncode})")

    # ---- 命令拼装 ----

    def remote_path(self) -> str:
        return f"{self.remote_dir}\\{self.target_name}"

    def build_steps(self) -> list[tuple[str, str]]:
        """
        返回 [(阶段名, 命令), ...]
        拆成多步是为了进度可见、便于排查（哪一步失败一目了然）。
        """
        rp = self.remote_path()
        url = self.http_url
        steps = [
            ("建目录", f'mkdir "{self.remote_dir}" 2>nul & echo OK'),
            # certutil 是 Win7+ 自带的下载工具，无需额外依赖
            ("下载", f'certutil -urlcache -split -f "{url}" "{rp}"'),
        ]
        if self.auto_start:
            steps.append(("启动", f'start "" "{rp}"'))
        return steps

    # ---- 单台部署 ----

    def deploy_one(self, ip: str) -> DeployResult:
        r = DeployResult(ip)
        self._emit(r)

        for stage, command in self.build_steps():
            if self._stop.is_set():
                r.stage = "取消"
                r.detail = "已取消"
                self._emit(r)
                return r

            r.stage = stage
            self._emit(r)

            # 命令里的占位符（便于自定义模板）
            cmd = (command
                   .replace("{url}", self.http_url)
                   .replace("{path}", self.remote_path())
                   .replace("{dir}", self.remote_dir)
                   .replace("{ip}", ip))

            ok, out = self.run_jcc(ip, cmd)
            r.steps.append((stage, ok, out))

            if not ok:
                r.stage = "失败"
                r.detail = f"{stage}失败: {out[:200]}"
                self._emit(r)
                return r

        r.ok = True
        r.stage = "完成"
        r.detail = "已部署" + ("并启动" if self.auto_start else "")
        self._emit(r)
        return r

    def _emit(self, r: DeployResult):
        """把进度放进队列（线程安全，UI 侧去取）"""
        try:
            self._progress_q.put_nowait(r)
        except Exception:
            pass

    def drain_progress(self) -> list[DeployResult]:
        """取出当前所有进度（UI 线程调用）"""
        out = []
        while True:
            try:
                out.append(self._progress_q.get_nowait())
            except queue.Empty:
                break
        return out

    # ---- 批量 ----

    def deploy_all(self, ips: list[str], on_progress=None) -> list[DeployResult]:
        """
        批量部署。on_progress(DeployResult) 会在【部署线程】里被调用，
        注意不要在回调里直接操作 Tk（用 after 转主线程）。
        """
        self._stop.clear()
        results = [DeployResult(ip) for ip in ips]

        def work(r: DeployResult) -> DeployResult:
            got = self.deploy_one(r.ip)
            if on_progress:
                try:
                    on_progress(got)
                except Exception:
                    pass
            return got

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            results = list(ex.map(work, results))

        return results

    def cancel(self):
        self._stop.set()


def summarize(results: list[DeployResult]) -> str:
    """结果汇总文案"""
    total = len(results)
    ok = sum(1 for r in results if r.ok)
    fail = [r for r in results if not r.ok and r.stage != "取消"]
    cancel = [r for r in results if r.stage == "取消"]
    lines = [f"总计 {total} 台：成功 {ok}，失败 {len(fail)}"
             + (f"，取消 {len(cancel)}" if cancel else "")]
    if fail:
        lines.append("")
        lines.append("失败明细（最多显示 10 条）:")
        for r in fail[:10]:
            lines.append(f"  {r.ip}  {r.stage}  {r.detail[:80]}")
    return "\n".join(lines)
