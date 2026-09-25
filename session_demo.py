"""
session_demo.py - 生成「设备详情」窗口效果图（含键鼠控制勾选框）
输出: session_preview.png
"""

import os
import time
from PIL import Image, ImageDraw, ImageFont

W, H = 1100, 760

# 蓝色主题
C_TITLEBAR = (21, 101, 192)
C_TITLEBAR_FG = (227, 242, 253)
C_APP_BG = (245, 249, 255)
C_ACCENT = (66, 165, 245)
C_TAB_ACTIVE = (255, 255, 255)
C_TAB_INACTIVE = (227, 238, 250)
C_BTN_BG = (232, 241, 251)
C_BTN_FG = (21, 101, 192)
C_TEXT_DARK = (55, 71, 79)
C_GREEN = (46, 125, 50)
C_SCREEN_BG = (13, 27, 51)

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
f_tab = f(10)
f_small = f(9)
f_tiny = f(8)
f_hud = f(10)

img = Image.new("RGB", (W, H), C_APP_BG)
d = ImageDraw.Draw(img)


def round_rect(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


# ============ 标题栏 ============
d.rectangle([0, 0, W, 36], fill=C_TITLEBAR)
d.text((14, 9), "🖥️  设备详情 - 演示机-01", fill=C_TITLEBAR_FG, font=f_title)
d.text((W - 260, 12), "192.168.1.101:9001   ·   Windows 11",
       fill=(187, 222, 251), font=f_small)

# ============ 设备操作区 ============
oy = 44
d.rectangle([10, oy, W - 10, oy + 74], fill=C_APP_BG, outline=C_ACCENT, width=1)
d.text((20, oy + 4), "设备操作", fill=C_BTN_FG, font=f_btn)

# 按钮单行居中
buttons = ["发送命令", "发送消息", "上传文件", "查看日志", "打开网址"]
BW, BH, BPAD = 104, 28, 10
total_w = len(buttons) * BW + (len(buttons) - 1) * BPAD
start_x = (W - total_w) // 2
for i, txt in enumerate(buttons):
    bx = start_x + i * (BW + BPAD)
    by = oy + 24
    round_rect(d, [bx, by, bx + BW, by + BH], 4, fill=C_BTN_BG)
    tw = d.textlength(txt, font=f_btn)
    d.text((bx + (BW - tw) / 2, by + 8), txt, fill=C_BTN_FG, font=f_btn)

# ============ 标签页 ============
ty = oy + 82
tabs = ["控制台", "文件浏览", "进程列表", "屏幕监控"]
active_idx = 3
TW = 120
tx = 10
for i, t in enumerate(tabs):
    active = (i == active_idx)
    top = C_TAB_ACTIVE if active else C_TAB_INACTIVE
    d.rectangle([tx, ty, tx + TW, ty + 30], fill=top, outline=(200, 215, 235))
    tc = C_BTN_FG if active else (120, 144, 156)
    tw = d.textlength(t, font=f_tab)
    d.text((tx + (TW - tw) / 2, ty + 9), t, fill=tc, font=f_tab)
    if active:
        d.rectangle([tx, ty, tx + TW, ty + 3], fill=C_ACCENT)
    tx += TW

# ============ 内容区 ============
cy0 = ty + 30
d.rectangle([10, cy0, W - 10, H - 60], fill=C_TAB_ACTIVE, outline=(200, 215, 235))

# ---- 控制条：勾选框 ----
cb_y = cy0 + 10
# 勾选框（已勾选）
d.rectangle([20, cb_y + 2, 34, cb_y + 16], fill=(227, 242, 253),
            outline=C_BTN_FG, width=2)
# 打勾
d.line([(23, cb_y + 9), (28, cb_y + 14)], fill=C_BTN_FG, width=2)
d.line([(28, cb_y + 14), (33, cb_y + 5)], fill=C_BTN_FG, width=2)
d.text((40, cb_y + 1), "🖱️ 控制鼠标键盘（勾选后可直接操作对方桌面）",
       fill=C_BTN_FG, font=f_btn)
d.text((W - 130, cb_y + 3), "● 控制已启用", fill=C_GREEN, font=f_small)

# ---- 屏幕画面区 ----
sx, sy = 20, cb_y + 28
sw, sh = W - 60, H - 60 - (cb_y + 28) - 10
d.rectangle([sx, sy, sx + sw, sy + sh], fill=C_SCREEN_BG)

# 画面内容：模拟一个桌面壁纸（16:9 居中）
aspect = 16 / 9
aw = sw
ah = int(aw / aspect)
if ah > sh:
    ah = sh
    aw = int(ah * aspect)
ax = sx + (sw - aw) // 2
ay = sy + (sh - ah) // 2

# 渐变壁纸
for i in range(ah):
    ratio = i / max(1, ah)
    r = int(255 * (0.98 - ratio * 0.25))
    g = int(140 + 60 * ratio)
    b = int(90 + 110 * ratio)
    d.line([(ax, ay + i), (ax + aw, ay + i)], fill=(r, g, b))

# 桌面元素：任务栏
tb_h = int(ah * 0.06)
d.rectangle([ax, ay + ah - tb_h, ax + aw, ay + ah], fill=(20, 28, 40))
# 开始按钮
d.rectangle([ax + 6, ay + ah - tb_h + 3, ax + 26, ay + ah - 3], fill=C_ACCENT)
# 几个窗口
d.rectangle([ax + int(aw*0.08), ay + int(ah*0.12),
             ax + int(aw*0.52), ay + int(ah*0.62)],
            fill=(250, 250, 252), outline=(180, 190, 205), width=1)
d.rectangle([ax + int(aw*0.08), ay + int(ah*0.12),
             ax + int(aw*0.52), ay + int(ah*0.12) + 20], fill=(21, 101, 192))
d.text((ax + int(aw*0.09), ay + int(ah*0.12) + 5), "文件资源管理器",
       fill=(255, 255, 255), font=f_tiny)

# 鼠标指针（表示正在被远程控制）
mx, my = ax + int(aw * 0.32), ay + int(ah * 0.4)
d.polygon([(mx, my), (mx + 14, my + 5), (mx + 7, my + 7), (mx + 5, my + 15)],
          fill=(255, 255, 255), outline=(30, 30, 30))

# HUD
d.text((sx + 8, sy + 8), "● 监控中  30 FPS  第1248帧",
       fill=(105, 240, 174), font=f_hud)
d.text((sx + 8, sy + 24), "被控端分辨率 1920x1080  ·  鼠标键盘已接管",
       fill=(144, 164, 174), font=f_tiny)

# ============ 底部执行按钮 ============
by2 = H - 44
bw2, bh2 = 80, 28
bx2 = W - 20 - bw2
round_rect(d, [bx2, by2, bx2 + bw2, by2 + bh2], 4, fill=C_TITLEBAR)
tw = d.textlength("执行", font=f_btn)
d.text((bx2 + (bw2 - tw) / 2, by2 + 8), "执行", fill=(255, 255, 255), font=f_btn)

out = os.path.join(os.path.dirname(__file__), "session_preview.png")
img.save(out)
print(f"✓ 已生成设备详情效果图: {out}  ({W}x{H})")
