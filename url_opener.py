"""
url_opener.py - 在被控端打开网址（被控端 agent 使用）

打开策略（依次尝试，第一个成功即返回）:
  1. 指定浏览器（控制端传了 browser 参数时）: chrome / edge / firefox / ie
  2. webbrowser 模块（系统默认浏览器）
  3. 系统命令兜底:
       Windows → start "" "url"
       macOS   → open "url"
       Linux   → xdg-open "url"

安全:
  - 只接受 http / https / ftp / mailto / file 协议，拒绝 javascript: 等危险 scheme
  - URL 不再拼进 shell 字符串，一律走参数列表传参，避免命令注入
  - 无协议前缀时自动补 https://

用法:
    from url_opener import open_url
    ok, msg, browser = open_url("https://example.com")
    ok, msg, browser = open_url("https://example.com", browser="chrome")
"""

import os
import platform
import shutil
import subprocess
import webbrowser

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"

# 允许的协议白名单（防 javascript: / data: 等）
ALLOWED_SCHEMES = ("http://", "https://", "ftp://", "mailto:", "file://")

# 浏览器名 → (Windows 常见路径, macOS 路径, Linux 可执行名)
BROWSERS = {
    "chrome": (
        [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
         r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ["google-chrome", "chromium", "chromium-browser"],
    ),
    "edge": (
        [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ["microsoft-edge", "microsoft-edge-stable"],
    ),
    "firefox": (
        [r"C:\Program Files\Mozilla Firefox\firefox.exe",
         r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"],
        "/Applications/Firefox.app/Contents/MacOS/firefox",
        ["firefox"],
    ),
    "ie": (
        [r"C:\Program Files\Internet Explorer\iexplore.exe",
         r"C:\Program Files (x86)\Internet Explorer\iexplore.exe"],
        "",
        [],
    ),
}


def normalize_url(url: str) -> str:
    """
    去空白；没写协议时补 https://

    关键: 必须先把【带 scheme 但不在白名单】的（javascript: / data: 等）认出来并原样返回，
    让后面的 is_safe_url 去拒绝。否则会被误当成域名补成 https:// ，
    既掩盖了危险意图，又可能生成诡异的 URL。
    """
    u = (url or "").strip()
    if not u:
        return ""
    low = u.lower()

    # 1. 已在白名单 → 原样（http/https/ftp/mailto/file）
    if any(low.startswith(s) for s in ALLOWED_SCHEMES):
        return u

    # 2. 有 scheme 标记 → 原样返回，交给 is_safe_url 拒绝
    #    - 含 "://"                    例: javascript://x
    #    - 已知危险/特殊 scheme 前缀   例: data:text/html, javascript:alert(1)
    if "://" in low:
        return u
    for bad in ("javascript:", "data:", "vbscript:", "about:",
                "chrome:", "view-source:", "blob:"):
        if low.startswith(bad):
            return u

    # 3. 其余当域名处理，补 https://
    #    例: www.baidu.com → https://www.baidu.com
    #        www.a.com:8080 → https://www.a.com:8080（端口是合法的）
    return "https://" + u


def is_safe_url(url: str) -> bool:
    """协议白名单校验"""
    low = (url or "").strip().lower()
    if not low:
        return False
    return any(low.startswith(s) for s in ALLOWED_SCHEMES)


def _find_browser(name: str) -> str:
    """按浏览器名找可执行文件路径，找不到返回空串"""
    key = (name or "").strip().lower()
    if key not in BROWSERS:
        return ""
    win_paths, mac_path, linux_names = BROWSERS[key]

    if IS_WINDOWS:
        for p in win_paths:
            if os.path.exists(p):
                return p
        # 也从 PATH 里找
        found = shutil.which(key) or shutil.which(key + ".exe")
        return found or ""
    if IS_MAC:
        return mac_path if os.path.exists(mac_path) else ""
    for n in linux_names:
        found = shutil.which(n)
        if found:
            return found
    return ""


def _no_window_flags():
    """Windows 下不弹子进程窗口"""
    if not IS_WINDOWS:
        return 0
    try:
        return subprocess.CREATE_NO_WINDOW      # type: ignore[attr-defined]
    except Exception:
        return 0


def _silent(func):
    """
    执行 func 期间抑制【本进程】的 stdout/stderr。

    用途: webbrowser / xdg-open 这类在找不到浏览器时会往控制台喷一堆
    "xxx: not found"，被控端是静默运行的，这些输出会全部落进 agent.log，
    把真正的业务日志淹掉。
    """
    import sys
    import io as _io

    saved_out, saved_err = sys.stdout, sys.stderr
    devnull = _io.StringIO()
    try:
        sys.stdout, sys.stderr = devnull, devnull
        return func()
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err


def _run(cmd: list) -> bool:
    """执行一条命令（列表形式，不经 shell，避免注入）"""
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_no_window_flags(),
            close_fds=not IS_WINDOWS,
        )
        return True
    except Exception:
        return False


def open_url(url: str, browser: str = ""):
    """
    在被控端打开网址。
    返回 (ok: bool, message: str, used_browser: str)
    """
    u = normalize_url(url)
    if not u:
        return False, "网址为空", ""
    if not is_safe_url(u):
        return False, (
            f"不支持的协议，已拒绝: {url}\n"
            f"仅允许: {', '.join(ALLOWED_SCHEMES)}"
        ), ""

    # ---- 1. 指定浏览器 ----
    if browser:
        exe = _find_browser(browser)
        if exe:
            if IS_MAC and exe.endswith(".app"):
                # macOS .app 用 open -a
                if _run(["open", "-a", exe, u]):
                    return True, f"已用 {browser} 打开: {u}", browser
            elif _run([exe, u]):
                return True, f"已用 {browser} 打开: {u}", browser
            return False, f"找到了 {browser} 但启动失败: {exe}", browser
        return False, (
            f"未在本机找到浏览器 '{browser}'。\n"
            f"可选: {', '.join(BROWSERS.keys())}，或留空用默认浏览器。"
        ), browser

    # ---- 2. webbrowser 模块（系统默认） ----
    try:
        # webbrowser.open 返回 True 只代表"已启动打开动作"，
        # 不代表网页真的打开了（比如被控端没装浏览器也会返回 True）。
        # 同时抑制它内部子进程(xdg-open 等)往被控端日志里喷错误。
        ok = _silent(lambda: webbrowser.open(u, new=2, autoraise=True))
        if ok:
            return True, f"已请求默认浏览器打开: {u}", "默认浏览器"
    except Exception as e:
        print(f"[URL] webbrowser 失败: {e}")

    # ---- 3. 系统命令兜底 ----
    if IS_WINDOWS:
        # start 是 cmd 内建命令，必须走 shell；URL 用双引号包起来
        try:
            subprocess.Popen(
                f'start "" "{u}"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_no_window_flags(),
            )
            return True, f"已打开（系统命令）: {u}", "默认浏览器"
        except Exception as e:
            return False, f"打开失败: {type(e).__name__}: {e}", ""
    elif IS_MAC:
        if _run(["open", u]):
            return True, f"已打开（open 命令）: {u}", "默认浏览器"
    else:
        for opener in ("xdg-open", "x-www-browser", "gnome-open"):
            if shutil.which(opener):
                if _run([opener, u]):
                    return True, f"已打开（{opener}）: {u}", "默认浏览器"

    return False, (
        f"打开失败: {u}\n"
        f"本机可能没有可用的浏览器，或未安装 xdg-open。"
    ), ""


def list_browsers() -> list:
    """
    列出本机可用的浏览器（给控制端下拉框用）。
    返回 [("默认浏览器", ""), ("chrome", "chrome"), ...] 只包含装了的。
    """
    result = [("默认浏览器", "")]
    for name in BROWSERS:
        if _find_browser(name):
            result.append((name.capitalize(), name))
    return result
