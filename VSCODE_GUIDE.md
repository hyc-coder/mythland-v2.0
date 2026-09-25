# VS Code 使用指南

## 1. 准备

### 安装扩展
打开项目时 VS Code 会右下角提示「安装推荐扩展」，点安装即可（Python + Pylance）。
或手动搜 `ms-python.python` 安装。

### 装依赖
`Ctrl + \`` 打开终端：
```bash
pip install -r requirements.txt
```
最小可用（只看预览墙）：
```bash
pip install pillow mss
```

### 验证 tkinter（控制端界面依赖）
```bash
python -c "import tkinter; print('OK')"
```
- 打印 `OK` → 没问题
- 报错 `No module named 'tkinter'` → Windows 需重跑 Python 安装程序 → Modify → 勾选 **tcl/tk and IDLE**

## 2. 运行

### 方式 A：一键单机演示（推荐先试这个）
1. 左侧点「运行和调试」图标（`Ctrl+Shift+D`）
2. 顶部下拉选 **`🚀 单机演示 (控制端 + 3台被控端)`**
3. 按 `F5`

会同时启动 4 个终端（1 个控制端 + 3 个被控端），
稍等几秒，控制端窗口就会出现 **3 张卡片** 的预览墙。

> 原理：3 个 Agent 各自监听 9001/9002/9003，但都广播到控制端的 9000 端口。
> 所以一台电脑就能模拟出多机器的效果。

### 方式 B：只跑单端调试
- 下拉选 `🖥️ 控制端 Controller` → `F5`（只有界面，等机器上线）
- 下拉选 `💻 被控端 演示机-01` → `F5`（只有被控端）

### 方式 C：真实局域网（教室多台电脑）
1. 每台学生机跑（终端里）：
   ```bash
   python agent.py --name "学生机01" --broadcast-ip 192.168.1.255 --port 9000 --broadcast-port 9000
   ```
   > `--broadcast-ip` 换成你教室网段，如 `10.0.0.255`
2. 教师机跑：`python controller.py --port 9000`

## 3. 调试

- 在 `controller.py` 的 `add_or_update_machine`、`_fetch_thumb` 等处打断点，
  F5 启动后会断下来，可查看 `msg`、`machine.thumb` 等变量。
- 多线程注意：`listen_broadcast`、`thumb_poll_loop` 都在子线程，
  断点可能不命中主线程逻辑，属正常现象。

## 4. 目录里这些文件是干嘛的

| 文件 | 用途 |
|---|---|
| `controller.py` | 控制端，极域风格预览墙界面 |
| `agent.py` | 被控端，装在学生机 |
| `screen.py` | 屏幕采集（真实截图，失败降级模拟画面） |
| `common.py` | 通信协议 |
| `test_*.py` | 测试脚本，学习用 |
| `preview_wall_demo.py` | 生成一张预览墙效果图 PNG，直观展示 UI |

## 5. 常见问题

**Q: 控制端界面空白，没发现机器？**
A: 确认被控端已启动；单机测试时 `--broadcast-ip` 必须是 `127.0.0.1`；
   检查防火墙是否拦截了 UDP 9000。

**Q: 中文日志乱码？**
A: 已在 `.vscode/settings.json` 设了 `PYTHONIOENCODING=utf-8`，
   若仍乱码，终端里手动执行 `$env:PYTHONIOENCODING="utf-8"`（PowerShell）。

**Q: 提示端口被占用？**
A: 上一个程序没关干净。换端口，或任务管理器结束 python 进程。

**Q: 缩略图是"模拟画面"不是真实桌面？**
A: 说明 `mss` 没装或当前环境抓不到屏幕（如远程桌面/无显卡）。
   装上 `pip install mss` 并在真实桌面环境运行即可。
