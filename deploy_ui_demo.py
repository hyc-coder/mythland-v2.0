# -*- coding: utf-8 -*-
"""
deploy_ui_demo.py - 渲染「一键部署」对话框效果图（v2 美化版）

输出: deploy_ui_preview.png
风格与主控制台（controller.py）完全一致：蓝色主题 + 圆角卡片
"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1180, 820
out = os.path.join(os.path.dirname(__file__), "deploy_ui_preview.png")

# ===== 蓝色主题（与 controller.py / deploy_ui.py 一致）=====
C_BG          = (13, 71, 161)      # 外层桌面背景（深蓝）
C_TITLEBAR    = (21, 101, 192)
C_TITLEBAR_FG = (227, 242, 253)
C_APP_BG      = (245, 249, 255)
C_GROUP_BG    = (238, 245, 255)
C_ACCENT      = (66, 165, 245)
C_BTN_BG      = (21, 101, 192)
C_BTN_FG      = (255, 255, 255)
C_BTN_LIGHT   = (227, 242, 253)
C_TEXT        = (55, 71, 79)
C_MUTED       = (120, 144, 156)
C_BORDER      = (200, 215, 235)
C_INPUT       = (255, 255, 255)
C_OK          = (46, 125, 50)
C_FAIL        = (198, 40, 40)
C_RUN         = (21, 101, 192)
C_PEND        = (144, 164, 174)
C_WARN        = (230, 81, 0)

FONT_PATH = None
for p in ["/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
          "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc"]:
    if os.path.exists(p):
        FONT_PATH = p
        break
mk = (lambda s: ImageFont.truetype(FONT_PATH, s)) if FONT_PATH else (lambda s: ImageFont.load_default())

f_title  = mk(15)
f_btn    = mk(11)
f_small  = mk(10)
f_tiny   = mk(9)
f_mono   = mk(11)
f_link   = mk(9)

img = Image.new("RGB", (W, H), C_BG)
d = ImageDraw.Draw(img)


def rr(box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


# ============ 窗口 ============
WX, WY, WW, WH = 120, 50, 700, 720
# 阴影
d.rounded_rectangle([WX + 4, WY + 4, WX + WW + 4, WY + WH + 4], radius=8, fill=(0, 0, 0, 40))
# 窗体
rr([WX, WY, WX + WW, WY + WH], 8, fill=C_APP_BG, outline=C_ACCENT, width=2)
# 标题栏（仅顶部两角圆角）
d.rounded_rectangle([WX, WY, WX + WW, WY + 42], radius=8, fill=C_TITLEBAR)
d.rectangle([WX, WY + 26, WX + WW, WY + 42], fill=C_TITLEBAR)  # 遮住下圆角→方角
d.text((WX + 16, WY + 12), "一键部署", fill=C_TITLEBAR_FG, font=f_title)
d.text((WX + 118, WY + 17), "通过 jcc.exe 远程执行 · 批量安装被控端", fill=(187, 222, 251), font=f_tiny)
d.text((WX + WW - 34, WY + 10), "✕", fill=C_TITLEBAR_FG, font=f_btn)

y = WY + 58

# ---- 分组框工具 ----
def group_header(y, title):
    """圆角分组：标题嵌在边线上"""
    gx, gw = WX + 16, WW - 32
    gh = 0  # 由调用方确定
    # 先画边框（占位，实际在内容区画）
    return gx, gw

def field_label(y, label, value, btn="选择…", value_w=None):
    gx = WX + 30
    d.text((gx, y + 4), label, fill=C_TITLEBAR, font=f_small)
    vw = value_w or (WW - 30 - 92 - 70)
    rr([gx + 62, y, gx + 62 + vw, y + 26], 4, fill=C_INPUT, outline=C_BORDER, width=1)
    d.text((gx + 70, y + 7), value, fill=C_TEXT, font=f_small)
    bx = gx + 62 + vw + 8
    rr([bx, y + 2, bx + 52, y + 24], 4, fill=C_BTN_LIGHT)
    d.text((bx + 10, y + 7), btn, fill=C_TITLEBAR, font=f_tiny)
    return y + 34

# ---- 1. 目标 IP ----
gx = WX + 16
d.text((gx + 8, y + 2), "目标 IP", fill=C_TITLEBAR, font=f_small)
d.line([(gx, y + 20), (gx + 8, y + 20)], fill=C_TITLEBAR, width=2)
d.line([(gx + 70, y + 20), (gx + WW - 32, y + 20)], fill=C_BORDER, width=1)
y += 28
d.text((gx + 10, y), "支持: 单个IP (192.168.80.12)、IP范围 (192.168.80.10-56)，多个用逗号或换行分隔",
       fill=C_MUTED, font=f_tiny)
d.text((gx + WW - 32 - 78, y + 2), "本机网段", fill=C_TITLEBAR, font=f_link)
d.text((gx + WW - 32 - 78 - 8 - 92, y + 2), "全段扫描 1-254", fill=C_TITLEBAR, font=f_link)
y += 22
rr([gx + 10, y, gx + WW - 26, y + 52], 4, fill=C_INPUT, outline=C_BORDER, width=1)
for i, line in enumerate(["192.168.80.10-56", "192.168.80.100, 192.168.80.105"]):
    d.text((gx + 20, y + 8 + i * 18), line, fill=C_TEXT, font=f_mono)
y += 64

# ---- 2. 部署文件 ----
d.text((gx + 8, y + 2), "部署文件", fill=C_TITLEBAR, font=f_small)
d.line([(gx, y + 20), (gx + 8, y + 20)], fill=C_TITLEBAR, width=2)
d.line([(gx + 78, y + 20), (gx + WW - 32, y + 20)], fill=C_BORDER, width=1)
y += 28
y = field_label(y, "被控端:", r"D:\远控\被控端.exe")
y = field_label(y, "jcc.exe:", r"D:\远控\jcc.exe")
d.text((gx + 72, y), "✓ 已找到 jcc.exe：D:\远控\jcc.exe", fill=C_OK, font=f_tiny)
y += 24

# ---- 3. 目标位置 ----
d.text((gx + 8, y + 2), "目标位置", fill=C_TITLEBAR, font=f_small)
d.line([(gx, y + 20), (gx + 8, y + 20)], fill=C_TITLEBAR, width=2)
d.line([(gx + 78, y + 20), (gx + WW - 32, y + 20)], fill=C_BORDER, width=1)
y += 28
y = field_label(y, "目录:", r"C:\ProgramData\RemoteAgent")
d.text((gx + 10, y + 4), "文件名:", fill=C_TITLEBAR, font=f_small)
rr([gx + 72, y, gx + 72 + 130, y + 26], 4, fill=C_INPUT, outline=C_BORDER)
d.text((gx + 80, y + 7), "agent.exe", fill=C_TEXT, font=f_small)
# 勾选框
cx = gx + 220
rr([cx, y + 5, cx + 14, y + 19], 3, fill=C_BTN_BG)
d.line([(cx + 3, y + 12), (cx + 6, y + 15), (cx + 11, y + 7)], fill=(255, 255, 255), width=2)
d.text((cx + 22, y + 7), "部署后自动启动", fill=C_TEXT, font=f_small)
y += 38

# ---- 4. 参数 ----
d.text((gx + 8, y + 2), "参数", fill=C_TITLEBAR, font=f_small)
d.line([(gx, y + 20), (gx + 8, y + 20)], fill=C_TITLEBAR, width=2)
d.line([(gx + 50, y + 20), (gx + WW - 32, y + 20)], fill=C_BORDER, width=1)
y += 28
d.text((gx + 10, y + 5), "并发:", fill=C_TITLEBAR, font=f_small)
rr([gx + 52, y + 1, gx + 52 + 50, y + 23], 4, fill=C_INPUT, outline=C_BORDER)
d.text((gx + 62, y + 6), "10", fill=C_TEXT, font=f_small)
d.text((gx + 116, y + 5), "超时(秒):", fill=C_TITLEBAR, font=f_small)
rr([gx + 178, y + 1, gx + 178 + 50, y + 23], 4, fill=C_INPUT, outline=C_BORDER)
d.text((gx + 188, y + 6), "60", fill=C_TEXT, font=f_small)
d.text((gx + 240, y + 7), "（单台每步等待上限）", fill=C_MUTED, font=f_tiny)
y += 36

# ---- 5. 部署进度 ----
d.text((gx + 8, y + 2), "部署进度", fill=C_TITLEBAR, font=f_small)
d.line([(gx, y + 20), (gx + 8, y + 20)], fill=C_TITLEBAR, width=2)
d.line([(gx + 78, y + 20), (gx + WW - 32, y + 20)], fill=C_BORDER, width=1)
y += 28
tbl_x = gx + 10
tbl_w = WW - 36
cols = [("IP 地址", 150), ("状态", 100), ("详情", tbl_w - 250)]
cx = tbl_x
for name, cw in cols:
    rr([cx, y, cx + cw, y + 24], 0, fill=C_BTN_LIGHT)
    tw = d.textlength(name, font=f_small)
    d.text((cx + (cw - tw) / 2, y + 6), name, fill=C_TITLEBAR, font=f_small)
    cx += cw
y += 24

rows = [
    ("192.168.80.10", "已完成",   "已部署并启动",                C_OK),
    ("192.168.80.11", "已完成",   "已部署并启动",                C_OK),
    ("192.168.80.12", "下载文件", "certutil -urlcache -split…",  C_RUN),
    ("192.168.80.13", "创建目录", "mkdir C:\ProgramData\…",      C_RUN),
    ("192.168.80.14", "等待中",   "",                            C_PEND),
    ("192.168.80.66", "失败",     "建目录失败: host unreachable", C_FAIL),
]
for ip, stage, detail, color in rows:
    cx = tbl_x
    cells = [(ip, 150), (stage, 100), (detail, tbl_w - 250)]
    for text, cw in cells:
        if cx == tbl_x + 150 + 100:  # 状态列居中 + 着色
            tw = d.textlength(text, font=f_small)
            d.text((cx + (cw - tw) / 2, y + 5), text, fill=color, font=f_small)
        else:
            d.text((cx + 8, y + 5), text[:34], fill=color if cx == tbl_x else C_MUTED, font=f_small)
        cx += cw
    y += 22
y += 4
d.text((gx + 10, y), "进行中…  成功 2  ·  失败 1  ·  共 47", fill=C_RUN, font=f_small)
y += 30

# ---- 按钮 ----
by = WY + WH - 56
rr([WX + 20, by, WX + 20 + 150, by + 36], 6, fill=C_BTN_BG)
t = "🚀  开始部署"
tw = d.textlength(t, font=f_btn)
d.text((WX + 20 + (150 - tw) / 2, by + 11), t, fill=C_BTN_FG, font=f_btn)
rr([WX + 186, by, WX + 186 + 90, by + 36], 6, fill=C_BTN_LIGHT)
t = "⏹  停止"
tw = d.textlength(t, font=f_btn)
d.text((WX + 186 + (90 - tw) / 2, by + 11), t, fill=C_TITLEBAR, font=f_btn)
rr([WX + WW - 20 - 80, by, WX + WW - 20, by + 36], 6, fill=C_BTN_LIGHT)
t = "关闭"
tw = d.textlength(t, font=f_btn)
d.text((WX + WW - 20 - 80 + (80 - tw) / 2, by + 11), t, fill=C_TITLEBAR, font=f_btn)

# ============ 右侧：说明 ============
RX = WX + WW + 60
d.text((RX, WY + 20), "界面说明", fill=C_TITLEBAR_FG, font=f_title)
notes = [
    ("① 标题栏", "蓝色条 + ✕ 关闭，与主控端一致"),
    ("② 目标 IP", "支持单 IP / 范围 / 逗号分隔，一键填本机网段"),
    ("③ 部署文件", "自动探测同目录 exe，未找到红字提示"),
    ("④ 目标位置", "远程目录 + 文件名，可选部署后启动"),
    ("⑤ 参数", "并发数（默认 10）+ 超时（默认 60s）"),
    ("⑥ 部署进度", "每台一行：IP / 状态 / 详情，实时刷新"),
    ("⑦ 按钮", "开始部署(主色) / 停止 / 关闭"),
]
ny = WY + 56
for title, desc in notes:
    d.ellipse([RX, ny + 2, RX + 20, ny + 22], fill=C_ACCENT)
    d.text((RX + 26, ny + 3), title, fill=(255, 255, 255), font=f_small)
    # 换行描述
    words = desc
    d.text((RX + 26, ny + 22), words, fill=(200, 215, 235), font=f_tiny)
    ny += 52

ny += 8
d.rounded_rectangle([RX, ny, RX + 300, ny + 130], 8, fill=(13, 27, 51))
lines = [
    "部署流程（后台自动执行）:",
    "",
    "1. 主控端起临时 HTTP 服务",
    "2. jcc → mkdir 目标目录",
    "3. jcc → certutil 下载 exe",
    "4. jcc → start 启动被控端",
]
for i, ln in enumerate(lines):
    col = (255, 255, 255) if i == 0 else (160, 220, 170)
    d.text((RX + 14, ny + 12 + i * 17), ln, fill=col, font=f_tiny)
ny += 150

d.text((RX, ny), "· 状态颜色：绿色完成 / 蓝色进行中 /", fill=(200, 215, 235), font=f_tiny)
d.text((RX, ny + 17), "  红色失败 / 灰色等待", fill=(200, 215, 235), font=f_tiny)

img.save(out)
print(f"✓ 已生成部署界面效果图: {out}  ({W}x{H})")
