"""
message_demo.py - 生成「发送消息」对话框 + 被控端右下角弹窗 效果图
输出: message_preview.png
"""

import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1100, 700

C_TITLEBAR = (21, 101, 192)
C_TITLEBAR_FG = (227, 242, 253)
C_APP_BG = (245, 249, 255)
C_ACCENT = (66, 165, 245)
C_BTN_BG = (232, 241, 251)
C_BTN_FG = (21, 101, 192)
C_MUTED = (120, 144, 156)
C_BORDER = (200, 215, 235)
C_TEXT = (55, 71, 79)
C_WARN = (239, 108, 0)
C_ERROR = (198, 40, 40)
C_WHITE = (255, 255, 255)

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
f_body = f(11)
f_tiny = f(8)

img = Image.new("RGB", (W, H), C_APP_BG)
d = ImageDraw.Draw(img)


def rr(box, radius, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


# ============================================================
# 左：发送消息 对话框
# ============================================================
DX, DY, DW, DH = 40, 90, 460, 470

d.rectangle([DX + 5, DY + 5, DX + DW + 5, DY + DH + 5], fill=(190, 200, 215))
d.rectangle([DX, DY, DX + DW, DY + DH], fill=C_APP_BG, outline=C_ACCENT, width=2)
d.rectangle([DX, DY, DX + DW, DY + 34], fill=C_TITLEBAR)
d.text((DX + 14, DY + 9), "发送消息（被控端弹窗）", fill=C_TITLEBAR_FG, font=f_title)

y = DY + 48
d.text((DX + 20, y), "发送消息到被控端桌面", fill=C_BTN_FG,
       font=(f_body[0] if False else f(10)))

y += 28
d.text((DX + 20, y + 4), "标题:", fill=C_BTN_FG, font=f_small)
d.rectangle([DX + 74, y, DX + DW - 20, y + 26], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((DX + 82, y + 6), "来自控制端的消息", fill=(70, 90, 110), font=f_small)

y += 36
d.text((DX + 20, y + 4), "内容:", fill=C_BTN_FG, font=f_small)
d.rectangle([DX + 74, y, DX + DW - 20, y + 130], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((DX + 84, y + 10), "请注意课堂纪律，\n把手机收起来。", fill=(70, 90, 110),
       font=f_small)

y += 142
d.text((DX + 20, y + 4), "常用:", fill=C_MUTED, font=f_tiny)
qx = DX + 74
for phrase in ["请注意课堂纪律", "请打开课本第 30 页", "还有 5 分钟下课"]:
    w = d.textlength(phrase, font=f_tiny) + 14
    rr([qx, y, qx + w, y + 20], 4, fill=C_BTN_BG)
    d.text((qx + 7, y + 4), phrase, fill=C_BTN_FG, font=f_tiny)
    qx += w + 4

y += 32
d.text((DX + 20, y + 4), "样式:", fill=C_BTN_FG, font=f_small)
for i, (label, color) in enumerate([("普通", C_TITLEBAR), ("提醒", C_WARN),
                                    ("警告", C_ERROR)]):
    cx = DX + 74 + i * 70
    d.ellipse([cx, y + 6, cx + 11, y + 17], outline=color, width=2)
    if i == 0:
        d.ellipse([cx + 3, y + 9, cx + 8, y + 14], fill=color)
    d.text((cx + 16, y + 4), label, fill=color, font=f_small)

y += 30
d.text((DX + 20, y + 4), "停留:", fill=C_BTN_FG, font=f_small)
d.rectangle([DX + 74, y, DX + 74 + 50, y + 24], fill=C_WHITE,
            outline=(190, 205, 225))
d.text((DX + 82, y + 5), "8", fill=(70, 90, 110), font=f_small)
d.text((DX + 132, y + 5), "秒（0 = 不自动消失，需手动点掉）",
       fill=C_MUTED, font=f_tiny)

y += 36
d.text((DX + 20, y), "弹窗从被控端屏幕右下角向上滑入，多条消息自下而上堆叠",
       fill=C_MUTED, font=f_tiny)

# 按钮
by = DY + DH - 50
rr([DX + 150, by, DX + 150 + 82, by + 30], 4, fill=C_TITLEBAR)
tw = d.textlength("发送", font=f_btn)
d.text((DX + 150 + (82 - tw) / 2, by + 9), "发送", fill=C_WHITE, font=f_btn)
rr([DX + 244, by, DX + 244 + 82, by + 30], 4, fill=C_BTN_BG)
tw = d.textlength("取消", font=f_btn)
d.text((DX + 244 + (82 - tw) / 2, by + 9), "取消", fill=C_BTN_FG, font=f_btn)

# 箭头：指向右侧弹窗
d.line([(DX + DW + 12, DY + 200), (DX + DW + 60, DY + 200)], fill=C_ACCENT, width=3)
d.polygon([(DX + DW + 60, DY + 194), (DX + DW + 60, DY + 206),
           (DX + DW + 74, DY + 200)], fill=C_ACCENT)
d.text((DX + DW + 14, DY + 178), "发送后", fill=C_ACCENT, font=f_small)

# ============================================================
# 右：被控端桌面（右下角弹窗）—— 模拟一个桌面
# ============================================================
SX, SY, SW, SH = 600, 60, 460, 330

# 桌面背景
d.rectangle([SX, SY, SX + SW, SY + SH], fill=(58, 90, 130))
for i in range(0, SW, 40):
    d.line([(SX + i, SY), (SX + i, SY + SH)], fill=(66, 100, 142), width=1)
# 任务栏
d.rectangle([SX, SY + SH - 34, SX + SW, SY + SH], fill=(32, 44, 62))
d.text((SX + 10, SY + SH - 24), "被控端桌面 · 演示机-01", fill=(180, 200, 220),
       font=f_small)

# ---- 三条弹窗，从下往上堆叠 ----
POPUP_W = 250
POPUP_H = 86
MARGIN = 14
GAP = 8

popups = [
    ("来自控制端的消息", "请注意课堂纪律，把手机收起来。", C_TITLEBAR, "教师机"),
    ("上课提醒", "请打开课本第 30 页。", C_WARN, "教师机"),
    ("警告", "立即停止与课堂无关的操作。", C_ERROR, "教师机"),
]

# 从下往上画：index 0 在最下面
for idx, (title, text, color, sender) in enumerate(popups):
    px = SX + SW - POPUP_W - MARGIN
    py = SY + SH - 34 - MARGIN - (idx + 1) * (POPUP_H + GAP) + GAP

    # 阴影
    d.rectangle([px + 3, py + 3, px + POPUP_W + 3, py + POPUP_H + 3],
                fill=(24, 34, 48))
    # 边框
    d.rectangle([px, py, px + POPUP_W, py + POPUP_H], fill=C_BORDER,
                outline=color, width=2)
    # 标题栏
    d.rectangle([px, py, px + POPUP_W, py + 26], fill=color)
    d.text((px + 9, py + 7), title, fill=C_WHITE,
           font=(f_small[0] if False else f(9)))
    d.text((px + POPUP_W - 20, py + 7), "✕", fill=C_WHITE, font=f_small)
    # 内容
    d.rectangle([px, py + 26, px + POPUP_W, py + POPUP_H], fill=C_WHITE)
    d.text((px + 10, py + 34), text, fill=C_TEXT, font=f_small)
    # 发送者
    d.text((px + POPUP_W - 62, py + POPUP_H - 16), f"来自: {sender}",
           fill=C_MUTED, font=f_tiny)

# 运动轨迹箭头（从下往上）
traj_x = SX + SW - 30
d.line([(traj_x, SY + SH - 20), (traj_x, SY + SH - 34 - MARGIN -
                                 len(popups) * (POPUP_H + GAP) + 20)],
       fill=(255, 255, 255), width=2)
d.polygon([(traj_x - 5, SY + SH - 34 - MARGIN - len(popups) * (POPUP_H + GAP) + 28),
           (traj_x + 5, SY + SH - 34 - MARGIN - len(popups) * (POPUP_H + GAP) + 28),
           (traj_x, SY + SH - 34 - MARGIN - len(popups) * (POPUP_H + GAP) + 18)],
          fill=(255, 255, 255))
d.text((traj_x - 120, SY + SH - 60), "向上滑入 ↑", fill=(255, 255, 255), font=f_small)

# ============================================================
# 底部说明
# ============================================================
ty = SY + SH + 30
d.text((40, ty), "被控端弹窗特性:", fill=C_BTN_FG, font=f_btn)
notes = [
    "· 从屏幕右下角向上滑入（约 300ms 动画）",
    "· 多条消息自下而上堆叠，同屏最多 4 条",
    "· 默认 8 秒自动消失；鼠标悬停暂停倒计时",
    "· 三种样式：普通(蓝) / 提醒(橙) / 警告(红)",
    "· 点击弹窗或右上角 ✕ 可立即关闭",
]
for i, n in enumerate(notes):
    d.text((50, ty + 26 + i * 20), n, fill=C_MUTED, font=f_small)

out = os.path.join(os.path.dirname(__file__), "message_preview.png")
img.save(out)
print(f"✓ 已生成发送消息效果图: {out}  ({W}x{H})")
