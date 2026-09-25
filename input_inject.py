"""
input_inject.py - 被控端键鼠注入（被控端 agent 使用）

依赖优先级:
  1. pyautogui —— 最简单，pip install pyautogui
  2. pynput    —— 备选，pip install pynput
  都没有 → 注入失败但不崩溃（只是不能控制，监控仍可用）

Windows 下不需要管理员权限。

用法:
    from input_inject import get_injector
    inj = get_injector()
    if inj.available:
        inj.move_to(100, 200)
        inj.click(100, 200, "left")
        inj.key_press("a")
"""

# Tk keysym → pyautogui 认识的键名
KEY_MAP = {
    "Return": "enter",
    "Escape": "esc",
    "BackSpace": "backspace",
    "Tab": "tab",
    "space": "space",
    "Delete": "delete",
    "Insert": "insert",
    "Home": "home",
    "End": "end",
    "Prior": "pageup",
    "Next": "pagedown",
    "Up": "up",
    "Down": "down",
    "Left": "left",
    "Right": "right",
    "Shift_L": "shift",
    "Shift_R": "shift",
    "Control_L": "ctrl",
    "Control_R": "ctrl",
    "Alt_L": "alt",
    "Alt_R": "alt",
    "Caps_Lock": "capslock",
    "Num_Lock": "numlock",
    "Print": "printscreen",
    "Pause": "pause",
}

# F1-F12
for _i in range(1, 13):
    KEY_MAP[f"F{_i}"] = f"f{_i}"


class InputInjector:
    """键鼠注入器（优先 pyautogui，回退 pynput）"""

    def __init__(self):
        self.backend = None
        self.error = ""
        self._pyautogui = None
        self._pynput = None

        # 试 pyautogui
        try:
            import pyautogui
            pyautogui.FAILSAFE = False   # 关掉"鼠标移到角落抛异常"的保护
            pyautogui.PAUSE = 0          # 每个动作后不暂停（我们要最快响应）
            self._pyautogui = pyautogui
            self.backend = "pyautogui"
            return
        except Exception as e:
            self.error = f"pyautogui 不可用: {e}"

        # 回退 pynput
        try:
            from pynput.mouse import Controller as MouseCtrl, Button
            from pynput.keyboard import Controller as KeyCtrl
            self._mouse = MouseCtrl()
            self._keyboard = KeyCtrl()
            self._Button = Button
            self._pynput = True
            self.backend = "pynput"
            return
        except Exception as e:
            self.error += f" | pynput 不可用: {e}"

    @property
    def available(self) -> bool:
        return self.backend is not None

    # ---------- 鼠标 ----------

    def move_to(self, x: int, y: int):
        if not self.available:
            return False
        try:
            if self._pyautogui:
                self._pyautogui.moveTo(int(x), int(y))
            else:
                self._mouse.position = (int(x), int(y))
            return True
        except Exception as e:
            print(f"[注入] 移动鼠标失败: {e}")
            return False

    def mouse_down(self, x: int, y: int, button: str = "left"):
        if not self.available:
            return False
        try:
            if self._pyautogui:
                self._pyautogui.mouseDown(x=int(x), y=int(y), button=button)
            else:
                self._mouse.position = (int(x), int(y))
                self._mouse.press(self._btn(button))
            return True
        except Exception as e:
            print(f"[注入] 按下鼠标失败: {e}")
            return False

    def mouse_up(self, x: int, y: int, button: str = "left"):
        if not self.available:
            return False
        try:
            if self._pyautogui:
                self._pyautogui.mouseUp(x=int(x), y=int(y), button=button)
            else:
                self._mouse.position = (int(x), int(y))
                self._mouse.release(self._btn(button))
            return True
        except Exception as e:
            print(f"[注入] 抬起鼠标失败: {e}")
            return False

    def click(self, x: int, y: int, button: str = "left"):
        if not self.available:
            return False
        try:
            if self._pyautogui:
                self._pyautogui.click(x=int(x), y=int(y), button=button)
            else:
                self._mouse.position = (int(x), int(y))
                b = self._btn(button)
                self._mouse.press(b)
                self._mouse.release(b)
            return True
        except Exception as e:
            print(f"[注入] 点击失败: {e}")
            return False

    def scroll(self, x: int, y: int, delta: int):
        if not self.available:
            return False
        try:
            if self._pyautogui:
                # pyautogui 的 scroll 单位是"格"，delta 通常是 ±120
                self._pyautogui.scroll(int(delta / 120) if abs(delta) >= 120 else (1 if delta > 0 else -1),
                                       x=int(x), y=int(y))
            else:
                self._mouse.position = (int(x), int(y))
                self._mouse.scroll(0, int(delta / 120) or (1 if delta > 0 else -1))
            return True
        except Exception as e:
            print(f"[注入] 滚轮失败: {e}")
            return False

    def _btn(self, button: str):
        """pynput 的按钮映射"""
        return {
            "left": self._Button.left,
            "right": self._Button.right,
            "middle": self._Button.middle,
        }.get(button, self._Button.left)

    # ---------- 键盘 ----------

    def key_down(self, key: str):
        if not self.available:
            return False
        try:
            k = KEY_MAP.get(key, key)
            if self._pyautogui:
                self._pyautogui.keyDown(k)
            else:
                self._keyboard.press(self._pynput_key(k))
            return True
        except Exception as e:
            print(f"[注入] 按下键失败: {e}")
            return False

    def key_up(self, key: str):
        if not self.available:
            return False
        try:
            k = KEY_MAP.get(key, key)
            if self._pyautogui:
                self._pyautogui.keyUp(k)
            else:
                self._keyboard.release(self._pynput_key(k))
            return True
        except Exception as e:
            print(f"[注入] 抬起键失败: {e}")
            return False

    def key_press(self, key: str):
        if not self.available:
            return False
        try:
            k = KEY_MAP.get(key, key)
            if self._pyautogui:
                # 单字符直接 typewrite 更可靠（支持中文等）
                if len(k) == 1:
                    self._pyautogui.typewrite(k)
                else:
                    self._pyautogui.press(k)
            else:
                kb = self._keyboard
                kb.press(self._pynput_key(k))
                kb.release(self._pynput_key(k))
            return True
        except Exception as e:
            print(f"[注入] 按键失败: {e}")
            return False

    def _pynput_key(self, k: str):
        """pynput 的键对象"""
        from pynput.keyboard import Key
        special = {
            "enter": Key.enter, "esc": Key.esc, "backspace": Key.backspace,
            "tab": Key.tab, "space": Key.space, "delete": Key.delete,
            "insert": Key.insert, "home": Key.home, "end": Key.end,
            "pageup": Key.page_up, "pagedown": Key.page_down,
            "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
            "shift": Key.shift, "ctrl": Key.ctrl, "alt": Key.alt,
            "capslock": Key.caps_lock, "numlock": Key.num_lock,
            "printscreen": Key.print_screen, "pause": Key.pause,
        }
        if k in special:
            return special[k]
        if k.startswith("f") and k[1:].isdigit():
            return getattr(Key, k, None) or k
        return k

    # ---------- 辅助 ----------

    def screen_size(self):
        """被控端屏幕分辨率 (w, h)"""
        try:
            if self._pyautogui:
                s = self._pyautogui.size()
                return (s.width, s.height)
            import mss
            with mss.mss() as sct:
                m = sct.monitors[1]
                return (m["width"], m["height"])
        except Exception:
            return (0, 0)


_injector = None


def get_injector() -> InputInjector:
    """获取全局单例注入器"""
    global _injector
    if _injector is None:
        _injector = InputInjector()
        if _injector.available:
            print(f"[Agent] 输入注入就绪 (后端: {_injector.backend})")
        else:
            print(f"[Agent] 输入注入不可用，将无法远程控制鼠标键盘")
            print(f"        原因: {_injector.error}")
            print(f"        修复: pip install pyautogui")
    return _injector
