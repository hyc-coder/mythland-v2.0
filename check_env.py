"""
check_env.py - 环境自检（双击或 python check_env.py 运行）
一次性查明：当前用的是哪个 Python、依赖装没装、装在哪、为什么 import 失败。
"""
import sys
import os
import subprocess

LINE = "=" * 60


def head(t):
    print("\n" + LINE)
    print(f"  {t}")
    print(LINE)


def check_module(name, import_stmt=None):
    """尝试导入模块，成功打印版本，失败打印真实报错"""
    stmt = import_stmt or name
    try:
        mod = __import__(name)
        ver = getattr(mod, "__version__", getattr(mod, "Version", "?"))
        print(f"  [OK]   {name:10s} {ver}")
        return True
    except Exception as e:
        print(f"  [FAIL] {name:10s} 导入失败 -> {type(e).__name__}: {e}")
        print(f"         导入语句: {stmt}")
        return False


def main():
    print(LINE)
    print("  远控软件 - 环境自检")
    print(LINE)

    # 1. 解释器信息
    head("1. 当前 Python 解释器")
    print(f"  路径:   {sys.executable}")
    print(f"  版本:   {sys.version.split()[0]}  ({sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})")
    print(f"  平台:   {sys.platform}")

    # 2. 依赖检查
    head("2. 依赖检查")
    results = {}
    results["tkinter"] = check_module("tkinter")          # 控制端界面（标准库）
    results["PIL"] = check_module("PIL")                  # Pillow：图像处理
    results["mss"] = check_module("mss")                  # 屏幕截图

    # 3. 如果 Pillow 失败，深挖原因
    if not results["PIL"]:
        head("3. Pillow 导入失败 - 详细追溯")
        try:
            import PIL  # noqa
        except Exception:
            import traceback
            traceback.print_exc()
        print("\n  可能原因:")
        print("   a) 装包的 Python 和当前运行/调试用的 Python 不是同一个")
        print("   b) Pillow 版本与当前 Python 版本不兼容")
        print("\n  修复建议:")
        print(f"   用【当前这个解释器】重装:")
        print(f"     \"{sys.executable}\" -m pip install --upgrade pillow mss")

    # 4. pip list 对照（看包装到了哪个解释器）
    head("4. 当前解释器的已装包（pip list 前几个）")
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pip", "list"],
            capture_output=True, text=True, timeout=30
        )
        lines = [l for l in out.stdout.splitlines()
                 if any(k in l.lower() for k in ("pillow", "mss", "pyinstaller", "pip"))]
        if lines:
            for l in lines:
                print(f"  {l}")
        else:
            print("  (未找到 pillow/mss —— 说明确实没装到这个解释器上)")
    except Exception as e:
        print(f"  执行 pip list 失败: {e}")

    # 5. 结论
    head("5. 结论与下一步")
    missing = [k for k, v in results.items() if not v]
    if not missing:
        print("  ✅ 所有依赖就绪，可以运行！")
        print("     控制端: python controller.py --port 9000")
        print("     被控端: python agent.py --name 演示机-01 --broadcast-ip 127.0.0.1 \\")
        print("                              --port 9001 --broadcast-port 9000")
    else:
        print(f"  ⚠️  缺少: {', '.join(missing)}")
        print("\n  一键修复（复制执行，注意用的是上面显示的那个 python 路径）:")
        print(f'     "{sys.executable}" -m pip install pillow mss')
        if "tkinter" in missing:
            print("\n  tkinter 缺失(Windows):")
            print("     重跑 Python 安装程序 -> Modify -> 勾选 'tcl/tk and IDLE'")
    print(LINE)


if __name__ == "__main__":
    main()
    if sys.platform == "win32":
        os.system("pause")
