# -*- coding: utf-8 -*-
"""
test_deploy_ui.py - 测试「一键部署」对话框 UI 层

验证:
  1. 模块可导入，open_deploy_dialog 存在且可调用
  2. 对话框可无错构建（不依赖真实 controller）
  3. 字段变量、控件齐全
  4. 阶段中文映射正确
  5. 文件探测 / IP 填入逻辑
"""
import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def skip_no_tk(cls):
    try:
        import tkinter  # noqa
        return cls
    except Exception:
        return unittest.skip("tkinter 不可用")(cls)


@skip_no_tk
class TestDeployUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        from deploy_ui import DeployDialog
        cls.tk = tk
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.dlg = DeployDialog(cls.root)
        cls.dlg.win.update_idletasks()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.dlg.win.destroy()
        except Exception:
            pass
        try:
            cls.root.destroy()
        except Exception:
            pass

    # -------- 1. 入口 --------
    def test_01_module_has_open_deploy_dialog(self):
        import deploy_ui
        self.assertTrue(callable(getattr(deploy_ui, "open_deploy_dialog", None)),
                        "缺少入口函数 open_deploy_dialog（这是'无法打开部署窗口'的根因）")

    def test_02_dialog_attributes(self):
        d = self.dlg
        # 关键控件存在
        for name in ("ip_text", "exe_var", "jcc_var", "dir_var", "name_var",
                     "workers_var", "timeout_var", "start_var",
                     "tree", "summary", "start_btn", "stop_btn", "close_btn",
                     "jcc_state"):
            self.assertTrue(hasattr(d, name), f"缺少属性: {name}")
        # 按钮初始状态：开始可用，停止禁用
        self.assertEqual(str(self.dlg.start_btn.cget("state")), "normal")
        self.assertEqual(str(self.dlg.stop_btn.cget("state")), "disabled")

    def test_03_default_values(self):
        from deploy import (DEFAULT_REMOTE_DIR, DEFAULT_TARGET_NAME,
                            DEFAULT_TIMEOUT, DEFAULT_WORKERS)
        d = self.dlg
        self.assertEqual(d.dir_var.get(), DEFAULT_REMOTE_DIR)
        self.assertEqual(d.name_var.get(), DEFAULT_TARGET_NAME)
        self.assertEqual(int(d.workers_var.get()), DEFAULT_WORKERS)
        self.assertEqual(int(d.timeout_var.get()), int(DEFAULT_TIMEOUT))

    def test_04_ip_fill(self):
        from deploy import local_subnet_prefix
        self.dlg._fill_local()
        self.assertEqual(self.dlg.ip_text.get("1.0", "end-1c"),
                         local_subnet_prefix() + "10-56")
        self.dlg._fill_full()
        self.assertEqual(self.dlg.ip_text.get("1.0", "end-1c"),
                         local_subnet_prefix() + "1-254")

    def test_05_stage_text_mapping(self):
        from deploy_ui import STAGE_TEXT
        # 关键阶段都有中文映射
        for k in ("待部署", "建目录", "下载", "启动", "完成", "失败", "取消"):
            self.assertIn(k, STAGE_TEXT)
            self.assertGreater(len(STAGE_TEXT[k]), 0)

    def test_06_tree_columns(self):
        cols = list(self.dlg.tree["columns"])
        self.assertEqual(cols, ["ip", "stage", "detail"])
        # 表头文字是中文
        self.assertEqual(self.dlg.tree.heading("ip", "text"), "IP 地址")
        self.assertEqual(self.dlg.tree.heading("stage", "text"), "状态")

    def test_07_tree_tag_colors(self):
        for tag in ("ok", "fail", "run", "pend", "cancel"):
            self.assertIn(tag, self.dlg.tree.tag_names())

    def test_08_file_detect_updates_state(self):
        # 模拟探测到 jcc
        self.dlg.jcc_var.set(os.path.join(HERE, "deploy.py"))
        self.dlg._pick_jcc = lambda: None  # 不弹对话框
        self.dlg._check_ready()
        self.assertIn("已选择", self.dlg.jcc_state.cget("text"))

    def test_09_start_without_exe_shows_warning(self):
        import tkinter.messagebox as mb
        self.dlg.exe_var.set("")
        self.dlg.jcc_var.set(os.path.join(HERE, "deploy.py"))
        with patch.object(mb, "showwarning") as w:
            self.dlg.start()
            self.assertTrue(w.called, "缺少被控端时应弹警告")
            self.assertIn("缺少文件", w.call_args[0][0])

    def test_10_start_without_jcc_shows_warning(self):
        import tkinter.messagebox as mb
        self.dlg.exe_var.set(os.path.join(HERE, "deploy.py"))
        self.dlg.jcc_var.set("")
        with patch.object(mb, "showwarning") as w:
            self.dlg.start()
            self.assertTrue(w.called)
            self.assertIn("jcc.exe", w.call_args[0][0])

    def test_11_invalid_ip_shows_warning(self):
        import tkinter.messagebox as mb
        self.dlg.exe_var.set(os.path.join(HERE, "deploy.py"))
        self.dlg.jcc_var.set(os.path.join(HERE, "deploy.py"))
        self.dlg.ip_text.delete("1.0", "end")
        self.dlg.ip_text.insert("1.0", "这不是一个IP\n999.999.999.999")
        with patch.object(mb, "showwarning") as w:
            self.dlg.start()
            self.assertTrue(w.called)
            self.assertIn("IP 无效", w.call_args[0][0])

    def test_12_running_ui_toggle(self):
        self.dlg._set_running_ui(True)
        self.assertEqual(str(self.dlg.stop_btn.cget("state")), "normal")
        self.dlg._set_running_ui(False)
        self.assertEqual(str(self.dlg.stop_btn.cget("state")), "disabled")

    def test_13_open_deploy_dialog_none_creates_root(self):
        # 无 parent 时不崩溃
        import deploy_ui
        with patch.object(deploy_ui, "DeployDialog") as mocked:
            deploy_ui.open_deploy_dialog(None)
            self.assertTrue(mocked.called)


if __name__ == "__main__":
    unittest.main(verbosity=2)
