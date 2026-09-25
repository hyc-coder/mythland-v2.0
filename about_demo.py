# -*- coding: utf-8 -*-
"""
about_demo.py - 渲染「关于软件」对话框效果图
输出: about_preview.png
"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 900, 620
out = os.path.join(os.path.dirname(__file__), "about_preview.png")

C_BG          = (13, 71, 161)
C_TITLEBAR    = (21, 101, 192)
C_TITLEBAR_FG = (227, 242, 253)
C_APP_BG      = (245, 249, 255)
C_ACCENT      = (66, 165, 245)
C_BTN_BG      = (21, 101, 192)
C_BTN_FG      = (255, 255, 255)
C_BTN_LIGHT   = (227, 242, 253)
C_TEXT        = (55, 71, 79)
C_MUTED       = (120, 144, 156)
C_BORDER      = (200, 215, 235)
C_WARN_BG     = (255, 248, 225)
C_WARN_FG     = (230, 81, 0)
C_WARN_BORDER = (255, 179, 0)

FONT_PATH = None
for p in ["/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
          "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc"]:
    if os.path.exists(p):
        FONT_PATH = p
        break
mk = (lambda s: ImageFont.truetype(FONT_PATH, s)) if FONT_PATH else (lambda s: ImageFont.load_default())
f_big    = mk(20)
f_title  = mk(15)
f_btn    = mk(11)
f_small  = mk(10)
f_tiny   = mk(9)
f_bold   = mk(10)

img = Image.new("RGB", (W, H), C_BG)
d = ImageDraw.Draw(img)

WX, WY, WW, WH = 170, 50, 560, 520
# 阴影
d.rounded_rectangle([WX + 5, WY + 5, WX + WW + 5, WY + WH + 5], radius=8, fill=(0, 0, 0))
# 窗体
d.rounded_rectangle([WX, WY, WX + WW, WY + WH], radius=8, fill=C_APP_BG, outline=C_ACCENT, width=2)
# 标题栏
d.rounded_rectangle([WX, WY, WX + WW, WY + 40], radius=8, fill=C_TITLEBAR)
d.rectangle([WX, WY + 24, WX + WW, WY + 40], fill=C_TITLEBAR)
d.text((WX + 16, WY + 11), "关于软件", fill=C_TITLEBAR_FG, font=f_title)
d.text((WX + WW - 32, WY + 9), "✕", fill=C_TITLEBAR_FG, font=f_btn)

y = WY + 58
# 软件名
d.text((WX + 22, y), "局域网远控 / 电子教室", fill=C_TITLEBAR, font=f_big)
y += 30
d.text((WX + 22, y), "面向机房 / 教室局域网的远程管理工具", fill=C_MUTED, font=f_tiny)
y += 26

# 信息条
d.rounded_rectangle([WX + 22, y, WX + WW - 22, y + 62], 6, fill=C_BTN_LIGHT)
d.text((WX + 34, y + 10), "版本", fill=C_TITLEBAR, font=f_small)
d.text((WX + 84, y + 9), "v2", fill=C_TEXT, font=f_bold)
d.text((WX + 34, y + 36), "作者", fill=C_TITLEBAR, font=f_small)
d.text((WX + 84, y + 35), "@爱分享的校长", fill=C_TEXT, font=f_bold)
y += 76

# 免责声明框
d.rounded_rectangle([WX + 22, y, WX + WW - 22, y + 268], 6, fill=C_WARN_BG, outline=C_WARN_BORDER, width=2)
d.text((WX + 34, y + 12), "⚠  免责声明", fill=C_WARN_FG, font=f_bold)
ly = y + 40
lines = [
    "本软件仅供学习研究与机房管理使用。",
    "",
    "1. 请务必在自己拥有、或已获得明确授权管理的",
    "    设备上部署和使用，严禁在他人设备上安装",
    "    或运行。",
    "",
    "2. 本软件功能等价于远程控制，可查看屏幕、控制",
    "    键鼠、传输文件、执行命令、管理进程。使用者",
    "    需自行确保用途合法合规。",
    "",
    "3. 因使用者违反上述约定、或违反所在地法律法规",
    "    而产生的一切后果，由使用者本人承担，作者",
    "    不承担任何责任。",
    "",
    "4. 本软件代码完全开源可审计，不含任何恶意行为；",
    "    若杀毒软件误报，请自行判断后添加信任。",
]
for i, ln in enumerate(lines):
    d.text((WX + 34, ly + i * 17), ln, fill=C_TEXT, font=f_tiny)
y += 280

# 确定按钮
by = WY + WH - 50
d.rounded_rectangle([WX + WW - 22 - 100, by, WX + WW - 22, by + 34], 6, fill=C_BTN_BG)
t = "确定"
tw = d.textlength(t, font=f_btn)
d.text((WX + WW - 22 - 100 + (100 - tw) / 2, by + 10), t, fill=C_BTN_FG, font=f_btn)

# 右侧说明
d.text((WX + WW + 40, WY + 20), "入口位置", fill=(227, 242, 253), font=f_title)
d.text((WX + WW + 40, WY + 48), "主界面工具栏最右侧", fill=(200, 215, 235), font=f_tiny)
d.text((WX + WW + 40, WY + 68), "「关于软件」按钮", fill=(200, 215, 235), font=f_tiny)

img.save(out)
print(f"✓ 已生成关于软件效果图: {out}  ({W}x{H})")
