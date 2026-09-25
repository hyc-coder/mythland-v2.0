"""
diag_deploy.py - 部署窗口"无法打开/点了没反应"精确诊断

用法: 在解压目录下双击，或在 CMD 里 python diag_deploy.py
输出: deploy_diag.log (同目录) + 控制台

会逐项检查并把异常堆栈完整打印出来，定位到具体哪一行。
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

LOG = os.path.join(HERE, "deploy_diag.log")


def log(msg):
    print(msg)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def section(title):
    log("")
    log("=" * 56)
    log("  " + title)
    log("=" * 56)


def check(label, fn):
    try:
        result = fn()
        log(f"  [OK]   {label}: {result}")
        return result
    except Exception as e:
        log(f"  [FAIL] {label}: {type(e).__name__}: {e}")
        log("         " + traceback.format_exc().replace("\n", "\n         "))
        return None


def main():
    open(LOG, "w", encoding="utf-8").close()
    log("部署窗口诊断 - " + HERE)

    # ---------- 1. 基础环境 ----------
    section("1. Python 环境")
    log(f"  executable: {sys.executable}")
    log(f"  version:    {sys.version.split()[0]}")
    log(f"  platform:   {sys.platform}")
    log(f"  cwd:        {os.getcwd()}")

    section("2. 关键模块能否导入")
    for mod in ("tkinter", "threading", "subprocess", "queue",
                "http.server", "socketserver", "ipaddress",
                "deploy", "deploy_ui"):
        check(f"import {mod}", lambda m=mod: __import__(m))

    # ---------- 3. tkinter 能否真正起窗口 ----------
    section("3. tkinter 真实可用性（有无显示环境）")
    def make_root():
        import tkinter as tk
        r = tk.Tk()
        r.title("diag")
        r.geometry("100x60")
        r.update_idletasks()
        return r
    root = check("创建 Tk 根窗口", make_root)
    if root is None:
        log("\n  >>> 结论: tkinter 无法创建窗口。")
        log("  >>> 常见原因: 服务器无显示器 / DISPLAY 未设置 / Python 装的是无 tk 版本。")
        log("  >>> 在 Windows 桌面环境通常不会有此问题；若在远程服务器跑请改用本地桌面。")
    else:
        try:
            root.destroy()
            log("  [OK]   窗口创建成功并已销毁")
        except Exception as e:
            log(f"  [WARN]  destroy 异常: {e}")

    # ---------- 4. DeployUI 类定义检查 ----------
    section("4. DeployUI 类")
    try:
        import deploy_ui
        log(f"  [OK]   deploy_ui 模块文件: {deploy_ui.__file__}")
    except Exception as e:
        log(f"  [FAIL] 无法导入 deploy_ui: {e}")
        log(traceback.format_exc())
        log("\n  >>> 这是最常见原因: 你替换的文件语法有误 / 保存成了 .txt / 依赖没装")
        return

    check("DeployUI 是可调用类",
          lambda: isinstance(deploy_ui.DeployUI, type))

    # ---------- 5. 真实实例化（模拟点击"打开"的全过程） ----------
    section("5. 模拟打开部署窗口（完整流程）")
    try:
        import tkinter as tk
        root2 = tk.Tk()
        root2.withdraw()

        log("  正在实例化 DeployUI ...")
        ui = deploy_ui.DeployUI(root2)
        log("  [OK]   DeployUI() 实例化成功")

        # 检查关键控件是否创建
        checks = [
            ("start_btn 开始部署按钮", lambda: ui.start_btn and ui.start_btn.winfo_exists()),
            ("stop_btn 停止按钮",     lambda: ui.stop_btn and ui.stop_btn.winfo_exists()),
            ("tree 进度表",           lambda: ui.tree and ui.tree.winfo_exists()),
            ("ip_text IP输入框",      lambda: ui.ip_text and ui.ip_text.winfo_exists()),
        ]
        for name, fn in checks:
            check(name, fn)

        # 检查 _start 方法存在且可调用
        check("_start 方法存在", lambda: callable(ui._start))
        check("_parse_ips 方法存在", lambda: callable(ui._parse_ips))

        # 模拟读 IP 框
        def read_ip():
            raw = ui.ip_text.get("1.0", "end").strip()
            return repr(raw)
        check("读取 IP 输入框内容", read_ip)

        # 关键: 检查文件探测结果（那个"已找到 jcc.exe"的绿字）
        log("")
        log("  --- 文件探测状态（这是点击后最容易卡住的地方）---")
        log(f"  agent_var: {ui.agent_var.get()}")
        log(f"  jcc_var:   {ui.jcc_var.get()}")
        log(f"  agent 存在: {os.path.isfile(ui.agent_var.get())}")
        log(f"  jcc 存在:   {os.path.isfile(ui.jcc_var.get())}")
        log(f"  file_hint:  {ui.file_hint.cget('text')}")
        log(f"  start_btn state: {ui.start_btn.cget('state')}")

        if not os.path.isfile(ui.jcc_var.get()):
            log("")
            log("  >>> [重要] jcc.exe 不存在于预期路径！")
            log("  >>> 这会导致 _check_files() 把开始按钮设为 disabled，")
            log("  >>> 表现就是'点了没反应'。")
            log("  >>> 解决: 把 jcc.exe 放到与被控端.exe 同目录，")
            log(f"  >>>       或在界面里点'选择'手动指定。")

        # 列出同目录所有 exe，方便对照
        log("")
        log("  --- 同目录下的 exe 文件 ---")
        found_any = False
        for fn in sorted(os.listdir(HERE)):
            if fn.lower().endswith(".exe"):
                log(f"    {fn}  ({os.path.getsize(os.path.join(HERE, fn))//1024} KB)")
                found_any = True
        if not found_any:
            log("    (无)")

        root2.after(200, root2.destroy)
        root2.mainloop()

    except Exception as e:
        log("")
        log("  !!!!! 打开窗口时抛异常 !!!!!")
        log(f"  {type(e).__name__}: {e}")
        log(traceback.format_exc())

    # ---------- 6. 结论 ----------
    section("6. 结论")
    log("  请查看上方 [FAIL] 标记的项，那一项就是根因。")
    log(f"  完整日志已写入: {LOG}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
    finally:
        print("")
        print("诊断完成，按任意键退出...")
        try:
            input()
        except Exception:
            pass
