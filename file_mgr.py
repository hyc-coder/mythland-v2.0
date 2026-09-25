"""
file_mgr.py - 被控端文件操作（被控端 agent 使用）

功能: 列目录 / 读文件分块(下载) / 写文件分块(上传) / 新建文件夹 / 删除

安全策略（Windows 系统目录写保护）:
  - 默认【开启】保护
  - 保护范围: 仅 Windows 下的 C:\\Windows（含子目录）。Linux / macOS 不保护。
  - 保护内容: 禁止一切【更改】操作 —— 删除 / 上传 / 新建文件夹
  - 允许: 浏览目录、下载文件（只读操作一律放行）

  临时关闭: 控制端「执行命令」栏输入 SAFE_MODE_OFF
  重新开启: 输入 SAFE_MODE_ON
  （仅对当前被控端进程生效，重启被控端后恢复默认开启）

  无论开关如何，以下【功能性校验】始终保留（不是安全限制，是操作本身要求）:
    - 路径不存在、不是目录、是目录不能当文件下载 → 返回明确错误
    - 上传文件名只取 basename，避免文件名里带路径写到意外位置

用法:
    from file_mgr import list_dir, read_chunk, FileUploader, make_dir, delete_path
"""

import os
import platform
import time

IS_WINDOWS = platform.system() == "Windows"

# ============ 安全模式（Windows 系统目录写保护） ============
#
# SAFE_MODE: 默认开关。True = 开启保护（默认）
# _safe_off : 运行时临时关闭标志，由控制端命令 SAFE_MODE_OFF / SAFE_MODE_ON 切换
#             （只影响当前被控端进程，重启后回到 SAFE_MODE 的值）
#
# 保护范围: 仅 Windows 的 C:\Windows（含子目录）
# 保护内容: 禁止一切【更改】—— 删除 / 上传 / 新建文件夹
# 放行:     浏览目录、下载文件（只读）
SAFE_MODE = True
_safe_off = False

# 受保护的目录（只在 Windows 下生效，比较时统一小写）
PROTECTED_DIR = "c:\\windows"


def set_safe_mode(enabled: bool):
    """
    运行时切换保护（临时生效，不写文件，重启被控端后恢复 SAFE_MODE 默认值）。
    set_safe_mode(False) → 关闭保护
    set_safe_mode(True)  → 开启保护
    """
    global _safe_off
    _safe_off = not bool(enabled)


def safe_enabled() -> bool:
    """当前保护是否生效"""
    return bool(SAFE_MODE) and not _safe_off


def safe_status() -> str:
    """给控制端显示的状态文本"""
    if not IS_WINDOWS:
        return "保护未启用（仅 Windows 生效）"
    return "保护已开启" if safe_enabled() else "保护已临时关闭"


# ---------- 路径处理 ----------

def default_root() -> str:
    """默认根目录：用户 home（避免一上来就暴露整个磁盘）"""
    try:
        return os.path.expanduser("~")
    except Exception:
        return "/" if not IS_WINDOWS else "C:\\"


def list_roots() -> list:
    """
    Windows: 返回可用盘符列表 [C:\\, D:\\, ...]
    Linux/Mac: 返回 [/
    """
    if not IS_WINDOWS:
        return ["/"]

    roots = []
    for c in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        p = f"{c}:\\"
        try:
            if os.path.exists(p):
                roots.append(p)
        except Exception:
            pass
    return roots or ["C:\\"]


def normalize(path: str) -> str:
    """规范化路径（消除 .. 和 . ）"""
    if not path:
        return default_root()
    try:
        return os.path.normpath(os.path.abspath(path))
    except Exception:
        return path


def is_protected(path: str) -> bool:
    """
    该路径是否受【写保护】（禁止删除 / 上传 / 新建）。

    条件（三条全满足才保护）:
      1. 保护开关处于开启状态（默认开；SAFE_MODE_OFF 可临时关）
      2. 当前系统是 Windows（Linux / macOS 不保护）
      3. 路径位于 C:\\Windows 之内（含 C:\\Windows 本身及所有子目录）

    只读操作（列目录、下载）一律不拦截 —— 见 list_dir / read_chunk。
    """
    if not safe_enabled():
        return False
    if not IS_WINDOWS:
        return False

    try:
        p = normalize(path).lower()
    except Exception:
        return False
    return p == PROTECTED_DIR or p.startswith(PROTECTED_DIR + "\\")


# 兼容旧名（内部/外部若仍调用 is_forbidden，等价于写保护判断）
is_forbidden = is_protected


# ---------- 列目录 ----------

def list_dir(path: str = ""):
    """
    返回 (path, parent, entries, error)
    entries: [{name, path, is_dir, size, mtime}, ...]
      目录排前面，再按名称排序
    path 为空 或 是盘符根且系统为Windows无此路径 → 返回盘符列表(虚拟目录)
    """
    if not path:
        # 顶层：返回盘符列表
        entries = []
        for r in list_roots():
            entries.append({
                "name": r, "path": r, "is_dir": True,
                "size": 0, "mtime": "", "virtual": True,
            })
        return "", "", entries, ""

    p = normalize(path)

    if not os.path.exists(p):
        return p, "", [], f"路径不存在: {p}"
    if not os.path.isdir(p):
        return p, "", [], f"不是目录: {p}"
    # 浏览是只读操作，即使受保护也可以看（保护只拦"改"）

    entries = []
    try:
        for name in os.listdir(p):
            fp = os.path.join(p, name)
            try:
                st = os.stat(fp)
                is_dir = os.path.isdir(fp)
                entries.append({
                    "name": name,
                    "path": fp,
                    "is_dir": is_dir,
                    "size": 0 if is_dir else st.st_size,
                    "mtime": time.strftime("%Y-%m-%d %H:%M",
                                           time.localtime(st.st_mtime)),
                })
            except Exception:
                # 无权限/损坏的文件也列出来，只是信息不全
                entries.append({
                    "name": name, "path": fp,
                    "is_dir": False, "size": 0, "mtime": "",
                })
    except Exception as e:
        return p, "", [], f"读取失败: {type(e).__name__}: {e}"

    # 目录优先，再按名称（忽略大小写）
    entries.sort(key=lambda x: (not x.get("is_dir"), x.get("name", "").lower()))

    parent = ""
    try:
        parent = os.path.dirname(p)
        if parent == p:      # 已经是根
            parent = ""
    except Exception:
        parent = ""

    return p, parent, entries, ""


# ---------- 读文件（下载用） ----------

def read_chunk(path: str, offset: int = 0, size: int = 256 * 1024):
    """
    读取文件的一个分块。
    返回 (data_bytes, total_size, eof, error)
    """
    p = normalize(path)
    if not os.path.exists(p):
        return b"", 0, True, f"文件不存在: {p}"
    if os.path.isdir(p):
        return b"", 0, True, f"是目录，不能下载: {p}"
    # 下载是只读操作，受保护目录也允许下载（保护只拦"改"）

    try:
        total = os.path.getsize(p)
        with open(p, "rb") as f:
            f.seek(offset)
            data = f.read(size)
        eof = (offset + len(data)) >= total
        return data, total, eof, ""
    except Exception as e:
        return b"", 0, True, f"读取失败: {type(e).__name__}: {e}"


# ---------- 写文件（上传用） ----------

class FileUploader:
    """
    接收分块写入文件。
    用法:
        up = FileUploader()
        up.begin(dir_path, name, size)
        for chunk in chunks: up.write(chunk)
        ok, msg, path = up.end()
    """

    def __init__(self):
        self._f = None
        self._path = ""
        self._size = 0
        self._written = 0

    def begin(self, dir_path: str, name: str, size: int = 0):
        d = normalize(dir_path) if dir_path else default_root()
        # 保护检查放最前（理由同 delete_path）
        if is_protected(d):
            return False, (f"受保护目录，禁止上传: {d}\n"
                           f"（C:\\Windows 已开启写保护；"
                           f"需临时关闭请在命令栏输入 SAFE_MODE_OFF）")
        if not os.path.isdir(d):
            return False, f"目标目录不存在: {d}"

        # 防止路径穿越：只取文件名部分
        safe_name = os.path.basename(name)
        if not safe_name:
            return False, "无效的文件名"

        self._path = os.path.join(d, safe_name)
        self._size = size
        self._written = 0
        try:
            self._f = open(self._path, "wb")
            return True, ""
        except Exception as e:
            return False, f"无法创建文件: {type(e).__name__}: {e}"

    def write(self, data: bytes):
        if self._f is None:
            return False, "未开始上传"
        try:
            self._f.write(data)
            self._written += len(data)
            return True, ""
        except Exception as e:
            return False, f"写入失败: {type(e).__name__}: {e}"

    def end(self):
        if self._f is None:
            return False, "未开始上传", ""
        try:
            self._f.close()
            self._f = None
            return True, f"已保存 {self._written} 字节", self._path
        except Exception as e:
            return False, f"关闭文件失败: {e}", self._path

    def abort(self):
        try:
            if self._f:
                self._f.close()
        except Exception:
            pass
        self._f = None


# ---------- 新建文件夹 / 删除 ----------

def make_dir(path: str):
    p = normalize(path)
    if is_protected(p):
        return False, (f"受保护目录，禁止新建文件夹: {p}\n"
                       f"（C:\\Windows 已开启写保护；"
                       f"需临时关闭请在命令栏输入 SAFE_MODE_OFF）")
    if os.path.exists(p):
        return False, f"已存在: {p}"
    try:
        os.makedirs(p, exist_ok=True)
        return True, f"已创建文件夹: {os.path.basename(p)}"
    except Exception as e:
        return False, f"创建失败: {type(e).__name__}: {e}"


def delete_path(path: str):
    """
    删除文件或文件夹（含非空目录）。
    SAFE_MODE=False 时不限制路径，系统目录也可删 —— 依赖还原保护兜底。
    """
    p = normalize(path)
    # 保护检查放在最前面 —— 沙盒/非Windows下路径可能"不存在"，
    # 但那不应掩盖"受保护"这一事实（否则提示会误导）
    if is_protected(p):
        return False, (f"受保护目录，禁止删除: {p}\n"
                       f"（C:\\Windows 已开启写保护；"
                       f"需临时关闭请在命令栏输入 SAFE_MODE_OFF）")
    if not os.path.exists(p):
        return False, f"不存在: {p}"

    import shutil
    try:
        if os.path.isdir(p):
            shutil.rmtree(p)
            return True, f"已删除文件夹: {os.path.basename(p)}"
        os.remove(p)
        return True, f"已删除文件: {os.path.basename(p)}"
    except Exception as e:
        # 常见: Windows 上文件被占用 → PermissionError
        return False, f"删除失败: {type(e).__name__}: {e}"
