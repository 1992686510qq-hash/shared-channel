# Shared Channel — 跨 Claude Code 窗口消息通道

两个独立 Claude Code 会话之间通过文件系统交换消息，无需网络、无需额外依赖。

## 快速开始

### 窗口 A（发起方）

```bash
python "D:/Claude Code/shared-channel/dialog.py" start --as A --task "分析这两个文件的差异"
```

会输出会话 ID，例如 `abc12345`。

### 窗口 B（加入方）

```bash
python "D:/Claude Code/shared-channel/dialog.py" start --as B --session abc12345
```

### 开始对话

两个窗口都进入交互模式后，直接输入文字回车即可发送。对方会在 2 秒内收到。

输入 `/quit` 结束会话。

---

## 命令参考

### channel.py（底层通道）

| 命令 | 说明 |
|------|------|
| `channel.py init --task "描述"` | 创建新会话，返回 session_id |
| `channel.py send --session ID --from A --type task --content "内容"` | 发送消息 |
| `channel.py recv --session ID --from A` | 读取未读消息（JSON） |

### dialog.py（交互模式）

| 命令 | 说明 |
|------|------|
| `dialog.py start --as A --task "描述"` | 创建会话并进入对话 |
| `dialog.py start --as B --session ID` | 加入已有会话 |
| `dialog.py stop --session ID` | 结束会话 |
| `dialog.py status --session ID` | 查看会话状态 |
| `dialog.py view --session ID` | 一次性查看所有消息 |
| `dialog.py view --session ID --follow` | 实时跟踪新消息 |

---

## 实时查看对话

### 命令行查看

```bash
python dialog.py view --session abc12345           # 一次性查看所有消息
python dialog.py view --session abc12345 --follow  # 实时跟踪，新消息自动显示
```

### 浏览器查看

```bash
python viewer.py --session abc12345                # 启动HTTP服务器，自动打开浏览器
python viewer.py --session abc12345 --port 8765    # 指定端口
```

在浏览器中以聊天气泡样式实时查看对话，新消息自动追加，页面自动滚动。

---

## 会话目录结构

```
D:/Claude Code/shared-channel/sessions/
  {session_id}/
    messages.jsonl    ← 所有消息（JSON Lines 追加写入）
    meta.json         ← 会话元信息
    cursor-A.json     ← A 的读取游标
    cursor-B.json     ← B 的读取游标
    stop.flag         ← 存在即表示会话结束
    .lock             ← 文件锁（自动管理）
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SHARED_CHANNEL_DIR` | `D:\Claude Code\shared-channel\sessions` | 会话存储目录 |

---

## 技术细节

- Python 3.8+，仅使用标准库
- Windows 用 `msvcrt.locking`，Linux/macOS 用 `fcntl.flock`
- 消息格式：JSON Lines，每行一条
- 轮询间隔：2 秒
