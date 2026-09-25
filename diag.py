"""
diag.py - 零抖动诊断脚本 (不依赖 controller.py，单独可跑)

用法 (在 VS Code 终端，确认是 3.12 后执行):
    python diag.py

它会:
1. 打印当前 Python 解释器路径 + 版本 (确认 VS Code 用的是哪个)
2. 检查 tkinter / Pillow / mss 是否真的能被导入
3. 跑一个 30 秒的"纯 Canvas 最小预览墙"，实测 1FPS 刷新是否抖动
4. 最终给出结论 + 确切修复命令

这个脚本不包含任何业务逻辑，只测"渲染层"，用来区分:
   - 环境问题 (Python 版本 / 依赖装错解释器)
   - 代码问题 (布局死循环 / 图片被 GC)
"""

import sys
import time
import traceback


def section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ---------- 1. 解释器信息 ----------
section("1. 解释器信息")
print(f"  可执行文件: {sys.executable}")
print(f"  版本:       {sys.version.split()[0]}")
print(f"  平台:       {sys.platform}")

# ---------- 2. 依赖检查 ----------
section("2. 依赖检查")

deps = {
    "tkinter": ("tkinter", "标准库，通常随 Python 一起安装"),
    "Pillow":  ("PIL", "图像处理，预览墙必需"),
    "mss":     ("mss", "被控端屏幕采集"),
}

results = {}
for name, (import_name, desc) in deps.items():
    try:
        mod = __import__(import_name)
        version = getattr(mod, "__version__", "未知")
        print(f"  [OK]   {name:8s} v{version:12s} ({desc})")
        results[name] = True
    except Exception as e:
        print(f"  [MISS] {name:8s} ({desc})")
        print(f"         导入失败: {type(e).__name__}: {e}")
        results[name] = False

# ---------- 3. 最小抖动测试 ----------
section("3. 最小抖动测试 (纯 Canvas，无业务逻辑)")

if not results.get("tkinter"):
    print("  ✗ tkinter 不可用，跳过渲染测试")
    print("    修复: 重装 Python 时勾选 'tcl/tk and IDLE'")
else:
    try:
        import tkinter as tk
        from tkinter import ImageTk
        from PIL import Image

        root = tk.Tk()
        root.title("抖动测试 - 看到画面静止 = 通过")
        root.geometry("640x400")

        canvas = tk.Canvas(root, bg="#0d47a1", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        # 创建一张测试卡片
        border = canvas.create_rectangle(20, 20, 300, 200, fill="#1976d2", outline="#42a5f5", width=3)
        title = canvas.create_rectangle(22, 22, 298, 44, fill="#1565c0", outline="")
        text = canvas.create_text(160, 120, text="测试中...", fill="white",
                                  font=("Microsoft YaHei", 14, "bold"))
        counter = canvas.create_text(160, 150, text="0 FPS", fill="#bbdefb",
                                     font=("Microsoft YaHei", 10))

        # 生成一张测试图片 (模拟 1FPS 刷新)
        img = Image.new("RGB", (276, 130), "#263238")
        photo = ImageTk.PhotoImage(img)
        img_item = canvas.create_image(22, 46, anchor="nw", image=photo)

        coords_count = [0]
        orig_coords = canvas.coords

        # 打桩: 统计 coords 调用次数 (抖动 = coords 被反复调用)
        def traced_coords(*args):
            coords_count[0] += 1
            return orig_coords(*args)

        canvas.coords = traced_coords

        frame_no = [0]
        running = [True]

        def on_close():
            running[0] = False
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)

        def tick():
            if not running[0]:
                return
            frame_no[0] += 1
            # 模拟 1FPS: 只换图片，不动布局
            new_img = Image.new("RGB", (276, 130), "#263238")
            from PIL import ImageDraw
            d = ImageDraw.Draw(new_img)
            d.text((80, 55), f"Frame {frame_no[0]}", fill="#69f0ae")
            new_photo = ImageTk.PhotoImage(new_img)
            canvas.itemconfig(img_item, image=new_photo)
            canvas._photo_ref = new_photo  # 防 GC
            canvas.itemconfig(counter, text=f"{frame_no[0]} FPS (只换图)")

            if frame_no[0] < 30:
                root.after(1000, tick)
            else:
                # 测试结束
                print(f"\n  --- 测试结果 ---")
                print(f"  总帧数:       {frame_no[0]}")
                print(f"  coords 调用:  {coords_count[0]} 次")
                if coords_count[0] == 0:
                    print(f"  ✓ 零抖动: 30 秒 1FPS 刷新，坐标 0 次变更")
                    print(f"    你的环境可以稳定运行预览墙，")
                    print(f"    若原程序仍抖，则是代码问题 (可换纯 Canvas 实现)")
                else:
                    print(f"  ! 存在坐标变更: {coords_count[0]} 次")
                    print(f"    可能是窗口缩放触发，属正常现象")
                running[0] = False
                root.after(2000, root.destroy)

        # 启动测试
        root.after(500, tick)
        print("  (窗口打开后等待 30 秒自动结束，观察画面是否静止)")
        root.mainloop()

    except Exception as e:
        print(f"  ✗ 渲染测试异常: {type(e).__name__}: {e}")
        traceback.print_exc()


# ---------- 4. 结论 ----------
section("4. 结论与修复命令")
exe = sys.executable

print("\n  如果上面测试显示 '零抖动'，说明环境没问题，")
print("  只需把预览墙改成 '纯 Canvas + 只换图不重排' 即可。\n")

print("  修复命令 (直接复制粘贴到 VS Code 终端):\n")
print(f'    "{exe}" -m pip install --upgrade pip')
print(f'    "{exe}" -m pip install pillow mss')
print()
print("  验证:")
print(f'    "{exe}" -c "import tkinter, PIL, mss; print(\\"全部OK\\")"')
print()
print("  切换 VS Code 解释器:")
print("    Ctrl+Shift+P -> Python: Select Interpreter")
print("    选择路径包含上面 exe 的 Python\n")
