"""
test_freedrag.py - v5 自由拖拽定位 + 层级修复 验证

覆盖:
  1. 层级修复: border 必须在最底层(tag_lower)，否则盖住图片 → 纯蓝方块
  2. 自由定位: 拖到任意坐标后停在那里，不吸附、不交换顺序
  3. 混合布局: 拖动过的卡片用自由坐标，其余仍自动网格排列
  4. 整理排列: 清除自由位置，全部回到网格
  5. 滚动区域: 覆盖被拖远的卡片
"""
import sys
import os
from unittest.mock import MagicMock, Mock

sys.path.insert(0, os.path.dirname(__file__))

for _m in ("tkinter", "tkinter.ttk", "tkinter.messagebox"):
    sys.modules.setdefault(_m, MagicMock())

from controller import PreviewWall, Machine, CARD_W, CARD_H, THUMB_W, THUMB_H


class FakeController:
    def __init__(self):
        self.machines = {}
        self.lock = __import__("threading").Lock()

    def on_selection_changed(self, mid):
        pass

    def control_selected(self, mid=None):
        pass


class FakeCanvas:
    """记录层级与坐标调用"""
    def __init__(self, w=1000, h=700):
        self.w = w
        self.h = h
        self._n = 0
        self.items_order = []      # 创建顺序（模拟层叠，后创建的在上）
        self.raised = []
        self.lowered = []
        self.coords_log = {}
        self.scrollregion = None

    def winfo_width(self): return self.w
    def winfo_height(self): return self.h
    def bind(self, *a, **k): pass
    def _new(self, kind):
        self._n += 1
        self.items_order.append((self._n, kind))
        return self._n
    def create_rectangle(self, *a, **k): return self._new("rect")
    def create_oval(self, *a, **k): return self._new("oval")
    def create_text(self, *a, **k): return self._new("text")
    def create_image(self, *a, **k): return self._new("image")
    def delete(self, i): pass
    def coords(self, i, *a):
        if a: self.coords_log[i] = a
    def itemconfig(self, i, **k): pass
    def tag_raise(self, i): self.raised.append(i)
    def tag_lower(self, i): self.lowered.append(i)
    def canvasx(self, x): return x
    def canvasy(self, y): return y
    def configure(self, **k):
        if "scrollregion" in k: self.scrollregion = k["scrollregion"]
    def pack(self, *a, **k): pass


def make_wall(n=3):
    root = Mock()
    root.winfo_width.return_value = 1024
    ctrl = FakeController()
    wall = PreviewWall(root, ctrl)
    wall.canvas = FakeCanvas()
    wall.scrollbar = Mock()
    for i in range(1, n + 1):
        mid = f"id-{i}"
        m = Machine(mid, f"PC-0{i}", "Win11", f"192.168.1.{i}", 9000 + i)
        from screen import ScreenCapturer
        m.set_thumb(ScreenCapturer(f"PC-0{i}").capture_jpeg(THUMB_W, THUMB_H))
        ctrl.machines[mid] = m
    wall.full_redraw(list(ctrl.machines.values()))
    return ctrl, wall


def test_border_z_order():
    """测试1: border 必须 tag_lower（最底层），否则盖住图片"""
    print("\n[测试1] 层级修复 —— border 不能在顶层")
    ctrl, wall = make_wall(1)
    cv = wall.canvas
    cv.lowered.clear()
    cv.raised.clear()

    mid = "id-1"
    items = wall.cards[mid]
    wall._place_items(mid, items, 50, 50)

    # border 应被 tag_lower 到最底
    assert items["border"] in cv.lowered, (
        "❌ 层级BUG: border 未被 tag_lower，会盖住缩略图 → 显示成纯蓝方块"
    )
    assert items["border"] not in cv.raised, (
        "❌ 层级BUG: border 被 tag_raise 到顶层了"
    )
    # 图片应被 raise
    assert items["img"] in cv.raised
    print(f"  ✓ border → tag_lower（最底），图片 → tag_raise（在上）")
    print(f"  ✓ 缩略图不再被蓝色填充矩形遮盖")


def test_free_drag_position():
    """测试2: 拖到任意坐标后自由停留"""
    print("\n[测试2] 自由拖拽定位")
    ctrl, wall = make_wall(3)
    before_order = list(wall.order)
    print(f"  初始 order: {before_order}")

    # 拖起 id-1，拖到 (600, 300)
    x1, y1, _, _ = wall._rects["id-1"]
    ev = Mock(); ev.x = x1 + 5; ev.y = y1 + 5; ev.x_root = 0; ev.y_root = 0
    wall._on_press(ev)

    tx, ty = 600, 300
    ev2 = Mock(); ev2.x = tx + 5; ev2.y = ty + 5; ev2.x_root = 600; ev2.y_root = 300
    wall._on_motion(ev2)
    assert wall._dragging is True
    print("  ✓ 跟手移动中（拖拽态已激活）")

    ev3 = Mock(); ev3.x = tx + 5; ev3.y = ty + 5; ev3.x_root = 600; ev3.y_root = 300
    wall._on_release(ev3)

    # 关键断言: 记录在 _free_pos，且坐标≈(600,300)
    assert "id-1" in wall._free_pos, "❌ 未记录自由坐标"
    fx, fy = wall._free_pos["id-1"]
    print(f"  释放位置: ({int(fx)}, {int(fy)})  期望≈(600, 300)")
    assert abs(fx - 600) < 15 and abs(fy - 300) < 15, (
        f"❌ 自由坐标错误: 得到 ({fx}, {fy})"
    )
    # 顺序不变（不是排序，是自由定位）
    assert wall.order == before_order, "自由拖动不应改变 order"
    print(f"  ✓ 停在任意坐标 (600,300)，order 未变 → 真·任意拖动")


def test_mixed_layout():
    """测试3: 拖动的卡片用自由坐标，其余仍网格排列"""
    print("\n[测试3] 混合布局")
    ctrl, wall = make_wall(4)

    # 拖动 id-2 到 (700, 50)
    x1, y1, _, _ = wall._rects["id-2"]
    ev = Mock(); ev.x = x1 + 5; ev.y = y1 + 5; ev.x_root = 0; ev.y_root = 0
    wall._on_press(ev)
    ev2 = Mock(); ev2.x = 705; ev2.y = 55; ev2.x_root = 700; ev2.y_root = 50
    wall._on_motion(ev2)
    ev3 = Mock(); ev3.x = 705; ev3.y = 55; ev3.x_root = 700; ev3.y_root = 50
    wall._on_release(ev3)

    # 其余卡片应重新紧凑网格排列（跳过 id-2 的槽位）
    r1 = wall._rects["id-1"]
    r3 = wall._rects["id-3"]
    r4 = wall._rects["id-4"]
    r2 = wall._rects["id-2"]
    print(f"  id-2 自由位置: ({int(r2[0])}, {int(r2[1])})")
    print(f"  id-1: ({int(r1[0])}, {int(r1[1])})  id-3: ({int(r3[0])}, {int(r3[1])})  id-4: ({int(r4[0])}, {int(r4[1])})")

    # id-2 应在自由坐标
    assert abs(r2[0] - 700) < 15
    # 其余三张应占据网格前三个槽位（第一行连续）
    grid = sorted([r1, r3, r4], key=lambda r: (r[1], r[0]))
    assert grid[0][1] == grid[1][1] == grid[2][1], "其余卡片应在同一行(网格排列)"
    print("  ✓ 拖动卡片自由定位，其余自动网格补位")


def test_arrange_grid():
    """测试4: 整理排列收回网格"""
    print("\n[测试4] 整理排列")
    ctrl, wall = make_wall(3)

    # 拖两张
    for mid, tx, ty in [("id-1", 500, 200), ("id-2", 800, 400)]:
        x1, y1, _, _ = wall._rects[mid]
        ev = Mock(); ev.x = x1 + 5; ev.y = y1 + 5; ev.x_root = 0; ev.y_root = 0
        wall._on_press(ev)
        ev2 = Mock(); ev2.x = tx + 5; ev2.y = ty + 5; ev2.x_root = tx; ev2.y_root = ty
        wall._on_motion(ev2)
        ev3 = Mock(); ev3.x = tx + 5; ev3.y = ty + 5; ev3.x_root = tx; ev3.y_root = ty
        wall._on_release(ev3)
    assert len(wall._free_pos) == 2
    print(f"  拖动了 {len(wall._free_pos)} 张")

    n = wall.arrange_grid()
    assert n == 2, f"应整理 2 张，实际 {n}"
    assert len(wall._free_pos) == 0, "整理后应清空自由位置"
    # 全部回到同一行网格
    ys = [wall._rects[m][1] for m in ["id-1", "id-2", "id-3"]]
    assert len(set(ys)) == 1, f"整理后应回到同一行，实际 y={ys}"
    print(f"  ✓ 整理 {n} 张，全部回到网格同一行 y={ys[0]}")


def test_scrollregion_expands():
    """测试5: 拖到远处时滚动区域要扩大"""
    print("\n[测试5] 滚动区域自适应")
    ctrl, wall = make_wall(2)
    sr_before = wall.canvas.scrollregion
    print(f"  拖动前 scrollregion: {sr_before}")

    # 拖到很远 (1500, 1200)
    x1, y1, _, _ = wall._rects["id-1"]
    ev = Mock(); ev.x = x1 + 5; ev.y = y1 + 5; ev.x_root = 0; ev.y_root = 0
    wall._on_press(ev)
    ev2 = Mock(); ev2.x = 1505; ev2.y = 1205; ev2.x_root = 1500; ev2.y_root = 1200
    wall._on_motion(ev2)
    ev3 = Mock(); ev3.x = 1505; ev3.y = 1205; ev3.x_root = 1500; ev3.y_root = 1200
    wall._on_release(ev3)

    sr_after = wall.canvas.scrollregion
    print(f"  拖动后 scrollregion: {sr_after}")
    assert sr_after is not None
    assert sr_after[2] >= 1500 + CARD_W, f"宽度应覆盖拖远的卡片，实际 {sr_after[2]}"
    assert sr_after[3] >= 1200 + CARD_H, f"高度应覆盖拖远的卡片，实际 {sr_after[3]}"
    print("  ✓ 滚动区域已扩大，拖远的卡片仍可滚动查看")


if __name__ == "__main__":
    print("=" * 62)
    print("  v5 自由拖拽定位 + 层级修复 验证")
    print("=" * 62)
    test_border_z_order()
    test_free_drag_position()
    test_mixed_layout()
    test_arrange_grid()
    test_scrollregion_expands()
    print("\n" + "=" * 62)
    print("  全部测试通过 ✓")
    print("=" * 62)
