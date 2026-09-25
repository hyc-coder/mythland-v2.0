"""
files_demo.py - 生成「文件浏览」页效果图
输出: files_preview.png
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
C_GREEN = (46, 125, 50)
C_GREEN_LIGHT = (232, 245, 233)
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
    active = (txt == "上传文件")
    round_rect([bx, by, bx + BW, by + BH], 4,
               fill=(C_ACCENT if active else C_BTN_BG))
    tw = d.textlength(txt, font=f_btn)
    d.text((bx + (BW - tw) / 2, by + 8), txt,
           fill=((255, 255, 255) if active else C_BTN_FG), font=f_btn)

# ============ 标签页 ============
ty = oy + 82
tabs = ["控制台", "文件浏览", "进程列表", "屏幕监控"]
active_idx = 1
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

# ---- 路径栏 ----
top_y = cy0 + 10
bx = 24


def small_btn(x, text, bg, fg):
    w = d.textlength(text, font=f_small) + 20
    round_rect([x, top_y, x + w, top_y + 24], 4, fill=bg)
    d.text((x + 10, top_y + 6), text, fill=fg, font=f_small)
    return x + w + 6


bx = small_btn(bx, "↑ 上级", C_BTN_BG, C_BTN_FG)
bx = small_btn(bx, "🏠 根目录", C_BTN_BG, C_BTN_FG)
bx = small_btn(bx, "刷新", C_BTN_BG, C_BTN_FG)

# 路径输入框
px = bx + 4
pw = W - 24 - px - 60
d.rectangle([px, top_y + 1, px + pw, top_y + 23], fill=(255, 255, 255),
            outline=(190, 205, 225))
d.text((px + 8, top_y + 6), "C:\\Users\\Student\\Documents",
       fill=(70, 90, 110), font=f_small)
bx = small_btn(px + pw + 6, "转到", C_BTN_BG, C_BTN_FG)

# ---- 操作按钮 ----
bar_y = top_y + 32
bx = 24
bx = small_btn(bx, "⬆ 上传文件", C_BTN_BG, C_BTN_FG)
bx = small_btn(bx, "⬇ 下载", C_GREEN_LIGHT, C_GREEN)
bx = small_btn(bx, "新建文件夹", C_BTN_BG, C_BTN_FG)
bx = small_btn(bx, "删除", C_RED, (255, 255, 255))

# ---- 表格 ----
tbl_y = bar_y + 34
tbl_x, tbl_w = 24, W - 68
row_h = 26

cols = [("名称", 400, "w"), ("大小", 120, "center"),
        ("修改时间", 170, "center"), ("类型", 110, "center")]

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

# 数据
rows = [
    ("..", "", "", "上级目录", True, False),
    ("作业", "", "2026-09-10 14:22", "文件夹", True, False),
    ("课件", "", "2026-09-08 09:15", "文件夹", True, False),
    ("图片", "", "2026-09-01 16:40", "文件夹", True, False),
    ("实验报告.docx", "245.3 KB", "2026-09-14 10:33", "文件", False, True),
    ("期末复习.pdf", "1.8 MB", "2026-09-13 21:07", "文件", False, False),
    ("成绩单.xlsx", "32.6 KB", "2026-09-12 15:48", "文件", False, False),
    ("笔记.txt", "8.1 KB", "2026-09-11 20:12", "文件", False, False),
    ("演示稿.pptx", "5.4 MB", "2026-09-09 11:26", "文件", False, False),
    ("照片.jpg", "2.2 MB", "2026-09-05 13:55", "文件", False, False),
    ("backup.zip", "48.7 MB", "2026-09-02 08:30", "文件", False, False),
    ("readme.md", "1.2 KB", "2026-08-28 17:20", "文件", False, False),
]

for i, (name, size, mtime, kind, is_dir, selected) in enumerate(rows):
    ry = tbl_y + row_h + i * row_h
    if ry + row_h > H - 70:
        break
    bg = (187, 222, 251) if selected else (C_ROW_ALT if i % 2 == 0 else (255, 255, 255))
    d.rectangle([tbl_x, ry, tbl_x + tbl_w, ry + row_h], fill=bg, outline=C_GRID)

    cx = tbl_x
    vals = [name, size, mtime, kind]
    for j, (val, (cname, cw, anchor)) in enumerate(zip(vals, cols)):
        if j == 0:
            icon = "📁 " if is_dir else "📄 "
            txt = icon + val
            fg = C_BTN_FG if is_dir else C_TEXT
        else:
            txt = val
            fg = C_MUTED if is_dir else C_TEXT
        tw = d.textlength(txt, font=f_cell)
        if anchor == "center":
            d.text((cx + (cw - tw) / 2, ry + 6), txt, fill=fg, font=f_cell)
        else:
            d.text((cx + 10, ry + 6), txt, fill=fg, font=f_cell)
        if j < len(cols) - 1:
            d.line([(cx + cw, ry), (cx + cw, ry + row_h)], fill=C_GRID)
        cx += cw

# ---- 底部状态 ----
sy = H - 52
d.text((24, sy), "共 12 项   ·   C:\\Users\\Student\\Documents   "
                 "·   选中: 实验报告.docx (245.3 KB)",
       fill=(96, 125, 139), font=f_small)

# ============ 底部执行按钮 ============
by2 = H - 44
bw2, bh2 = 80, 28
bx2 = W - 20 - bw2
round_rect([bx2, by2, bx2 + bw2, by2 + bh2], 4, fill=C_TITLEBAR)
tw = d.textlength("执行", font=f_btn)
d.text((bx2 + (bw2 - tw) / 2, by2 + 8), "执行", fill=(255, 255, 255), font=f_btn)

out = os.path.join(os.path.dirname(__file__), "files_preview.png")
img.save(out)
print(f"✓ 已生成文件浏览效果图: {out}  ({W}x{H})")
