"""
url_demo.py - 生成「打开网址」对话框效果图
输出: url_preview.png
"""

import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1100, 620

C_TITLEBAR = (21, 101, 192)
C_TITLEBAR_FG = (227, 242, 253)
C_APP_BG = (245, 249, 255)
C_ACCENT = (66, 165, 245)
C_BTN_BG = (232, 241, 251)
C_BTN_FG = (21, 101, 192)
C_TEXT = (55, 71, 79)
C_MUTED = (120, 144, 156)
C_GREEN = (46, 125, 50)
C_TERM_BG = (13, 27, 51)
C_TERM_GREEN = (200, 230, 201)
C_PROMPT = (100, 181, 246)
C_BORDER = (200, 215, 235)

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


# ============================================================
# 左半：主窗口（设备详情，控制台页）
# ============================================================
L_W = 660

d.rectangle([0, 0, L_W, 36], fill=C_TITLEBAR)
d.text((14, 9), "🖥️  设备详情 - 演示机-01", fill=C_TITLEBAR_FG, font=f_title)
d.text((L_W - 210, 12), "192.168.1.101:9001", fill=(187, 222, 251), font=f_small)

oy = 44
d.rectangle([10, oy, L_W - 10, oy + 96], fill=C_APP_BG, outline=C_ACCENT, width=1)
d.text((20, oy + 4), "设备操作", fill=C_BTN_FG, font=f_btn)

buttons = ["发送命令", "发送消息", "上传文件", "进程管理", "查看日志", "打开网址"]
BW, BH, BPAD = 92, 26, 7
total_w = len(buttons) * BW + (len(buttons) - 1) * BPAD
start_x = (L_W - total_w) // 2
for i, txt in enumerate(buttons):
    bx = start_x + i * (BW + BPAD)
    by = oy + 22
    active = (txt == "打开网址")
    round_rect([bx, by, bx + BW, by + BH], 4,
               fill=(C_ACCENT if active else C_BTN_BG))
    tw = d.textlength(txt, font=f_btn)
    d.text((bx + (BW - tw) / 2, by + 7), txt,
           fill=((255, 255, 255) if active else C_BTN_FG), font=f_btn)

crow = oy + 58
d.text((20, crow + 4), "命令:", fill=C_BTN_FG, font=f_btn)
ex = 62
ew = L_W - 62 - 92
d.rectangle([ex, crow + 1, ex + ew, crow + 25], fill=(255, 255, 255),
            outline=(190, 205, 225))
ebx = ex + ew + 8
round_rect([ebx, crow + 1, ebx + 66, crow + 25], 4, fill=C_TITLEBAR)
tw = d.textlength("执行", font=f_btn)
d.text((ebx + (66 - tw) / 2, crow + 7), "执行", fill=(255, 255, 255), font=f_btn)

# 标签页
ty = oy + 102
tabs = ["控制台", "文件浏览", "进程列表", "屏幕监控"]
TW = 100
tx = 10
for i, t in enumerate(tabs):
    active = (i == 0)
    top = (255, 255, 255) if active else (227, 238, 250)
    d.rectangle([tx, ty, tx + TW, ty + 28], fill=top, outline=C_BORDER)
    tc = C_BTN_FG if active else C_MUTED
    tw = d.textlength(t, font=f_btn)
    d.text((tx + (TW - tw) / 2, ty + 8), t, fill=tc, font=f_btn)
    if active:
        d.rectangle([tx, ty, tx + TW, ty + 3], fill=C_ACCENT)
    tx += TW

# 控制台输出
cy0 = ty + 28
term_y = cy0 + 10
term_h = H - 60 - term_y
d.rectangle([10, cy0, L_W - 10, H - 40], fill=(255, 255, 255), outline=C_BORDER)
d.rectangle([20, term_y, L_W - 20, term_y + term_h], fill=C_TERM_BG)

lines = [
    ("cmd", "> systeminfo | findstr /C:\"OS\""),
    ("out", "OS 名称:  Microsoft Windows 11 专业版"),
    ("blank", ""),
    ("ok", "✓ 打开网址: 已请求默认浏览器打开: https://www.baidu.com  [默认浏览器]"),
    ("blank", ""),
    ("cmd", "> tasklist | findstr chrome"),
    ("out", "chrome.exe   1204 Console   1   428,332 K"),
    ("out", "chrome.exe   3812 Console   1   312,708 K"),
]
ly = term_y + 10
for kind, text in lines:
    if ly > term_y + term_h - 14:
        break
    if kind == "blank":
        ly += 8
        continue
    color = {"cmd": C_PROMPT, "ok": C_TERM_GREEN,
             "out": C_TERM_GREEN}.get(kind, C_TERM_GREEN)
    d.text((32, ly), text, fill=color, font=f_mono)
    ly += 18

# ============================================================
# 右半：打开网址 对话框（浮层）
# ============================================================
DX, DY, DW, DH = 700, 90, 380, 250

# 阴影
d.rectangle([DX + 5, DY + 5, DX + DW + 5, DY + DH + 5], fill=(190, 200, 215))
d.rectangle([DX, DY, DX + DW, DY + DH], fill=C_APP_BG, outline=C_ACCENT, width=2)

# 对话框标题栏
d.rectangle([DX, DY, DX + DW, DY + 34], fill=C_TITLEBAR)
d.text((DX + 14, DY + 9), "打开网址（被控端）", fill=C_TITLEBAR_FG, font=f_title)

# 说明
d.text((DX + 20, DY + 48), "在被控端浏览器中打开网址",
       fill=C_BTN_FG, font=(f_btn[0] if False else f(10)))

# 网址输入
iy = DY + 78
d.text((DX + 20, iy + 4), "网址:", fill=C_BTN_FG, font=f_small)
d.rectangle([DX + 74, iy, DX + DW - 20, iy + 26], fill=(255, 255, 255),
            outline=(190, 205, 225))
d.text((DX + 82, iy + 6), "www.baidu.com", fill=(70, 90, 110), font=f_small)
cur = DX + 82 + d.textlength("www.baidu.com", font=f_small)
d.line([(cur, iy + 5), (cur, iy + 20)], fill=C_ACCENT, width=2)

# 浏览器选择
by = DY + 116
d.text((DX + 20, by + 4), "浏览器:", fill=C_BTN_FG, font=f_small)
round_rect([DX + 74, by, DX + 74 + 120, by + 26], 4, fill=(255, 255, 255),
           outline=(190, 205, 225))
d.text((DX + 84, by + 6), "默认浏览器", fill=C_TEXT, font=f_small)
# 下拉箭头
d.polygon([(DX + 74 + 108, by + 10), (DX + 74 + 114, by + 10),
           (DX + 74 + 111, by + 16)], fill=C_MUTED)
d.text((DX + 204, by + 6), "（指定浏览器需已安装）",
       fill=C_MUTED, font=(f_small[0] if False else f(8)))

# 最近
hy = DY + 154
d.text((DX + 20, hy + 4), "最近:", fill=C_MUTED, font=f_small)
d.rectangle([DX + 74, hy, DX + DW - 20, hy + 24], fill=(255, 255, 255),
            outline=(190, 205, 225))
d.text((DX + 82, hy + 5), "https://www.baidu.com", fill=(70, 90, 110),
       font=f_small)

# 提示
d.text((DX + 20, DY + 192), "不带协议自动补 https://  ·  仅支持 http/https/ftp/mailto/file",
       fill=C_MUTED, font=(f_small[0] if False else f(8)))

# 按钮
bny = DY + DH - 46
round_rect([DX + 150, bny, DX + 150 + 82, bny + 30], 4, fill=C_TITLEBAR)
tw = d.textlength("打开", font=f_btn)
d.text((DX + 150 + (82 - tw) / 2, bny + 9), "打开", fill=(255, 255, 255), font=f_btn)

round_rect([DX + 244, bny, DX + 244 + 82, bny + 30], 4, fill=C_BTN_BG)
tw = d.textlength("取消", font=f_btn)
d.text((DX + 244 + (82 - tw) / 2, bny + 9), "取消", fill=C_BTN_FG, font=f_btn)

# 底部注释
d.text((20, H - 26), "← 主窗口：控制台页显示执行结果",
       fill=C_MUTED, font=f_small)
d.text((DX, H - 26), "↑ 打开网址对话框", fill=C_MUTED, font=f_small)

out = os.path.join(os.path.dirname(__file__), "url_preview.png")
img.save(out)
print(f"✓ 已生成打开网址效果图: {out}  ({W}x{H})")
