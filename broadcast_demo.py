"""
broadcast_demo.py - 生成「屏幕广播」效果图
输出: broadcast_preview.png
"""

import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1120, 780

C_TITLEBAR = (21, 101, 192)
C_TITLEBAR_FG = (227, 242, 253)
C_APP_BG = (245, 249, 255)
C_ACCENT = (66, 165, 245)
C_BTN_BG = (21, 101, 192)
C_BTN_FG = (255, 255, 255)
C_BTN_LIGHT = (227, 242, 253)
C_MUTED = (120, 144, 156)
C_BORDER = (200, 215, 235)
C_TEXT = (55, 71, 79)
C_WHITE = (255, 255, 255)
C_RED = (198, 40, 40)
C_DESK = (58, 90, 130)
C_TASKBAR = (32, 44, 62)
C_TIP = (187, 222, 251)

FONT_PATH = None
for p in [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc",
]:
    if os.path.exists(p):
        FONT_PATH = p
        break

f = (lambda s: ImageFont.truetype(FONT_PATH, s)) if FONT_PATH else (lambda s: ImageFont.load_default())
f_title = f(13)
f_btn = f(10)
f_small = f(9)
f_tiny = f(8)
f_big = f(11)

img = Image.new("RGB", (W, H), C_APP_BG)
d = ImageDraw.Draw(img)


def rr(box, radius, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


# ============================================================
# 左：主控端 屏幕广播配置对话框
# ============================================================
DX, DY, DW, DH = 30, 90, 430, 400

d.rectangle([DX + 5, DY + 5, DX + DW + 5, DY + DH + 5], fill=(190, 200, 215))
d.rectangle([DX, DY, DX + DW, DY + DH], fill=C_APP_BG, outline=C_ACCENT, width=2)
d.rectangle([DX, DY, DX + DW, DY + 34], fill=C_TITLEBAR)
d.text((DX + 14, DY + 9), "屏幕广播（把本机屏幕直播给被控端）",
       fill=C_TITLEBAR_FG, font=f_title)

y = DY + 50
d.text((DX + 20, y), "把本机的屏幕广播给被控端", fill=C_BTN_BG,
       font=(f_big[0] if False else f(10)))

y += 30
d.text((DX + 20, y + 4), "标题:", fill=C_BTN_BG, font=f_small)
d.rectangle([DX + 90, y, DX + DW - 20, y + 26], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((DX + 98, y + 6), "教师机演示", fill=(70, 90, 110), font=f_small)

y += 36
d.text((DX + 20, y + 4), "帧率:", fill=C_BTN_BG, font=f_small)
d.rectangle([DX + 90, y, DX + 90 + 56, y + 24], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((DX + 100, y + 5), "8", fill=(70, 90, 110), font=f_small)
d.text((DX + 156, y + 5), "FPS（教学演示 6~10 就够）", fill=C_MUTED, font=f_tiny)

y += 34
d.text((DX + 20, y + 4), "画面宽:", fill=C_BTN_BG, font=f_small)
d.rectangle([DX + 90, y, DX + 90 + 56, y + 24], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((DX + 100, y + 5), "1280", fill=(70, 90, 110), font=f_small)
d.text((DX + 156, y + 5), "px（等比缩放，越小越省带宽）", fill=C_MUTED, font=f_tiny)

y += 38
d.text((DX + 20, y + 4), "范围:", fill=C_BTN_BG, font=f_small)
d.ellipse([DX + 90, y + 6, DX + 101, y + 17], outline=C_BTN_BG, width=2)
d.ellipse([DX + 93, y + 9, DX + 98, y + 14], fill=C_BTN_BG)
d.text((DX + 106, y + 4), "全部在线（30 台）", fill=C_TEXT, font=f_small)
d.ellipse([DX + 240, y + 6, DX + 251, y + 17], outline=C_MUTED, width=2)
d.text((DX + 256, y + 4), "仅选中（未选机器）", fill=C_MUTED, font=f_small)

y += 34
d.text((DX + 20, y), "被控端会弹出广播窗口：可调整大小，但无法自行关闭，",
       fill=C_MUTED, font=f_tiny)
d.text((DX + 20, y + 16), "只能由主控端点「结束广播」关闭。",
       fill=C_MUTED, font=f_tiny)

by = DY + DH - 52
rr([DX + 130, by, DX + 130 + 100, by + 32], 4, fill=C_BTN_BG)
tw = d.textlength("开始广播", font=f_btn)
d.text((DX + 130 + (100 - tw) / 2, by + 10), "开始广播", fill=C_BTN_FG, font=f_btn)
rr([DX + 240, by, DX + 240 + 90, by + 32], 4, fill=C_BTN_LIGHT)
tw = d.textlength("取消", font=f_btn)
d.text((DX + 240 + (90 - tw) / 2, by + 10), "取消", fill=C_BTN_BG, font=f_btn)

# 箭头：主控端 → 学生机
ax1, ax2 = DX + DW + 10, DX + DW + 66
d.line([(ax1, DY + 150), (ax2, DY + 150)], fill=C_ACCENT, width=3)
d.polygon([(ax2, DY + 144), (ax2, DY + 156), (ax2 + 14, DY + 150)], fill=C_ACCENT)
d.text((ax1 + 2, DY + 128), "广播画面", fill=C_ACCENT, font=f_small)

# ============================================================
# 右上：学生机桌面 + 广播窗口
# ============================================================
SX, SY, SW, SH = 520, 60, 570, 400

d.rectangle([SX, SY, SX + SW, SY + SH], fill=C_DESK)
for i in range(0, SW, 40):
    d.line([(SX + i, SY), (SX + i, SY + SH)], fill=(66, 100, 142), width=1)
d.rectangle([SX, SY + SH - 32, SX + SW, SY + SH], fill=C_TASKBAR)
d.text((SX + 10, SY + SH - 22), "学生机桌面 · 演示机-01", fill=(180, 200, 220),
       font=f_small)

# 广播窗口
VX, VY, VW, VH = SX + 70, SY + 40, 430, 300
d.rectangle([VX + 4, VY + 4, VX + VW + 4, VY + VH + 4], fill=(24, 34, 48))
d.rectangle([VX, VY, VX + VW, VY + VH], fill=(0, 0, 0), outline=C_TITLEBAR, width=2)

# 标题栏
d.rectangle([VX, VY, VX + VW, VY + 34], fill=C_TITLEBAR)
d.text((VX + 10, VY + 9), "📺  教师机演示", fill=C_WHITE,
       font=(f_small[0] if False else f(10)))
d.text((VX + VW - 150, VY + 11), "由主控端控制 · 无法自行关闭",
       fill=C_TIP, font=f_tiny)

# 画面区（模拟教师机屏幕内容）
px, py = VX + 2, VY + 36
pw, ph = VW - 4, VH - 36 - 26
d.rectangle([px, py, px + pw, py + ph], fill=(240, 244, 250))
# 画面里的"课件"示意
d.rectangle([px + 20, py + 20, px + pw - 20, py + 60], fill=(66, 165, 245))
d.text((px + 34, py + 32), "第三章  计算机网络基础", fill=C_WHITE, font=f_small)
for i in range(4):
    ly = py + 80 + i * 26
    d.rectangle([px + 20, ly, px + 20 + 260 - i * 40, ly + 10], fill=(176, 190, 205))
d.rectangle([px + pw - 130, py + 80, px + pw - 20, py + 170], fill=(255, 213, 79))
d.text((px + pw - 120, py + 118), "示意图", fill=(90, 70, 20), font=f_small)

# 底部状态栏
d.rectangle([VX, VY + VH - 26, VX + VW, VY + VH], fill=C_TITLEBAR)
d.text((VX + 10, VY + VH - 19),
       "1920×1080  ·  8 FPS  ·  拖动边框可调整大小  ·  只能由主控端结束",
       fill=C_TIP, font=f_tiny)

# 四个角的可调整大小把手
for (cx, cy) in [(VX, VY), (VX + VW, VY), (VX, VY + VH), (VX + VW, VY + VH)]:
    d.rectangle([cx - 4, cy - 4, cx + 4, cy + 4], fill=C_ACCENT)
d.text((VX + VW + 12, VY + 150), "↔\n可\n调\n整\n大\n小", fill=C_ACCENT, font=f_tiny)

# 关闭按钮被禁止（✕ 上打红圈斜杠）
xx, xy = VX + VW + 16, VY + 8
d.text((xx, xy), "✕", fill=C_MUTED, font=f_btn)
d.ellipse([xx - 6, xy - 2, xx + 22, xy + 22], outline=C_RED, width=2)
d.line([(xx - 4, xy + 20), (xx + 20, xy)], fill=C_RED, width=2)
d.text((xx + 30, xy + 4), "点击 ✕ / Alt+F4 均无效", fill=C_RED, font=f_tiny)

# ============================================================
# 底部：说明
# ============================================================
ty = SY + SH + 24
d.text((30, ty), "屏幕广播", fill=C_BTN_BG, font=(f_btn[0] if False else f(12)))
notes = [
    "· 主控端采集自己的屏幕 → 推给所有被控端（直播式，默认 8 FPS / 宽 1280px）",
    "· 被控端弹出广播窗口：可拖动边框调整大小，也可以最大化",
    "· 窗口无法自行关闭 —— 拦截 ✕ / Alt+F4 / Esc / Ctrl+W，只提示不关闭",
    "· 只有主控端点「结束广播」才会关闭（发 bc_quit + bc_stop 双保险）",
    "· 主控端崩溃或断线时，被控端检测到连接断开也会自动关窗，不留孤儿窗口",
    "· 只显示最新一帧，网络慢时丢弃旧帧，画面不会堆积延迟",
]
for i, n in enumerate(notes):
    d.text((40, ty + 26 + i * 19), n, fill=C_MUTED, font=f_small)

# 带宽提示
d.text((40, ty + 26 + len(notes) * 19 + 8),
       "带宽参考：8 FPS × 1280px ≈ 每台 0.5 MB/s，30 台约 15 MB/s（千兆局域网可承受）",
       fill=C_ACCENT, font=f_small)

out = os.path.join(os.path.dirname(__file__), "broadcast_preview.png")
img.save(out)
print(f"✓ 已生成屏幕广播效果图: {out}  ({W}x{H})")
