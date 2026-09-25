"""
screen.py - 屏幕采集（真实截图 / 模拟画面 降级）
输出统一为 JPEG 二进制，供 Agent 返回缩略图、Controller 预览墙显示。

优先级:
  1. 尝试真实截图 (mss / PIL.ImageGrab)
  2. 失败则生成带机器名的模拟桌面画面 (PIL)
这样在没有显示环境的机器(如服务器/测试机)上也能演示预览墙效果。
"""

import io
import time
import threading

try:
    import mss  # 跨平台高效截图
    HAS_MSS = True
except Exception:
    HAS_MSS = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except Exception:
    HAS_PIL = False

# 兜底占位图：160x100 深灰 JPEG（硬编码 base64，不依赖任何第三方库）
# 用于「Pillow 不可用」的极端情况，保证 capture_jpeg 永不抛异常。
_PLACEHOLDER_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABQODxIPDRQSEBIXFRQYHjIhHhwcHj0sLiQySUBMS0dARkVQWnNiUFVtVkV"
    "GZIhlbXd7gYKBTmCNl4x9lnN+gXz/2wBDARUXFx4aHjshITt8U0ZTfHx8fHx8fHx8fHx8fHx8fHx8fHx8"
    "fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHz/wAARCAAIAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEA"
    "AAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEI"
    "I0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4"
    "eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo"
    "6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQA"
    "AQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNE"
    "RUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3"
    "uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDn6KKKsD//2Q=="
)


def _placeholder_jpeg() -> bytes:
    """返回内置占位 JPEG 字节（纯标准库实现）"""
    import base64
    try:
        return base64.b64decode(_PLACEHOLDER_JPEG_B64)
    except Exception:
        return b""


class ScreenCapturer:
    """屏幕采集器: 单例风格，持续生成 JPEG 缩略图"""

    def __init__(self, machine_name: str = "PC"):
        self.machine_name = machine_name
        import platform
        self.os_name = f"{platform.system()} {platform.release()}"
        self._sct = None
        self._lock = threading.Lock()
        self._frame_index = 0
        if HAS_MSS:
            try:
                self._sct = mss.mss()
            except Exception:
                self._sct = None

    # ---------- 公共 API ----------

    def capture_jpeg(self, width: int = 160, height: int = 100, quality: int = 50) -> bytes:
        """
        采集一帧并缩放为指定尺寸的 JPEG 二进制。
        成功返回真实截图，失败返回模拟画面（永远不抛异常）。
        """
        self._frame_index += 1
        try:
            # 真实截图需要 mss + Pillow 同时可用
            if self._sct and HAS_MSS and HAS_PIL:
                return self._grab_real(width, height, quality)
        except Exception:
            pass
        # 降级: 模拟画面
        return self._make_fake(width, height, quality)

    # ---------- 真实截图 ----------

    def _grab_real(self, width: int, height: int, quality: int) -> bytes:
        # 抓取主显示器
        monitor = self._sct.monitors[1] if len(self._sct.monitors) > 1 else self._sct.monitors[0]
        raw = self._sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.rgb)
        return self._resize_and_encode(img, width, height, quality)

    # ---------- 模拟画面（演示/降级） ----------

    def _make_fake(self, width: int, height: int, quality: int) -> bytes:
        """生成一张带机器名 + 动态时间戳的模拟桌面，用于演示预览墙"""
        if not HAS_PIL:
            # Pillow 不可用：直接返回内置占位 JPEG，绝不触碰 Image（否则 NameError）
            return _placeholder_jpeg()

        # 根据帧号做轻微动画，让预览墙看起来"活着"
        hue = (self._frame_index * 7) % 360
        bg = self._hsv_to_rgb(hue / 360.0, 0.45, 0.35)
        img = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(img)

        # 标题栏
        draw.rectangle([0, 0, width, 22], fill=(20, 20, 40))
        # 桌面图标(几个色块)
        colors = [(220, 60, 60), (60, 200, 90), (70, 130, 230), (240, 200, 60)]
        for i, c in enumerate(colors):
            x = 10 + i * 36
            draw.rectangle([x, 34, x + 26, 60], fill=c)
        # 文字信息
        text = f"{self.machine_name}\n{time.strftime('%H:%M:%S')}\nFrame {self._frame_index}"
        draw.multiline_text((8, 70), text, fill=(240, 240, 240))
        return self._encode(img, quality)

    # ---------- 工具 ----------

    def _resize_and_encode(self, img: "Image.Image", width: int, height: int, quality: int) -> bytes:
        img = img.resize((width, height), Image.LANCZOS)
        return self._encode(img, quality)

    @staticmethod
    def _encode(img: "Image.Image", quality: int) -> bytes:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    @staticmethod
    def _hsv_to_rgb(h: float, s: float, v: float) -> tuple:
        # 简易 HSV->RGB，用于生成变化背景色
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return (int(r * 255), int(g * 255), int(b * 255))
