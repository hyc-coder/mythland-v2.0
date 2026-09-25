"""
agent_silent.pyw - 被控端【静默启动】入口（源码运行时用）

.pyw 后缀在 Windows 上会被 pythonw.exe 执行 —— 完全无控制台窗口，
双击后直接后台运行，桌面上什么都看不到（符合"静默启动"要求）。

所有输出都写进程序同目录的 agent.log，控制端可远程查看。

用法:
    双击本文件即可（零参数，自动发现）

注意:
  - 这是【源码运行】用的静默入口
  - 打包成 exe 后用 --windowed（build.py 已配置），不需要本文件
  - 想看实时日志窗口时，改用: python agent.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import main

if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 静默模式下没有控制台，异常要落到日志文件里，便于排查
        import traceback
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "agent_error.log"), "a", encoding="utf-8") as f:
                f.write("\n[崩溃] =====\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        sys.exit(1)
