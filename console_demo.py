"""
console_demo.py - 生成「控制台（远程命令）」页效果图
输出: console_preview.png
"""

import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1100, 760

C_TITLEBAR = (21, 101, 192)
C_TITLEBAR_FG = (227, 242, 253)
C_APP_BG = (245, 249, 255)
C_ACCENT = (66, 165, 245)
C_BTN_BG = (232, 241, 251)
C_BTN_FG = (21, 101, 192)
C_TAB_ACTIVE = (255, 255, 255)
C_TAB_INACTIVE = (227, 238, 250)
C_TEXT = (55, 71, 79)
C_MUTED = (120, 144, 156)
C_TERM_BG = (13, 27, 51)
C_GREEN = (200, 230, 201)
C_PROMPT = (100, 181, 246)
C_ERR = (239, 154, 154)
C_OK = (129, 199, 132)

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
f_mono = f(11)
f_tiny = f(8)

img = Image.new("RGB", (W, H), C_APP_BG)
d = ImageDraw.Draw(img)


def round_rect(box, radius, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


# ============ 标题栏 ============
d.rectangle([0, 0, W, 36], fill=C_TITLEBAR)
d.text((14, 9), "🖥️  设备详情 - 演示机-01", fill=C_TITLEBAR_FG, font=f_title)
d.text((W - 250, 12), "192.168.1.101:9001   ·   Windows 11",
       fill=(187, 222, 251), font=f_small)

# ============ 设备操作区 ============
oy = 44
d.rectangle([10, oy, W - 10, oy + 96], fill=C_APP_BG, outline=C_ACCENT, width=1)
d.text((20, oy + 4), "设备操作", fill=C_BTN_FG, font=f_btn)

buttons = ["发送命令", "发送消息", "上传文件", "进程管理", "查看日志", "打开网址"]
BW, BH, BPAD = 104, 28, 10
total_w = len(buttons) * BW + (len(buttons) - 1) * BPAD
start_x = (W - total_w) // 2
for i, txt in enumerate(buttons):
    bx = start_x + i * (BW + BPAD)
    by = oy + 24
    round_rect([bx, by, bx + BW, by + BH], 4, fill=C_BTN_BG)
    tw = d.textlength(txt, font=f_btn)
    d.text((bx + (BW - tw) / 2, by + 8), txt, fill=C_BTN_FG, font=f_btn)

# 命令输入行
crow = oy + 62
d.text((20, crow + 4), "命令:", fill=C_BTN_FG, font=f_btn)
ex = 62
ew = W - 62 - 100
d.rectangle([ex, crow + 1, ex + ew, crow + 25], fill=(255, 255, 255),
            outline=(190, 205, 225))
d.text((ex + 8, crow + 5), "ipconfig | findstr IPv4",
       fill=(70, 90, 110), font=f_small)
d.text((ex + 8, crow + 5), "ipconfig | findstr IPv4",
       fill=(70, 90, 110), font=f_small)
# 光标
cur_x = ex + 8 + d.textlength("ipconfig | findstr IPv4", font=f_small)
d.line([(cur_x, crow + 5), (cur_x, crow + 19)], fill=C_ACCENT, width=2)

# 执行按钮
ebx = ex + ew + 8
round_rect([ebx, crow + 1, ebx + 72, crow + 25], 4, fill=C_TITLEBAR)
tw = d.textlength("执行", font=f_btn)
d.text((ebx + (72 - tw) / 2, crow + 7), "执行", fill=(255, 255, 255), font=f_btn)

# ============ 标签页 ============
ty = oy + 102
tabs = ["控制台", "文件浏览", "进程列表", "屏幕监控"]
active_idx = 0
TW = 120
tx = 10
for i, t in enumerate(tabs):
    active = (i == active_idx)
    top = C_TAB_ACTIVE if active else C_TAB_INACTIVE
    d.rectangle([tx, ty, tx + TW, ty + 30], fill=top, outline=(200, 215, 235))
    tc = C_BTN_FG if active else C_MUTED
    tw = d.textlength(t, font=f_btn)
    d.text((tx + (TW - tw) / 2, ty + 9), t, fill=tc, font=f_btn)
    if active:
        d.rectangle([tx, ty, tx + TW, ty + 3], fill=C_ACCENT)
    tx += TW

# ============ 内容区 ============
cy0 = ty + 30
d.rectangle([10, cy0, W - 10, H - 60], fill=C_TAB_ACTIVE, outline=(200, 215, 235))

# ---- 头部：标题 + 清空 ----
hdr = cy0 + 10
d.text((24, hdr), "控制台输出", fill=C_BTN_FG, font=(f_btn[0] if False else f(10)))
bx2 = W - 24 - 56
round_rect([bx2, hdr - 2, bx2 + 56, hdr + 20], 4, fill=C_BTN_BG)
d.text((bx2 + 14, hdr + 2), "清空", fill=C_BTN_FG, font=f_small)

# ---- 常用命令 ----
qy = hdr + 28
d.text((24, qy + 2), "常用:", fill=C_MUTED, font=f_small)
qx = 66
for label in ["ipconfig / ifconfig", "系统信息", "当前目录", "进程列表"]:
    w = d.textlength(label, font=f_small) + 16
    round_rect([qx, qy, qx + w, qy + 20], 4, fill=C_BTN_BG)
    d.text((qx + 8, qy + 4), label, fill=C_BTN_FG, font=f_small)
    qx += w + 5

# ---- 终端区 ----
ty2 = qy + 30
th = H - 60 - ty2 - 8
d.rectangle([24, ty2, W - 44, ty2 + th], fill=C_TERM_BG)

lines = [
    ("cmd", "C:\\Users\\Student> ipconfig | findstr IPv4"),
    ("out", "   IPv4 地址 . . . . . . . . . . . . : 192.168.1.101"),
    ("out", "   子网掩码  . . . . . . . . . . . . : 255.255.255.0"),
    ("out", "   默认网关  . . . . . . . . . . . . : 192.168.1.1"),
    ("ok", "✓ (退出码 0)"),
    ("blank", ""),
    ("cmd", "C:\\Users\\Student> cd C:\\Windows\\System32"),
    ("ok", "✓ C:\\Windows\\System32"),
    ("blank", ""),
    ("cmd", "C:\\Users\\Student> systeminfo | findstr /C:\"操作系统\""),
    ("out", "操作系统名称:          Microsoft Windows 11 专业版"),
    ("out", "操作系统版本:          10.0.22631 暂缺 Build 22631"),
    ("ok", "✓ (退出码 0)"),
    ("blank", ""),
    ("cmd", "C:\\Users\\Student> SAFE_MODE_STATUS"),
    ("out", "保护状态: 保护已开启"),
    ("out", "（默认配置 SAFE_MODE=True，重启被控端后回到该值）"),
    ("ok", "✓ (退出码 0)"),
    ("blank", ""),
    ("cmd", "C:\\Users\\Student> notrealcmd"),
    ("err", "✗ 'notrealcmd' 不是内部或外部命令，也不是可运行的程序"),
    ("blank", ""),
    ("cmd", "C:\\Users\\Student> ▌"),
]

ly = ty2 + 10
for kind, text in lines:
    if ly > ty2 + th - 16:
        break
    if kind == "blank":
        ly += 8
        continue
    if kind == "cmd":
        color = C_PROMPT
    elif kind == "err":
        color = C_ERR
    elif kind == "ok":
        color = C_OK
    else:
        color = C_GREEN
    d.text((36, ly), text, fill=color, font=f_mono)
    ly += 19

# ---- 底部提示 ----
d.text((24, H - 52), "默认超时 30 秒   ·   ↑/↓ 翻历史命令   ·   cd 持久生效",
       fill=C_MUTED, font=f_small)

# ============ 底部执行按钮 ============
by2 = H - 44
bw2, bh2 = 80, 28
bx3 = W - 20 - bw2
round_rect([bx3, by2, bx3 + bw2, by2 + bh2], 4, fill=C_TITLEBAR)
tw = d.textlength("执行", font=f_btn)
d.text((bx3 + (bw2 - tw) / 2, by2 + 8), "执行", fill=(255, 255, 255), font=f_btn)

out = os.path.join(os.path.dirname(__file__), "console_preview.png")
img.save(out)
print(f"✓ 已生成控制台效果图: {out}  ({W}x{H})")
