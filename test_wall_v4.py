"""
test_wall_v4.py - v4 纯 Canvas 预览墙验证
重点验证「不抖动」：
  1. 1FPS 刷新只 itemconfig，不改任何坐标
  2. layout() 防重入，scrollregion 只在变化时设置
  3. 拖拽跟手移动 + 释放交换顺序
"""
import sys
import os
import time
from unittest.mock import MagicMock, Mock

sys.path.insert(0, os.path.dirname(__file__))

for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
    sys.modules.setdefault(_m, MagicMock())

import tkinter as tk
from controller import PreviewWall, Machine, CARD_W, CARD_H, THUMB_W, THUMB_H


class FakeController:
    def __init__(self):
        self.machines = {}
        self.lock = __import__("threading").Lock()

    def on_selection_changed(self, mid):
        pass

    def control_selected(self, mid=None):
        self._ctrl_called = mid


class FakeCanvas:
    """记录所有 coords/itemconfig 调用的假 Canvas"""
    def __init__(self, w=1000, h=700):
        self.w = w
        self.h = h
        self.items = {}
        self._n = 0
        self.coords_calls = 0
        self.itemconfig_calls = 0
        self.scrollregion_calls = 0
        self._sr = None

    def winfo_width(self): return self.w
    def winfo_height(self): return self.h
    def bind(self, *a, **k): pass
    def create_rectangle(self, *a, **k): self._n += 1; self.items[self._n] = ('rect', a); return self._n
    def create_oval(self, *a, **k): self._n += 1; self.items[self._n] = ('oval', a); return self._n
    def create_text(self, *a, **k): self._n += 1; self.items[self._n] = ('text', a); return self._n
    def create_image(self, *a, **k): self._n += 1; self.items[self._n] = ('image', a); return self._n
    def delete(self, i): self.items.pop(i, None)
    def coords(self, i, *a): self.coords_calls += 1
    def itemconfig(self, i, **k): self.itemconfig_calls += 1
    def tag_raise(self, i): pass
    def tag_lower(self, i): pass
    def canvasx(self, x): return x
    def canvasy(self, y): return y
    def configure(self, **k):
        if 'scrollregion' in k:
            self.scrollregion_calls += 1
            self._sr = k['scrollregion']
    def pack(self, *a, **k): pass


def make_wall(n=3):
    root = Mock()
    root.winfo_width.return_value = 1024
    ctrl = FakeController()
    wall = PreviewWall(root, ctrl)
    wall.canvas = FakeCanvas()
    wall.scrollbar = Mock()
    mids = []
    for i in range(1, n + 1):
        mid = f"id-{i}"
        m = Machine(mid, f"PC-0{i}", "Win11", f"192.168.1.{i}", 9000 + i)
        from screen import ScreenCapturer
        m.set_thumb(ScreenCapturer(f"PC-0{i}").capture_jpeg(THUMB_W, THUMB_H))
        ctrl.machines[mid] = m
        mids.append(mid)
    return ctrl, wall, mids


def test_no_jitter_on_refresh():
    print("\n[测试1] 1FPS 刷新 —— 必须零坐标变动")
    ctrl, wall, mids = make_wall(3)
    wall.full_redraw(list(ctrl.machines.values()))

    cv = wall.canvas
    # 重置计数器
    cv.coords_calls = 0
    cv.itemconfig_calls = 0
    cv.scrollregion_calls = 0

    # 模拟 30 轮 1FPS 刷新
    for _ in range(30):
        for mid in mids:
            wall.update_one(mid)

    print(f"  30 轮刷新后: coords={cv.coords_calls}, "
          f"scrollregion={cv.scrollregion_calls}, itemconfig={cv.itemconfig_calls}")
    assert cv.coords_calls == 0, (
        f"❌ 仍在抖动: 刷新触发了 {cv.coords_calls} 次坐标变更（应严格为 0）"
    )
    assert cv.scrollregion_calls == 0, (
        f"❌ 仍在抖动: 刷新触发了 {cv.scrollregion_calls} 次 scrollregion 变更"
    )
    print(f"  ✓ 图片刷新只走 itemconfig({cv.itemconfig_calls} 次)，坐标完全不动 → 不抖动")


def test_layout_no_recursion():
    print("\n[测试2] layout() 防重入")
    ctrl, wall, mids = make_wall(3)
    wall.full_redraw(list(ctrl.machines.values()))
    cv = wall.canvas
    cv.scrollregion_calls = 0
    cv.coords_calls = 0

    wall.layout()
    first_coords = cv.coords_calls
    first_sr = cv.scrollregion_calls
    print(f"  首次 layout: coords={first_coords}, scrollregion={first_sr}")

    # 再调一次，内容没变 → scrollregion 不应再设置（避免 Configure 循环）
    cv.scrollregion_calls = 0
    wall.layout()
    print(f"  再次 layout: scrollregion={cv.scrollregion_calls} (内容未变应为 0)")
    assert cv.scrollregion_calls == 0, "内容未变时不应重复设置 scrollregion"
    print("  ✓ scrollregion 仅在变化时设置 → 不触发 Configure 循环")

    # 防重入
    wall._layouting = True
    cv.coords_calls = 0
    wall.layout()
    assert cv.coords_calls == 0, "重入时应直接返回"
    wall._layouting = False
    print("  ✓ 防重入生效（Configure 回调不会递归）")


def test_drag_swap():
    print("\n[测试3] 拖拽交换顺序")
    ctrl, wall, mids = make_wall(4)
    wall.full_redraw(list(ctrl.machines.values()))
    before = list(wall.order)
    print(f"  拖拽前: {before}")

    # 按下 id-1（其左上角坐标）
    x1, y1, x2, y2 = wall._rects["id-1"]
    ev = Mock(); ev.x = x1 + 5; ev.y = y1 + 5; ev.x_root = 100; ev.y_root = 100
    wall._on_press(ev)
    assert wall._drag_mid == "id-1"

    # 移动到 id-3 位置（超阈值）
    tx, ty, _, _ = wall._rects["id-3"]
    ev2 = Mock(); ev2.x = tx + 5; ev2.y = ty + 5; ev2.x_root = 500; ev2.y_root = 100
    wall._on_motion(ev2)
    assert wall._dragging is True, "超阈值应进入拖拽"
    print("  ✓ 超过阈值进入拖拽态，卡片跟手移动")

    # 释放在 id-3 上
    ev3 = Mock(); ev3.x = tx + 5; ev3.y = ty + 5; ev3.x_root = 500; ev3.y_root = 100
    wall._on_release(ev3)

    after = list(wall.order)
    print(f"  拖拽后 order: {after}")
    # v5: 改为自由定位 —— 停在拖到的坐标，不再交换顺序
    assert "id-1" in wall._free_pos, "应记录自由坐标"
    fx, fy = wall._free_pos["id-1"]
    print(f"  自由坐标: ({int(fx)}, {int(fy)})")
    assert abs(fx - tx) < 15 and abs(fy - ty) < 15, "应停在释放位置"
    print("  ✓ 卡片自由停留在拖到的坐标（v5 任意拖动）")


def test_hit_test_and_select():
    print("\n[测试4] 点击命中与选中")
    ctrl, wall, mids = make_wall(3)
    wall.full_redraw(list(ctrl.machines.values()))

    x1, y1, x2, y2 = wall._rects["id-2"]
    assert wall._hit_test(x1 + 10, y1 + 10) == "id-2", "应命中 id-2"
    # 空白处（卡片下方的空白区域，y 超出所有卡片高度）
    blank_y = y1 + CARD_H + 60
    assert wall._hit_test(x1 + 10, blank_y) is None, f"空白处({blank_y})不应命中任何卡片"
    print("  ✓ 命中检测准确（卡片内命中，空白处返回 None）")

    ev = Mock(); ev.x = x1 + 10; ev.y = y1 + 10; ev.x_root = 0; ev.y_root = 0
    wall._on_press(ev)
    assert wall.get_selected() == "id-2", "按下应选中"
    print("  ✓ 单击选中生效")


def test_thumb_render_no_pil():
    print("\n[测试5] 无 Pillow 时降级不崩溃")
    ctrl, wall, mids = make_wall(1)
    # 模拟 PIL 不可用
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    import builtins
    orig = builtins.__import__
    def fake(name, *a, **k):
        if name.startswith("PIL"):
            raise ImportError("模拟无 Pillow")
        return orig(name, *a, **k)
    builtins.__import__ = fake
    try:
        wall._err_logged = False
        wall.update_one("id-1")     # 不应抛异常
        print("  ✓ 无 Pillow 时优雅降级（打印提示但不崩溃）")
    finally:
        builtins.__import__ = orig


if __name__ == "__main__":
    print("=" * 62)
    print("  v4 纯 Canvas 预览墙 —— 抖动修复验证")
    print("=" * 62)
    test_no_jitter_on_refresh()
    test_layout_no_recursion()
    test_drag_swap()
    test_hit_test_and_select()
    test_thumb_render_no_pil()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓  (抖动已根治)")
    print("=" * 62)
