"""
process_demo.py - 生成「进程管理」页效果图
输出: process_preview.png
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
C_RED = (198, 40, 40)
C_RED_LIGHT = (255, 235, 238)
C_ROW_ALT = (245, 249, 255)
C_GRID = (215, 228, 242)
C_TEXT = (55, 71, 79)
C_MUTED = (120, 144, 156)

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
f_cell = f(10)
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
d.rectangle([10, oy, W - 10, oy + 74], fill=C_APP_BG, outline=C_ACCENT, width=1)
d.text((20, oy + 4), "设备操作", fill=C_BTN_FG, font=f_btn)

buttons = ["发送命令", "发送消息", "上传文件", "进程管理", "查看日志", "打开网址"]
BW, BH, BPAD = 104, 28, 10
total_w = len(buttons) * BW + (len(buttons) - 1) * BPAD
start_x = (W - total_w) // 2
for i, txt in enumerate(buttons):
    bx = start_x + i * (BW + BPAD)
    by = oy + 24
    # 「进程管理」高亮（当前所在页）
    active = (txt == "进程管理")
    round_rect([bx, by, bx + BW, by + BH], 4,
               fill=(C_ACCENT if active else C_BTN_BG))
    tw = d.textlength(txt, font=f_btn)
    d.text((bx + (BW - tw) / 2, by + 8), txt,
           fill=((255, 255, 255) if active else C_BTN_FG), font=f_btn)

# ============ 标签页 ============
ty = oy + 82
tabs = ["控制台", "文件浏览", "进程列表", "屏幕监控"]
active_idx = 2
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

# ---- 进程页工具栏 ----
bar_y = cy0 + 10
bx = 24

def small_btn(x, text, bg, fg):
    w = d.textlength(text, font=f_small) + 22
    round_rect([x, bar_y, x + w, bar_y + 24], 4, fill=bg)
    d.text((x + 11, bar_y + 6), text, fill=fg, font=f_small)
    return x + w + 8

bx = small_btn(bx, "刷新", C_BTN_BG, C_BTN_FG)
bx = small_btn(bx, "结束进程", C_RED_LIGHT, C_RED)
bx = small_btn(bx, "强制结束", C_RED, (255, 255, 255))

# 搜索框
d.text((bx + 8, bar_y + 6), "搜索:", fill=C_BTN_FG, font=f_small)
sx = bx + 44
d.rectangle([sx, bar_y + 1, sx + 120, bar_y + 23], fill=(255, 255, 255),
            outline=(190, 205, 225))
d.text((sx + 6, bar_y + 6), "chrome", fill=(150, 165, 180), font=f_small)

# 自动刷新勾选框
cbx = sx + 140
d.rectangle([cbx, bar_y + 5, cbx + 14, bar_y + 19], fill=(227, 242, 253),
            outline=C_BTN_FG, width=2)
d.line([(cbx + 3, bar_y + 12), (cbx + 6, bar_y + 15)], fill=C_BTN_FG, width=2)
d.line([(cbx + 6, bar_y + 15), (cbx + 11, bar_y + 6)], fill=C_BTN_FG, width=2)
d.text((cbx + 20, bar_y + 6), "自动刷新(3秒)", fill=C_BTN_FG, font=f_small)

# ---- 表格 ----
tbl_y = bar_y + 34
tbl_x, tbl_w = 24, W - 68
row_h = 26

cols = [("PID", 70, "center"), ("进程名称", 300, "w"),
        ("CPU %", 90, "center"), ("内存 MB", 110, "center"),
        ("状态", 110, "center")]

# 表头
d.rectangle([tbl_x, tbl_y, tbl_x + tbl_w, tbl_y + row_h],
            fill=(232, 241, 251), outline=C_GRID)
cx = tbl_x
for name, cw, _a in cols:
    d.line([(cx, tbl_y), (cx, tbl_y + row_h)], fill=C_GRID)
    tw = d.textlength(name, font=f_cell)
    d.text((cx + (cw - tw) / 2, tbl_y + 6), name, fill=C_BTN_FG, font=f_cell)
    cx += cw
d.line([(cx, tbl_y), (cx, tbl_y + row_h)], fill=C_GRID)

# 数据行
rows = [
    ("1204", "chrome.exe", "12.5", "428.3", "running"),
    ("3812", "chrome.exe", "8.2", "312.7", "running"),
    ("556", "explorer.exe", "1.1", "98.4", "running"),
    ("2890", "notepad.exe", "0.3", "24.6", "running"),
    ("4410", "StudentMain.exe", "3.8", "156.2", "running"),
    ("1024", "python.exe", "0.9", "86.5", "running"),
    ("778", "svchost.exe", "0.4", "52.1", "running"),
    ("912", "msedge.exe", "5.6", "264.8", "running"),
    ("334", "winlogon.exe", "0.1", "18.3", "running"),
    ("1902", "SearchApp.exe", "0.7", "74.9", "running"),
    ("88", "csrss.exe", "0.2", "12.7", "running"),
    ("2156", "Teams.exe", "2.4", "198.3", "running"),
    ("4002", "WeChat.exe", "1.8", "176.4", "running"),
    ("610", "dwm.exe", "1.5", "64.2", "running"),
    ("3358", "Spotify.exe", "0.6", "142.8", "running"),
]

sel_row = 4   # 高亮选中行（StudentMain.exe）
for i, row in enumerate(rows):
    ry = tbl_y + row_h + i * row_h
    if ry + row_h > H - 70:
        break
    selected = (i == sel_row)
    bg = (187, 222, 251) if selected else (
        C_ROW_ALT if i % 2 == 0 else (255, 255, 255))
    d.rectangle([tbl_x, ry, tbl_x + tbl_w, ry + row_h], fill=bg, outline=C_GRID)

    cx = tbl_x
    for j, (val, cw, anchor) in enumerate(zip(row, [c[1] for c in cols],
                                              [c[2] for c in cols])):
        fg = C_TEXT
        if j == 0:
            fg = C_BTN_FG
        elif j == 2 and float(val) > 5:
            fg = C_RED      # CPU 占用高的标红
        tw = d.textlength(val, font=f_cell)
        if anchor == "center":
            d.text((cx + (cw - tw) / 2, ry + 6), val, fill=fg, font=f_cell)
        else:
            d.text((cx + 10, ry + 6), val, fill=fg, font=f_cell)
        if j < len(cols) - 1:
            d.line([(cx + cw, ry), (cx + cw, ry + row_h)], fill=C_GRID)
        cx += cw

# ---- 底部状态 ----
sy = H - 52
d.text((24, sy), "共 86 个进程   ·   采集方式: psutil（完整信息）   "
                 "·   选中: StudentMain.exe (PID 4410)",
       fill=(96, 125, 139), font=f_small)

# ============ 底部执行按钮 ============
by2 = H - 44
bw2, bh2 = 80, 28
bx2 = W - 20 - bw2
round_rect([bx2, by2, bx2 + bw2, by2 + bh2], 4, fill=C_TITLEBAR)
tw = d.textlength("执行", font=f_btn)
d.text((bx2 + (bw2 - tw) / 2, by2 + 8), "执行", fill=(255, 255, 255), font=f_btn)

out = os.path.join(os.path.dirname(__file__), "process_preview.png")
img.save(out)
print(f"✓ 已生成进程管理效果图: {out}  ({W}x{H})")
