"""
build.py - 一键打包成 exe（双端零参数启动）

产物（输出到 dist/）:
    控制端.exe        教师机用，图形界面，无黑框
    被控端.exe        学生机用，后台静默运行，无黑框（日志写 agent.log）
    被控端-调试版.exe  同上但带控制台，可实时看日志（排查用）

用法:
    python build.py

可选:
    python build.py --onedir     # 打成文件夹（启动更快，适合 U 盘携带）
    python build.py --debug      # 只打调试版
"""

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")

# 公用隐藏导入：打包器静态分析抓不到的动态 import
COMMON_HIDDEN = [
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL._tkinter_finder",
    "mss",
    "mss.windows",
    # tkinter 子模块：都是函数内 import，静态分析抓不到
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "tkinter.simpledialog",
    "tkinter.filedialog",
    "tkinter.font",
]

# 控制端专属: 这些都是【函数内动态 import】的，必须显式声明
CONTROLLER_HIDDEN = COMMON_HIDDEN + [
    "session",          # 设备详情窗口
    "broadcast",        # 屏幕广播（主控端采集并推流）
    "deploy",           # 一键部署核心
    "deploy_ui",        # 一键部署对话框
    "about",            # 关于软件对话框（免责声明 + 作者）
    "http.server",      # 部署时起临时 HTTP 供目标机下载
]

# 被控端专属: input_inject + pyautogui 依赖链（都是 try/except 动态导入）
AGENT_HIDDEN = COMMON_HIDDEN + [
    "input_inject",     # 键鼠注入
    "process_mgr",      # 进程管理
    "file_mgr",         # 文件管理
    "url_opener",       # 打开网址
    "notifier",         # 右下角消息弹窗
    "viewer",           # 屏幕广播窗口（被控端接收端）
    "webbrowser",       # 打开网址的标准库后端
    "psutil",
    "pyautogui",
    "pyautogui._pyautogui_win",
    "pyscreeze",
    "pytweening",
    "pymsgbox",
    "mouseinfo",
    "pynput",
    "pynput.mouse",
    "pynput.keyboard",
    "pynput.mouse._win32",
    "pynput.keyboard._win32",
]


def run(cmd, desc=""):
    print(f"\n>>> {desc or ' '.join(cmd[:3])}")
    print(f"    {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode != 0:
        print(f"\n[失败] 退出码 {r.returncode}: {desc}")
        return False
    return True


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa
        print(f"[OK] PyInstaller 已安装")
        return True
    except ImportError:
        print("[..] 正在安装 PyInstaller ...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])
        if r.returncode != 0:
            print("[错误] PyInstaller 安装失败，请手动执行:")
            print(f'       "{sys.executable}" -m pip install pyinstaller')
            return False
        return True


def check_deps():
    """
    检查依赖是否装到当前解释器（打包会把它们一起打进 exe）。

    分级:
      必需   pillow —— 缺了预览墙无法渲染，直接黑屏
      推荐   mss    —— 缺了只能发模拟画面（看不到对方真实桌面）
      可选   pyautogui/pynput —— 缺了不能远程控制键鼠，但监控正常
    """
    print("\n" + "=" * 60)
    print("  依赖检查（这些会被一起打包进 exe）")
    print("=" * 60)

    required = {"pillow": "PIL"}          # 缺了不能跑
    recommended = {"mss": "mss", "psutil": "psutil"}   # 缺了功能降级
    optional = {"pyautogui": "pyautogui", "pynput": "pynput"}   # 缺了不能控制

    missing_required = []
    for pkg, imp in required.items():
        try:
            __import__(imp)
            print(f"  [必需] {pkg:12s} ✓ 已安装")
        except ImportError:
            print(f"  [必需] {pkg:12s} ✗ 缺失")
            missing_required.append(pkg)

    missing_reco = []
    RECO_DESC = {
        "mss": "可采集真实桌面",
        "psutil": "进程管理信息完整（CPU/内存）",
    }
    for pkg, imp in recommended.items():
        desc = RECO_DESC.get(pkg, "")
        try:
            __import__(imp)
            print(f"  [推荐] {pkg:12s} ✓ 已安装（{desc}）")
        except ImportError:
            print(f"  [推荐] {pkg:12s} ✗ 缺失（功能降级）")
            missing_reco.append(pkg)

    has_input = False
    for pkg, imp in optional.items():
        try:
            __import__(imp)
            print(f"  [可选] {pkg:12s} ✓ 已安装（键鼠控制可用）")
            has_input = True
        except ImportError:
            print(f"  [可选] {pkg:12s} - 未安装")

    if missing_required:
        print(f"\n[错误] 缺少必需依赖: {', '.join(missing_required)}")
        print(f'      请执行: "{sys.executable}" -m pip install pillow')
        return False

    if missing_reco:
        impact = {
            "mss": "被控端只能发送【模拟画面】，看不到对方真实桌面",
            "psutil": "进程管理降级为系统命令（Windows 用 tasklist，无 CPU 占用）",
        }
        print(f"\n[警告] 缺少推荐依赖: {', '.join(missing_reco)}")
        for pkg in missing_reco:
            print(f"       - {pkg}: {impact.get(pkg, '功能降级')}")
        print(f"  建议先安装:")
        print(f'       "{sys.executable}" -m pip install {" ".join(missing_reco)}')

    if not has_input:
        print(f"\n[提示] 未装 pyautogui/pynput，打包后【不能远程控制键鼠】，屏幕监控仍正常。")
        print(f'      如需控制: "{sys.executable}" -m pip install pyautogui')

    return True


def _has(pkg):
    try:
        __import__(pkg)
        return True
    except ImportError:
        return False


def build(script, name, windowed, hidden, mode_flag, dry_run=False):
    cmd = [sys.executable, "-m", "PyInstaller", script, f"--name={name}", mode_flag]
    if windowed:
        cmd.append("--windowed")
    else:
        cmd.append("--console")
    for h in hidden:
        cmd.append(f"--hidden-import={h}")
    cmd += ["--clean", "--noconfirm", "--log-level=WARN"]
    if dry_run:
        print(f"\n[预览] 打包 {name} 的命令:")
        print(f"       {' '.join(cmd)}")
        return True
    return run(cmd, f"打包 {name}")


def main():
    ap = argparse.ArgumentParser(description="打包成 exe")
    ap.add_argument("--onedir", action="store_true", help="打成文件夹（默认单文件）")
    ap.add_argument("--debug", action="store_true", help="只打调试版（带控制台）")
    ap.add_argument("--dry-run", action="store_true", help="只打印打包命令，不实际执行")
    args = ap.parse_args()

    mode_flag = "--onedir" if args.onedir else "--onefile"
    print("=" * 60)
    print("  局域网远控 - 打包成 exe")
    print(f"  模式: {mode_flag}" + ("  [预览模式]" if args.dry_run else ""))
    print("=" * 60)

    if not check_deps():
        return 1

    if not args.dry_run:
        if not ensure_pyinstaller():
            return 1
        # 清理旧产物
        for d in ("build", "dist"):
            p = os.path.join(HERE, d)
            if os.path.isdir(p):
                print(f"[..] 清理旧 {d}/")
                shutil.rmtree(p, ignore_errors=True)

    results = []

    if not args.debug:
        results.append(("controller", build("controller.py", "controller", True,
                                            CONTROLLER_HIDDEN, mode_flag, args.dry_run)))
        results.append(("agent", build("agent.py", "agent", True,
                                       AGENT_HIDDEN, mode_flag, args.dry_run)))

    results.append(("agent-debug", build("agent.py", "agent-debug", False,
                                         AGENT_HIDDEN, mode_flag, args.dry_run)))

    print("\n" + "=" * 60)
    print("  打包结果")
    print("=" * 60)
    ok = True
    for name, r in results:
        print(f"  {name:16s} {'✓ 成功' if r else '✗ 失败'}")
        if not r:
            ok = False

    if ok:
        print(f"\n  产物在: {DIST}")
        print(f"\n  使用方式（无需任何参数）:")
        print(f"    教师机: 双击 controller.exe")
        print(f"    学生机: 双击 agent.exe  （后台静默，无任何窗口）")
        print(f"    两端启动后会自动发现彼此，几秒内出现画面")
        print(f"\n  被控端日志:")
        print(f"    自动写在 exe 同目录的 agent.log（无窗口也能查运行状态）")
        print(f"    控制端点「查看日志」可远程读取；超过 2MB 自动轮转为 agent.log.old")
        print(f"\n  注意: 首次运行若被杀软拦截，请选择【允许】；")
        print(f"        防火墙需放行（专用网络）。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
