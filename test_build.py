"""
test_build.py - 打包配置自检

打包最容易踩的坑：函数内【动态 import】的模块，PyInstaller 静态分析抓不到，
不会打进 exe，运行时才报 ModuleNotFoundError —— 而且只在打包后暴露，
源码跑得好好的根本发现不了。

历史上踩过:
  - session.py（设备详情）被漏掉
  - broadcast / deploy / deploy_ui / http.server（控制端动态加载）被漏掉
  - tkinter.messagebox / simpledialog / filedialog 被漏掉

本测试用 AST 扫描每个入口脚本的【函数内 import】，逐一核对
是否在对应的 --hidden-import 列表里。以后新增模块漏声明，这里会直接报错。

运行: python test_build.py
"""

import ast
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build as B

# 标准库 / 一定会被打进去的，不需要声明
STDLIB_SAFE = {
    "os", "sys", "io", "time", "socket", "threading", "queue", "base64",
    "platform", "subprocess", "re", "shutil", "struct", "json", "traceback",
    "argparse", "datetime", "colorsys", "tempfile", "stat", "urllib.request",
    "concurrent.futures", "xml.etree.ElementTree",
}


def inner_imports(py_path: str) -> set:
    """
    找出【函数内】的 import（缩进的 import 行）。
    这类 import PyInstaller 静态分析可能抓不到。
    """
    with open(py_path, encoding="utf-8") as f:
        src = f.read()
    found = set()
    for line in src.split("\n"):
        s = line.strip()
        if not (s.startswith("import ") or s.startswith("from ")):
            continue
        if not (line.startswith(" ") or line.startswith("\t")):
            continue          # 顶层 import，静态分析能抓到
        if s.startswith("from "):
            mod = s.split()[1]
        else:
            mod = s[len("import "):].split()[0]
        found.add(mod.split(".")[0] if not mod.startswith("tkinter") else mod)
    return found


def assert_covered(entry: str, hidden: list, label: str):
    """入口脚本里所有函数内 import 的【本项目模块】都必须在 hidden 列表里"""
    path = os.path.join(HERE, entry)
    mods = inner_imports(path)
    print(f"\n[{label}] {entry} 的函数内 import:")
    missing = []
    for m in sorted(mods):
        # 本项目模块 = 同目录下有对应 .py
        is_local = os.path.isfile(os.path.join(HERE, m + ".py"))
        is_std = m in STDLIB_SAFE
        ok = (not is_local) or (m in hidden)
        mark = "✓" if (m in hidden or is_std) else ("✗" if is_local else "·")
        kind = "本地模块" if is_local else ("标准库" if is_std else "第三方")
        print(f"   {mark} {m:22s} {kind}")
        if is_local and m not in hidden:
            missing.append(m)

    if missing:
        raise AssertionError(
            f"{label}({entry}) 这些本地模块是函数内动态 import，"
            f"必须加进 {label}_HIDDEN: {missing}\n"
            f"否则打包成 exe 后会 ModuleNotFoundError")
    print(f"   → 本地模块已全部声明 ✓")


def test_controller_hidden():
    print("\n[测试1] 控制端隐藏导入完整性")
    assert_covered("controller.py", B.CONTROLLER_HIDDEN, "CONTROLLER")


def test_agent_hidden():
    print("\n[测试2] 被控端隐藏导入完整性")
    assert_covered("agent.py", B.AGENT_HIDDEN, "AGENT")


def test_transitive():
    """
    递归检查：被 hidden 声明的模块，它自己内部的动态 import 也要覆盖。
    例: controller → deploy_ui → deploy → http.server
    """
    print("\n[测试3] 传递依赖（模块内部还有动态 import）")
    checked = set()

    def walk(mod, hidden, label, depth=0):
        if mod in checked or depth > 3:
            return
        checked.add(mod)
        path = os.path.join(HERE, mod + ".py")
        if not os.path.isfile(path):
            return
        for m in sorted(inner_imports(path)):
            is_local = os.path.isfile(os.path.join(HERE, m + ".py"))
            if not is_local and m not in ("http.server",):
                continue
            if m in STDLIB_SAFE and not is_local:
                continue
            if m not in hidden:
                raise AssertionError(
                    f"{mod} 动态 import 了 {m}，但 {label}_HIDDEN 里没有 → "
                    f"打包后会 ModuleNotFoundError")
            print(f"   {'  ' * depth}{mod} → {m} ✓")
            walk(m, hidden, label, depth + 1)

    walk("session", B.CONTROLLER_HIDDEN, "CONTROLLER")
    walk("broadcast", B.CONTROLLER_HIDDEN, "CONTROLLER")
    walk("deploy_ui", B.CONTROLLER_HIDDEN, "CONTROLLER")
    walk("deploy", B.CONTROLLER_HIDDEN, "CONTROLLER")
    print("   → 控制端传递依赖完整 ✓")

    checked.clear()
    for m in ("viewer", "notifier", "url_opener", "process_mgr",
              "file_mgr", "input_inject"):
        walk(m, B.AGENT_HIDDEN, "AGENT")
    print("   → 被控端传递依赖完整 ✓")


def test_tkinter_submodules():
    print("\n[测试4] tkinter 子模块（函数内 import 的最易漏）")
    need = ["tkinter", "tkinter.ttk", "tkinter.messagebox",
            "tkinter.simpledialog", "tkinter.filedialog", "tkinter.font"]
    for n in need:
        assert n in B.CONTROLLER_HIDDEN, f"控制端缺 {n}"
        assert n in B.AGENT_HIDDEN, f"被控端缺 {n}"
    print(f"   {len(need)} 个 tkinter 子模块均已声明 ✓")


def _toplevel_local_imports(mod: str) -> set:
    """模块的【顶层】import 里属于本项目的模块（静态分析能抓到）"""
    path = os.path.join(HERE, mod + ".py")
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as f:
        src = f.read()
    out = set()
    for line in src.split("\n"):
        s = line.strip()
        if not (s.startswith("import ") or s.startswith("from ")):
            continue
        if line.startswith(" ") or line.startswith("\t"):
            continue                     # 缩进的 = 函数内，不算静态可达
        if s.startswith("from "):
            name = s.split()[1]
        else:
            name = s[len("import "):].split()[0]
        root = name.split(".")[0]
        if os.path.isfile(os.path.join(HERE, root + ".py")):
            out.add(root)
    return out


def _statically_reachable(entries) -> set:
    """从入口脚本出发，BFS 收集所有静态可达的本地模块"""
    seen, stack = set(), list(entries)
    while stack:
        m = stack.pop()
        if m in seen:
            continue
        seen.add(m)
        stack.extend(_toplevel_local_imports(m) - seen)
    return seen


def test_all_local_modules_declared():
    """
    所有功能模块都必须【能被打包进 exe】，途径二选一:
      A. 静态可达（入口脚本顶层 import 链）—— PyInstaller 自动抓到
      B. 在 hidden-import 列表里 —— 手动声明
    两条路都不通的 = 会被漏掉。
    """
    print("\n[测试5] 所有功能模块都能被打包进 exe")
    static = _statically_reachable(["controller", "agent"])
    print(f"  静态可达（PyInstaller 自动抓到）: {sorted(static)}")

    all_hidden = set(B.CONTROLLER_HIDDEN) | set(B.AGENT_HIDDEN)
    # 诊断/自查脚本不需要打进 exe（运行时不依赖它们）
    skip_prefix = ("test_", "diag_")
    skip_names = {"build", "diag", "check_env", "agent_silent"}
    uncovered = []
    for fn in sorted(os.listdir(HERE)):
        if not fn.endswith(".py") or fn.endswith("_demo.py"):
            continue
        mod = fn[:-3]
        if mod.startswith(skip_prefix) or mod in skip_names:
            continue
        if mod in static:
            print(f"   ✓ {mod:16s} （静态可达）")
        elif mod in all_hidden:
            print(f"   ✓ {mod:16s} （hidden 声明）")
        else:
            uncovered.append(mod)

    assert not uncovered, (
        f"这些模块既非静态可达、也不在 hidden 列表里，打包时会被漏掉: {uncovered}")
    print("   → 无遗漏 ✓")


def test_entry_scripts_exist():
    print("\n[测试6] 入口脚本存在且语法正确")
    for entry in ("controller.py", "agent.py", "session.py", "build.py"):
        p = os.path.join(HERE, entry)
        assert os.path.isfile(p), f"缺 {entry}"
        with open(p, encoding="utf-8") as f:
            compile(f.read(), p, "exec")
        print(f"   ✓ {entry}")
    # 静默启动入口
    for extra in ("agent_silent.pyw", "build.bat", "start_demo.bat"):
        p = os.path.join(HERE, extra)
        if os.path.isfile(p):
            print(f"   ✓ {extra}")
    print("   ✓ 入口齐全")


def test_dry_run():
    print("\n[测试7] build.py 能正常生成打包命令")
    r = subprocess.run([sys.executable, "build.py", "--dry-run"],
                       cwd=HERE, capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    assert "打包 controller 的命令" in out, "应打印控制端打包命令"
    assert "打包 agent 的命令" in out, "应打印被控端打包命令"
    # 三个产物都要出现在预览里（英文名）
    for name in ("controller", "agent", "agent-debug"):
        assert f"--name={name}" in out, f"预览里缺 {name}"
    print("   ✓ 三个产物的打包命令都能生成（controller/agent/agent-debug）")

    # 控制端命令必须含这些动态模块
    ctrl_line = [l for l in out.split("\n") if "--name=controller" in l][0]
    for need in ("session", "broadcast", "deploy_ui", "about", "http.server"):
        assert f"--hidden-import={need}" in ctrl_line, f"控制端打包命令缺 {need}"
    print("   ✓ 控制端命令含 session/broadcast/deploy_ui/about/http.server")

    agent_line = [l for l in out.split("\n") if "--name=agent " in l
                  or "--name=agent --" in l][0]
    for need in ("viewer", "notifier", "url_opener", "process_mgr",
                 "file_mgr", "input_inject"):
        assert f"--hidden-import={need}" in agent_line, f"被控端打包命令缺 {need}"
    print("   ✓ 被控端命令含 viewer/notifier/url_opener/process_mgr/...")

    # 产物名必须是纯 ASCII（中文名在某些 PyInstaller/系统上会出问题）
    for name in ("controller", "agent", "agent-debug"):
        assert name.isascii(), f"产物名含非 ASCII: {name}"
    print("   ✓ 产物名均为 ASCII，兼容性好")


if __name__ == "__main__":
    print("=" * 62)
    print("  打包配置自检")
    print("=" * 62)
    test_controller_hidden()
    test_agent_hidden()
    test_transitive()
    test_tkinter_submodules()
    test_all_local_modules_declared()
    test_entry_scripts_exist()
    test_dry_run()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓  打包配置完整")
    print("=" * 62)
