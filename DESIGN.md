# 局域网远控软件 - 架构设计

## 目标场景
电脑教室局域网内，某一台学生机（控制端 Controller）控制其他学生机（被控端 Agent）。
仅供学习研究，需在获得授权/本人拥有的设备上使用。

## 技术栈
- Python 3.10+
- GUI: Tkinter（内置，教学友好，无需额外依赖）
- 传输: TCP socket + 自定义简单协议（JSON 头 + 二进制体）
- 屏幕采集: mss（快速跨平台截图）
- 图像编码: Pillow JPEG 压缩（局域网带宽足够）
- 键鼠注入: pyautogui / pyDirectInput（Windows 用 SendInput）

## 程序形态
- `controller.py` → 打包为 Controller.exe（控制端，教师/主控用）
- `agent.py` → 打包为 Agent.exe（被控端，安装在每台学生机）

## 通信协议
所有消息 = 4字节长度前缀(BigEndian) + JSON字符串
二进制数据（截图/文件）= JSON头(msg_type, payload_size) + 原始字节流

消息类型:
- `hello`         Agent→Controller 上线通告
- `screen_req`    Controller→Agent 请求一帧
- `screen_frame`  Agent→Controller 图像JPEG数据
- `mouse_move`    Controller→Agent 鼠标移动
- `mouse_click`   Controller→Agent 鼠标点击/双击
- `key_press`     Controller→Agent 按键
- `file_start`    Controller→Agent 开始接收文件
- `file_data`     Controller→Agent 文件分块
- `file_end`      Controller→Agent 文件结束
- `file_list`     Controller→Agent 请求文件列表
- `ping`/`pong`   心跳

## 目录结构
```
remote_control/
├── common.py        # 共享: 协议编解码、消息常量
├── agent.py         # 被控端
├── controller.py    # 控制端
├── requirements.txt
└── DESIGN.md
```

## 模块拆分
### Agent (被控端)
1. ScreenCapturer - 屏幕采集 + JPEG编码
2. InputHandler - 接收指令并执行键鼠注入
3. FileReceiver - 接收文件保存
4. AgentServer - 监听端口、管理单个控制端连接

### Controller (控制端)
1. ScreenViewer - 接收并渲染画面（Tkinter Canvas + PIL）
2. InputSender - 捕获本地鼠标键盘事件转发
3. MachineList - 多机器列表管理（上线/离线/选择）
4. FileSender - 发送文件
5. ControllerClient - 连接多个Agent，连接池管理

## 数据流
控制端选中某机器 → 开启"控制会话" → 循环: 请求screen_frame → 渲染
                           → 用户鼠标事件 → 转发mouse_move/click
                           → 用户键盘事件 → 转发key_press
                           → 文件拖拽/选择 → file_start/data/end
