"""
preview_wall_demo.py - 渲染「v3 蓝色主题 + 可拖拽」预览墙效果图
输出: preview_wall.png
"""
import os
import time
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 760

# ===== 蓝色主题配色（与 controller.py 一致）=====
C_TITLEBAR    = (21, 101, 192)
C_TITLEBAR_FG = (227, 242, 253)
C_BG          = (13, 71, 161)
C_APP_BG      = (245, 249, 255)
C_CARD        = (25, 118, 210)
C_CARD_BORDER = (13, 71, 161)
C_ACCENT      = (66, 165, 245)
C_DRAG        = (255, 179, 0)
C_TEXT        = (255, 255, 255)
C_LED_ON      = (105, 240, 174)
C_LED_OFF     = (120, 144, 156)

THUMB_W, THUMB_H = 176, 110
CARD_W = THUMB_W + 12
CARD_H = THUMB_H + 58
COLS = 5
PAD = 12

machines = [
    ("教师机",    "192.168.1.100", "online"),
    ("学生机-01", "192.168.1.101", "online"),
    ("学生机-02", "192.168.1.102", "online"),
    ("学生机-03", "192.168.1.103", "online"),
    ("学生机-04", "192.168.1.104", "offline"),
    ("学生机-05", "192.168.1.105", "online"),
    ("学生机-06", "192.168.1.106", "online"),
    ("学生机-07", "192.168.1.107", "online"),
    ("学生机-08", "192.168.1.108", "online"),
    ("学生机-09", "192.168.1.109", "offline"),
    ("学生机-10", "192.168.1.110", "online"),
]
selected = "学生机-02"
dragging = "学生机-05"      # 演示拖拽态（琥珀色边框）

img = Image.new("RGB", (W, H), C_APP_BG)
draw = ImageDraw.Draw(img)

# 字体
font_path = None
for p in [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc",
]:
    if os.path.exists(p):
        font_path = p
        break
f = (lambda s: ImageFont.truetype(font_path, s)) if font_path else (lambda s: ImageFont.load_default())
font_title = f(15)
font_name = f(12)
font_small = f(10)
font_tip = f(11)


def hsv2rgb(h, s, v):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


# ===== 标题栏 =====
draw.rectangle([0, 0, W, 40], fill=C_TITLEBAR)
draw.text((16, 10), "🖥️  局域网远控 · 控制端", fill=C_TITLEBAR_FG, font=font_title)
draw.text((W - 250, 14), "卡片可拖拽排序 · 1 FPS 实时画面",
          fill=(187, 222, 251), font=font_small)

# ===== 工具栏 =====
draw.rectangle([0, 40, W, 88], fill=C_APP_BG)
for i, txt in enumerate(["刷新列表", "扫描网段", "停止轮询", "控制选中"]):
    bx = 12 + i * 96
    draw.rounded_rectangle([bx, 50, bx + 86, 76], radius=4, fill=C_TITLEBAR)
    draw.text((bx + 16, 57), txt, fill=(255, 255, 255), font=font_small)
# 状态标签
draw.rounded_rectangle([W - 190, 50, W - 14, 76], radius=4, fill=(227, 242, 253))
draw.text((W - 178, 57), "在线 9 / 11", fill=C_TITLEBAR, font=font_small)

# ===== 预览墙背景 =====
draw.rectangle([0, 88, W, H], fill=C_BG)

start_x, start_y = PAD, 100
for idx, (name, ip, status) in enumerate(machines):
    r, c = idx // COLS, idx % COLS
    x = start_x + c * (CARD_W + PAD)
    y = start_y + r * (CARD_H + PAD)

    is_sel = (name == selected)
    is_drag = (name == dragging)
    border = C_DRAG if is_drag else (C_ACCENT if is_sel else C_CARD_BORDER)
    bw = 4 if (is_sel or is_drag) else 2

    draw.rounded_rectangle([x, y, x + CARD_W, y + CARD_H], radius=6,
                           fill=C_CARD, outline=border, width=bw)

    # 顶部蓝色标题条（拖拽把手）
    draw.rectangle([x + 2, y + 2, x + CARD_W - 2, y + 20], fill=C_TITLEBAR)
    draw.text((x + 7, y + 5), "⋮⋮", fill=C_TITLEBAR_FG, font=font_small)

    # 缩略图
    tx, ty = x + 6, y + 24
    thumb = Image.new("RGB", (THUMB_W, THUMB_H), (13, 27, 51))
    td = ImageDraw.Draw(thumb)
    if status == "online":
        hue = (idx * 37) % 360 / 360.0
        td.rectangle([0, 0, THUMB_W, 16], fill=(21, 101, 192))
        for i, col in enumerate([(220, 60, 60), (60, 200, 90), (70, 130, 230), (240, 200, 60)]):
            bx0 = 8 + i * 40
            td.rectangle([bx0, 24, bx0 + 28, 52], fill=col)
        td.multiline_text((8, 60), f"{name}\n{time.strftime('%H:%M:%S')}",
                          fill=(230, 230, 230), font=font_small)
    else:
        td.text((THUMB_W // 2 - 26, THUMB_H // 2 - 8), "无信号",
                fill=(120, 144, 156), font=font_small)
    img.paste(thumb, (tx, ty))

    # 信息栏: 指示灯 + 名称/IP
    led_x, led_y = x + 8, y + THUMB_H + 32
    draw.ellipse([led_x, led_y, led_x + 10, led_y + 10],
                 fill=C_LED_ON if status == "online" else C_LED_OFF)
    draw.text((led_x + 16, y + THUMB_H + 27), name, fill=C_TEXT, font=font_name)
    draw.text((led_x + 16, y + THUMB_H + 43), ip, fill=(187, 222, 251), font=font_small)

# 底部说明
draw.text((16, H - 24),
          "蓝色主题 · 卡片可拖拽排序 · 1 FPS 实时桌面 · 零配置自动发现",
          fill=(187, 222, 251), font=font_tip)

out = os.path.join(os.path.dirname(__file__), "preview_wall.png")
img.save(out)
print(f"✓ 已生成蓝色主题效果图: {out}  ({W}x{H})")
