"""
process_mgr.py - 被控端进程管理（被控端 agent 使用）

依赖优先级:
  1. psutil  —— 信息最全（CPU / 内存 / 状态 / 路径），pip install psutil
  2. tasklist —— Windows 自带（只有 PID / 名称 / 内存）
  3. ps       —— Linux / macOS 自带
  都没有 → 返回空列表（界面提示"无法采集"）

用法:
    from process_mgr import get_process_list, kill_process
    procs, backend = get_process_list()
    ok, msg = kill_process(1234, force=False)
"""

import os
import platform
import subprocess

PSUTIL = None
try:
    import psutil
    PSUTIL = psutil
except Exception:
    psutil = None

IS_WINDOWS = platform.system() == "Windows"


def get_backend() -> str:
    """当前实际可用的采集方式"""
    if PSUTIL is not None:
        return "psutil"
    if IS_WINDOWS:
        return "tasklist"
    return "ps"


# ---------- 采集进程列表 ----------

def get_process_list():
    """
    返回 (procs, backend)
    procs: [{pid, name, cpu, mem, status, exe}, ...]
      cpu:  CPU 占用百分比（float，psutil 才有，其它为 0.0）
      mem:  内存占用 MB（float）
      exe:  可执行文件路径（可能为空）
    """
    if PSUTIL is not None:
        try:
            return _list_psutil(), "psutil"
        except Exception as e:
            print(f"[进程] psutil 采集失败，降级: {e}")

    if IS_WINDOWS:
        try:
            return _list_tasklist(), "tasklist"
        except Exception as e:
            print(f"[进程] tasklist 采集失败: {e}")
            return [], "none"

    try:
        return _list_ps(), "ps"
    except Exception as e:
        print(f"[进程] ps 采集失败: {e}")
        return [], "none"


def _list_psutil():
    procs = []
    # 先取一次 CPU，隔一下再取才能算出百分比
    for p in psutil.process_iter(["pid", "name", "status", "exe", "memory_info"]):
        try:
            info = p.info
            mem = 0.0
            mi = info.get("memory_info")
            if mi is not None:
                mem = round(mi.rss / 1024 / 1024, 1)     # 字节 → MB
            procs.append({
                "pid": int(info.get("pid") or 0),
                "name": info.get("name") or "?",
                "cpu": 0.0,
                "mem": mem,
                "status": info.get("status") or "?",
                "exe": info.get("exe") or "",
            })
        except Exception:
            continue

    # 二次采样算 CPU（需要短暂间隔）
    try:
        cpu_map = {}
        for p in psutil.process_iter(["pid"]):
            try:
                p.cpu_percent(None)
            except Exception:
                pass
        import time as _t
        _t.sleep(0.15)
        for p in psutil.process_iter(["pid"]):
            try:
                cpu_map[p.info["pid"]] = p.cpu_percent(None) or 0.0
            except Exception:
                pass
        for item in procs:
            item["cpu"] = round(cpu_map.get(item["pid"], 0.0), 1)
    except Exception:
        pass

    return procs


def _list_tasklist():
    """Windows: tasklist /FO CSV /NH"""
    out = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        capture_output=True, timeout=20,
        creationflags=_no_window(),
    )
    text = out.stdout.decode("gbk", errors="replace") or out.stdout.decode("utf-8", errors="replace")

    procs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('"') is False:
            continue
        # CSV: "name","pid","session","session#","mem K"
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) < 5:
            continue
        name, pid_s, _sess, _sessn, mem_s = parts[0], parts[1], parts[2], parts[3], parts[4]
        try:
            pid = int(pid_s)
        except Exception:
            continue
        # 内存形如 "1,234 K"
        mem = 0.0
        try:
            mem_kb = float(mem_s.replace("K", "").replace(",", "").replace(" ", "").strip() or 0)
            mem = round(mem_kb / 1024, 1)
        except Exception:
            pass
        procs.append({
            "pid": pid, "name": name, "cpu": 0.0,
            "mem": mem, "status": "running", "exe": "",
        })
    return procs


def _list_ps():
    """Linux / macOS: ps 命令"""
    out = subprocess.run(
        ["ps", "-eo", "pid,comm,pcpu,pmem,stat"],
        capture_output=True, timeout=20,
    )
    text = out.stdout.decode("utf-8", errors="replace")
    procs = []
    for line in text.splitlines()[1:]:          # 跳过表头
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        try:
            procs.append({
                "pid": int(parts[0]),
                "name": parts[1],
                "cpu": float(parts[2]),
                "mem": 0.0,              # pmem 是百分比，需总内存换算，这里省略
                "status": parts[4],
                "exe": "",
            })
        except Exception:
            continue
    return procs


# ---------- 结束进程 ----------

def kill_process(pid: int, force: bool = False):
    """
    结束进程，返回 (ok: bool, message: str)

    force=False → 优雅退出（SIGTERM / taskkill 不带 /F）
    force=True  → 强制结束（SIGKILL / taskkill /F）
    """
    if pid <= 0:
        return False, "无效的 PID"
    if pid == os.getpid():
        return False, "不能结束被控端自身进程（会导致掉线）"

    # 保护：绝不结束系统关键进程
    GUARD = {0, 4}
    if pid in GUARD:
        return False, f"PID {pid} 是系统核心进程，已拒绝结束"

    if PSUTIL is not None:
        try:
            p = psutil.Process(pid)
            name = p.name()
            if force:
                p.kill()          # SIGKILL
            else:
                p.terminate()     # SIGTERM
            return True, f"已结束 {name} (PID {pid})"
        except psutil.NoSuchProcess:
            return False, f"进程 {pid} 不存在或已退出"
        except psutil.AccessDenied:
            return False, f"权限不足，无法结束 {pid}（试试强制结束）"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    # 无 psutil：用系统命令
    if IS_WINDOWS:
        cmd = ["taskkill", "/PID", str(pid)]
        if force:
            cmd.append("/F")
        cmd.append("/T")      # 连同子进程
    else:
        cmd = ["kill", "-9" if force else "-15", str(pid)]

    try:
        r = subprocess.run(cmd, capture_output=True, timeout=15,
                           creationflags=_no_window())
        if r.returncode == 0:
            return True, f"已结束 PID {pid}"
        err = (r.stderr or b"").decode("utf-8", errors="replace").strip()
        err = (r.stdout or b"").decode("utf-8", errors="replace").strip() or err
        return False, err or f"taskkill 返回 {r.returncode}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _no_window():
    """Windows 下隐藏子进程窗口（被控端静默运行必需）"""
    if not IS_WINDOWS:
        return 0
    try:
        return subprocess.CREATE_NO_WINDOW      # type: ignore[attr-defined]
    except Exception:
        return 0
