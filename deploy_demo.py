"""
deploy_demo.py - 生成「一键部署」界面效果图
输出: deploy_preview.png
"""

import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1060, 780

C_TITLEBAR = (21, 101, 192)
C_TITLEBAR_FG = (227, 242, 253)
C_APP_BG = (245, 249, 255)
C_ACCENT = (66, 165, 245)
C_BTN = (21, 101, 192)
C_BTN_FG = (255, 255, 255)
C_BTN_LIGHT = (227, 242, 253)
C_TEXT = (55, 71, 79)
C_MUTED = (120, 144, 156)
C_BORDER = (200, 215, 235)
C_WHITE = (255, 255, 255)
C_OK = (46, 125, 50)
C_FAIL = (198, 40, 40)
C_RUN = (21, 101, 192)
C_PEND = (144, 164, 174)
C_GROUP = (232, 241, 251)

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
f_mono = f(10)
f_tiny = f(8)

img = Image.new("RGB", (W, H), C_APP_BG)
d = ImageDraw.Draw(img)


def rr(box, radius, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def group(x, y, w, h, title):
    """带标题的分组框"""
    d.rectangle([x, y, x + w, y + h], fill=C_GROUP, outline=C_BORDER)
    tw = d.textlength(title, font=f_small)
    d.rectangle([x + 8, y - 7, x + 8 + tw + 10, y + 8], fill=C_APP_BG)
    d.text((x + 13, y - 7), title, fill=C_TITLEBAR, font=f_small)
    return x + 10, y + 16


# ============ 窗口 ============
WX, WY, WW, WH = 30, 40, 620, 690

d.rectangle([WX + 5, WY + 5, WX + WW + 5, WY + WH + 5], fill=(190, 200, 215))
d.rectangle([WX, WY, WX + WW, WY + WH], fill=C_APP_BG, outline=C_ACCENT, width=2)
d.rectangle([WX, WY, WX + WW, WY + 34], fill=C_TITLEBAR)
d.text((WX + 14, WY + 9), "🚀  一键部署被控端", fill=C_TITLEBAR_FG, font=f_title)
d.text((WX + WW - 160, WY + 11), "通过 jcc.exe 远程执行", fill=(187, 222, 251),
       font=f_small)

y = WY + 46

# ---- 目标 IP ----
gx, gy = group(WX + 12, y, WW - 24, 96, " 目标 IP ")
d.text((gx, gy), "支持: 192.168.80.12 / 192.168.80.10-56，多个用逗号或换行分隔",
       fill=C_MUTED, font=f_tiny)
rr([gx + WW - 24 - 100, gy - 2, gx + WW - 24 - 10, gy + 18], 3, fill=C_BTN_LIGHT)
d.text((gx + WW - 24 - 92, gy + 2), "填本机网段", fill=C_TITLEBAR, font=f_tiny)

d.rectangle([gx, gy + 24, gx + WW - 24 - 10, gy + 66], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((gx + 8, gy + 32), "192.168.80.10-56", fill=(70, 90, 110), font=f_mono)
d.text((gx + 8, gy + 48), "192.168.80.100, 192.168.80.105",
       fill=(70, 90, 110), font=f_mono)

y += 116

# ---- 部署文件 ----
gx, gy = group(WX + 12, y, WW - 24, 108, " 部署文件 ")
d.text((gx, gy + 4), "被控端:", fill=C_TITLEBAR, font=f_small)
d.rectangle([gx + 60, gy, gx + WW - 24 - 60, gy + 24], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((gx + 68, gy + 6), "D:\\远控\\agent.exe", fill=(70, 90, 110), font=f_small)
rr([gx + WW - 24 - 52, gy + 1, gx + WW - 24 - 8, gy + 23], 3, fill=C_BTN_LIGHT)
d.text((gx + WW - 24 - 46, gy + 6), "选择", fill=C_TITLEBAR, font=f_tiny)

d.text((gx, gy + 36), "jcc.exe:", fill=C_TITLEBAR, font=f_small)
d.rectangle([gx + 60, gy + 32, gx + WW - 24 - 60, gy + 56], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((gx + 68, gy + 38), "D:\\远控\\jcc.exe", fill=(70, 90, 110), font=f_small)
rr([gx + WW - 24 - 52, gy + 33, gx + WW - 24 - 8, gy + 55], 3, fill=C_BTN_LIGHT)
d.text((gx + WW - 24 - 46, gy + 38), "选择", fill=C_TITLEBAR, font=f_tiny)

d.text((gx + 4, gy + 66), "✓ 已找到 jcc.exe: D:\\远控\\jcc.exe", fill=C_OK,
       font=f_tiny)

y += 128

# ---- 目标位置 ----
gx, gy = group(WX + 12, y, WW - 24, 82, " 目标位置 ")
d.text((gx, gy + 4), "目录:", fill=C_TITLEBAR, font=f_small)
d.rectangle([gx + 60, gy, gx + WW - 24 - 20, gy + 24], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((gx + 68, gy + 6), r"C:\ProgramData\RemoteAgent", fill=(70, 90, 110),
       font=f_small)

d.text((gx, gy + 36), "文件名:", fill=C_TITLEBAR, font=f_small)
d.rectangle([gx + 60, gy + 32, gx + 60 + 110, gy + 56], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((gx + 68, gy + 38), "agent.exe", fill=(70, 90, 110), font=f_small)
# 勾选框
d.rectangle([gx + 190, gy + 38, gx + 202, gy + 50], fill=C_WHITE,
            outline=C_TITLEBAR, width=2)
d.line([(gx + 192, gy + 44), (gx + 196, gy + 48), (gx + 204, gy + 38)],
       fill=C_TITLEBAR, width=2)
d.text((gx + 210, gy + 38), "部署后启动", fill=C_TEXT, font=f_small)

y += 102

# ---- 参数 ----
gx, gy = group(WX + 12, y, WW - 24, 52, " 参数 ")
d.text((gx, gy + 6), "并发:", fill=C_TITLEBAR, font=f_small)
d.rectangle([gx + 46, gy + 2, gx + 96, gy + 26], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((gx + 54, gy + 7), "10", fill=(70, 90, 110), font=f_small)
d.text((gx + 116, gy + 6), "超时(秒):", fill=C_TITLEBAR, font=f_small)
d.rectangle([gx + 178, gy + 2, gx + 228, gy + 26], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((gx + 186, gy + 7), "60", fill=(70, 90, 110), font=f_small)
d.text((gx + 240, gy + 8), "（单条命令的等待上限）", fill=C_MUTED, font=f_tiny)

y += 72

# ---- 进度表 ----
gx, gy = group(WX + 12, y, WW - 24, 150, " 进度 ")
cols = [("IP", 130), ("状态", 90), ("详情", 300)]
cx = gx
for name, cw in cols:
    d.rectangle([cx, gy, cx + cw, gy + 22], fill=C_BTN_LIGHT, outline=C_BORDER)
    tw = d.textlength(name, font=f_small)
    d.text((cx + (cw - tw) / 2, gy + 5), name, fill=C_TITLEBAR, font=f_small)
    cx += cw

rows = [
    ("192.168.80.10", "完成", "已部署并启动", C_OK),
    ("192.168.80.11", "完成", "已部署并启动", C_OK),
    ("192.168.80.12", "下载", "certutil -urlcache ...", C_RUN),
    ("192.168.80.13", "建目录", "mkdir ...", C_RUN),
    ("192.168.80.14", "待部署", "", C_PEND),
    ("192.168.80.66", "失败", "建目录失败: host unreachable", C_FAIL),
]
ry = gy + 22
for ip, stage, detail, color in rows:
    d.rectangle([gx, ry, gx + 520, ry + 20], fill=C_WHITE, outline=C_BORDER)
    d.text((gx + 6, ry + 4), ip, fill=C_TEXT, font=f_small)
    tw = d.textlength(stage, font=f_small)
    d.text((gx + 130 + (90 - tw) / 2, ry + 4), stage, fill=color, font=f_small)
    d.text((gx + 226, ry + 4), detail[:42], fill=C_MUTED, font=f_tiny)
    ry += 20

# 汇总
d.text((WX + 22, ry + 8), "进行中…  成功 2  ·  失败 1  ·  共 47", fill=C_RUN,
       font=f_small)

# ---- 按钮 ----
by = WY + WH - 48
rr([WX + 130, by, WX + 130 + 110, by + 32], 4, fill=C_BTN)
tw = d.textlength("开始部署", font=f_btn)
d.text((WX + 130 + (110 - tw) / 2, by + 10), "开始部署", fill=C_BTN_FG, font=f_btn)
rr([WX + 250, by, WX + 250 + 90, by + 32], 4, fill=C_BTN_LIGHT)
tw = d.textlength("停止", font=f_btn)
d.text((WX + 250 + (90 - tw) / 2, by + 10), "停止", fill=C_TITLEBAR, font=f_btn)
rr([WX + 350, by, WX + 350 + 90, by + 32], 4, fill=C_BTN_LIGHT)
tw = d.textlength("关闭", font=f_btn)
d.text((WX + 350 + (90 - tw) / 2, by + 10), "关闭", fill=C_TITLEBAR, font=f_btn)

# ============ 右侧：部署流程图 ============
RX = WX + WW + 40
d.text((RX, WY + 20), "部署原理", fill=C_TITLEBAR, font=f_title)

steps = [
    ("①", "主控端起临时 HTTP 服务", "把 agent.exe 暴露为\nhttp://主控IP:随机端口/agent.exe\n（只提供这一个文件）"),
    ("②", "jcc.exe 让目标机建目录", 'jcc.exe -ip 192.168.80.10-56 \\\n  -c mkdir "C:\\ProgramData\\RemoteAgent"'),
    ("③", "jcc.exe 让目标机下载", 'jcc.exe -ip ... -c certutil \\\n  -urlcache -split -f "http://.../agent.exe" \\\n  "C:\\ProgramData\\RemoteAgent\\agent.exe"'),
    ("④", "jcc.exe 让目标机启动", 'jcc.exe -ip ... -c start "" \\\n  "C:\\ProgramData\\RemoteAgent\\agent.exe"'),
]

sy = WY + 50
for num, title, cmd in steps:
    d.ellipse([RX, sy, RX + 24, sy + 24], fill=C_TITLEBAR)
    tw = d.textlength(num, font=f_small)
    d.text((RX + (24 - tw) / 2, sy + 6), num, fill=C_BTN_FG, font=f_small)
    d.text((RX + 34, sy + 5), title, fill=C_TEXT, font=f_small)
    # 命令块
    cy = sy + 28
    lines = cmd.split("\n")
    bh = len(lines) * 15 + 10
    d.rectangle([RX + 34, cy, RX + 380, cy + bh], fill=(13, 27, 51))
    for i, ln in enumerate(lines):
        d.text((RX + 42, cy + 5 + i * 15), ln, fill=(200, 230, 201), font=f_tiny)
    sy += 28 + bh + 16

# 说明
ty = sy + 4
notes = [
    "· jcc.exe 只能执行命令，不能直接传文件",
    "  → 所以先起 HTTP，让目标机用 certutil 自己拉",
    "· 不需要开共享、不需要目标机开权限",
    "· 每台独立并发（默认 10 台同时），失败不影响其它",
    "· 每步单独执行，进度表能看到卡在哪一步",
    "· 中途可停止：已开始的跑完，未开始的取消",
]
for i, n in enumerate(notes):
    d.text((RX, ty + i * 17), n, fill=C_MUTED, font=f_tiny)

out = os.path.join(os.path.dirname(__file__), "deploy_preview.png")
img.save(out)
print(f"✓ 已生成一键部署效果图: {out}  ({W}x{H})")
