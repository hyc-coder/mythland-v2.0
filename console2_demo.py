"""
console2_demo.py - 生成「控制台（命令 / 日志 双视图）」效果图
输出: console2_preview.png
"""

import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1100, 720

C_TITLEBAR = (21, 101, 192)
C_TITLEBAR_FG = (227, 242, 253)
C_APP_BG = (245, 249, 255)
C_ACCENT = (66, 165, 245)
C_BTN_BG = (232, 241, 251)
C_BTN_FG = (21, 101, 192)
C_TAB_ACTIVE = (255, 255, 255)
C_TAB_INACTIVE = (227, 238, 250)
C_MUTED = (120, 144, 156)
C_BORDER = (200, 215, 235)
C_TERM_BG = (13, 27, 51)
C_TERM_FG = (200, 230, 201)
C_PROMPT = (100, 181, 246)
C_OK = (129, 199, 132)
C_ERR = (239, 154, 154)
C_LOG_DIM = (144, 164, 174)

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

crow = oy + 62
d.text((20, crow + 4), "命令:", fill=C_BTN_FG, font=f_btn)
ex = 62
ew = W - 62 - 92
d.rectangle([ex, crow + 1, ex + ew, crow + 25], fill=(255, 255, 255),
            outline=(190, 205, 225))
ebx = ex + ew + 8
round_rect([ebx, crow + 1, ebx + 66, crow + 25], 4, fill=C_TITLEBAR)
tw = d.textlength("执行", font=f_btn)
d.text((ebx + (66 - tw) / 2, crow + 7), "执行", fill=(255, 255, 255), font=f_btn)

# ============ 标签页 ============
ty = oy + 102
tabs = ["控制台", "文件浏览", "进程列表", "屏幕监控"]
TW = 120
tx = 10
for i, t in enumerate(tabs):
    active = (i == 0)
    top = C_TAB_ACTIVE if active else C_TAB_INACTIVE
    d.rectangle([tx, ty, tx + TW, ty + 28], fill=top, outline=C_BORDER)
    tc = C_BTN_FG if active else C_MUTED
    tw = d.textlength(t, font=f_btn)
    d.text((tx + (TW - tw) / 2, ty + 8), t, fill=tc, font=f_btn)
    if active:
        d.rectangle([tx, ty, tx + TW, ty + 3], fill=C_ACCENT)
    tx += TW

cy0 = ty + 28
d.rectangle([10, cy0, W - 10, H - 60], fill=C_TAB_ACTIVE, outline=C_BORDER)

# ============ 视图切换栏 ============
vy = cy0 + 10

# 「💻 命令」高亮（当前视图）
b1w = 100
round_rect([24, vy, 24 + b1w, vy + 28], 4, fill=C_TITLEBAR)
d.text((24 + 14, vy + 8), "💻 命令", fill=(255, 255, 255), font=f_btn)

b2x = 24 + b1w + 6
b2w = 120
round_rect([b2x, vy, b2x + b2w, vy + 28], 4, fill=C_BTN_BG)
d.text((b2x + 14, vy + 8), "📄 被控端日志", fill=C_BTN_FG, font=f_btn)

# 右侧：清空
bx = W - 24 - 64
round_rect([bx, vy + 2, bx + 64, vy + 26], 4, fill=C_BTN_BG)
d.text((bx + 16, vy + 8), "清空", fill=C_BTN_FG, font=f_small)

# ============ 常用命令 ============
qy = vy + 34
d.text((24, qy + 2), "常用:", fill=C_MUTED, font=f_small)
qx = 66
for label in ["ipconfig / ifconfig", "系统信息", "当前目录", "进程列表"]:
    w = d.textlength(label, font=f_small) + 16
    round_rect([qx, qy, qx + w, qy + 20], 4, fill=C_BTN_BG)
    d.text((qx + 8, qy + 4), label, fill=C_BTN_FG, font=f_small)
    qx += w + 5

# ============ 终端区 ============
term_y = qy + 30
term_h = H - 74 - term_y
d.rectangle([24, term_y, W - 44, term_y + term_h], fill=C_TERM_BG)

lines = [
    ("dim", "远程控制台已就绪。"),
    ("dim", "在上方「命令」输入框输入命令，回车或点「执行」即可在被控端运行。"),
    ("dim", "内置指令: SAFE_MODE_STATUS / SAFE_MODE_OFF / SAFE_MODE_ON"),
    ("blank", ""),
    ("cmd", "C:\\Users\\Student> ipconfig | findstr IPv4"),
    ("out", "   IPv4 地址 . . . . . . . . . . . . : 192.168.1.101"),
    ("ok", "✓ (无输出，退出码 0)"),
    ("blank", ""),
    ("cmd", "C:\\Users\\Student> SAFE_MODE_STATUS"),
    ("out", "保护状态: 保护已开启"),
    ("ok", "✓ (退出码 0)"),
    ("blank", ""),
    ("cmd", "C:\\Users\\Student> notrealcmd"),
    ("err", "✗ 'notrealcmd' 不是内部或外部命令，也不是可运行的程序"),
    ("blank", ""),
    ("cmd", "C:\\Users\\Student> ▌"),
]

ly = term_y + 10
for kind, text in lines:
    if ly > term_y + term_h - 14:
        break
    if kind == "blank":
        ly += 8
        continue
    color = {"cmd": C_PROMPT, "out": C_TERM_FG, "ok": C_OK,
             "err": C_ERR, "dim": C_LOG_DIM}.get(kind, C_TERM_FG)
    d.text((36, ly), text, fill=color, font=f_mono)
    ly += 18

# ============ 底部提示 ============
d.text((24, H - 52),
       "在此执行命令并查看输出   ·   切换「被控端日志」看 agent.log   ·   ↑/↓ 翻历史命令",
       fill=C_MUTED, font=f_small)

# 右下角小图：日志视图示意
lx, ly0, lw, lh = W - 400, H - 152, 380, 100
d.rectangle([lx, ly0, lx + lw, ly0 + lh], fill=C_TERM_BG, outline=C_ACCENT, width=2)
d.rectangle([lx, ly0, lx + lw, ly0 + 22], fill=C_TITLEBAR)
d.text((lx + 10, ly0 + 5), "📄 被控端日志 (agent.log)",
       fill=(255, 255, 255), font=f_small)
log_lines = [
    "[Agent] 启动: 演示机-01 (Windows 11)",
    "[Agent] 广播上线: 演示机-01 -> 192.168.1.255:9086",
    "[Agent] TCP服务启动，监听端口 9001",
    "[Agent] 控制端连接: ('192.168.1.7', 52310)",
]
ly2 = ly0 + 28
for t in log_lines:
    if ly2 > ly0 + lh - 12:
        break
    d.text((lx + 10, ly2), t, fill=C_TERM_FG, font=(f_mono[0] if False else f(9)))
    ly2 += 16

out = os.path.join(os.path.dirname(__file__), "console2_preview.png")
img.save(out)
print(f"✓ 已生成控制台双视图效果图: {out}  ({W}x{H})")
