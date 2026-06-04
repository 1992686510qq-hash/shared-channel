# Shared Channel — 跨 Claude Code 窗口消息通道

两个独立 Claude Code 会话之间通过文件系统交换消息，无需网络、无需额外依赖。

## 安装

> 📖 详细安装指南（含 Claude Code 自动安装提示词）：[INSTALL.md](INSTALL.md)

```bash
# 克隆仓库
git clone https://github.com/1992686510qq-hash/shared-channel.git "D:/Claude Code/shared-channel"

# 验证安装
python "D:/Claude Code/shared-channel/channel.py" init --task "测试"
# 应输出: {"session_id": "...", "task": "测试"}
```

**环境要求**：Python 3.8+（仅标准库，无需 pip install）

---

## 快速开始

### 方式一：auto-chat.py 自动对话（推荐）

两个窗口各运行一条命令，AI 自动对话，无需人工干预：

```bash
# 窗口 A（发起方）— 创建会话
python "D:/Claude Code/shared-channel/auto-chat.py" --as A --task "你的任务描述"

# 窗口 B（加入方）— 拿到 session_id 后运行
python "D:/Claude Code/shared-channel/auto-chat.py" --as B --session <SESSION_ID>
```

auto-chat.py 会自动：
- 每 15 秒检查对方的新消息
- 收到消息后调用 claude CLI 生成回复并发送
- 最多运行 50 轮或 30 分钟（可调）
- 对方停止时自动退出

### 方式二：dialog.py 手工交互

人坐在两个窗口前打字对话：

```bash
# 窗口 A
python "D:/Claude Code/shared-channel/dialog.py" start --as A --task "任务描述"
# 输出: [SESSION] 会话ID: abc12345

# 窗口 B
python "D:/Claude Code/shared-channel/dialog.py" start --as B --session abc12345
```

直接输入文字回车发送，`/quit` 退出。

### 方式三：/cvs 斜杠命令

在 Claude Code 中输入：

```
/cvs 你的任务描述
```

自动创建会话、发送第一条消息、生成给 B 的提示词。

---

## 命令参考

### channel.py（底层通道）

```bash
python channel.py init --task "描述"                        # 创建会话
python channel.py send --session ID --from A --content "内容" # 发送消息
python channel.py recv --session ID --from A                 # 读取未读消息
```

### auto-chat.py（自动对话）

```bash
python auto-chat.py --as A --task "描述"                     # 发起方
python auto-chat.py --as B --session ID                      # 加入方
python auto-chat.py --as A --task "..." --interval 10        # 轮询间隔 10 秒
python auto-chat.py --as A --task "..." --max-turns 30       # 最多 30 轮
python auto-chat.py --as A --task "..." --max-minutes 20     # 最多 20 分钟
```

### dialog.py（手工交互）

```bash
python dialog.py start --as A --task "描述"                  # 创建会话
python dialog.py start --as B --session ID                   # 加入会话
python dialog.py view --session ID                           # 查看消息
python dialog.py view --session ID --follow                  # 实时跟踪
python dialog.py status --session ID                         # 会话状态
python dialog.py stop --session ID                           # 停止会话
```

### viewer.py（浏览器查看）

```bash
python viewer.py --session ID                                # 打开浏览器
python viewer.py --session ID --port 9000                    # 指定端口
python viewer.py --session ID --no-browser                   # 不自动打开
```

---

## 会话目录结构

```
sessions/{session_id}/
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
| `PYTHONIOENCODING` | `utf-8` | 子进程编码（建议设置） |

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `channel.py` | 底层消息通道（init/send/recv） |
| `dialog.py` | 手工交互封装（start/stop/status/view） |
| `auto-chat.py` | 自动对话编排器（轮询 + claude CLI） |
| `session-agent.py` | 简化轮询器（仅打印，不生成回复） |
| `viewer.py` | 浏览器可视化查看器 |
| `ARCHITECTURE.md` | 架构与实现详解 |
| `INSTALL.md` | 安装指南（含自动安装提示词） |
| `prompt-template.md` | 提示词模板 |
| `AGENT-PROMPT.md` | Agent 系统提示词 |

---

## 技术细节

- Python 3.8+，仅使用标准库，零外部依赖
- Windows 用 `msvcrt.locking`，Linux/macOS 用 `fcntl.flock`
- 消息格式：JSON Lines，每行一条，UTF-8 编码
- 游标机制：增量读取，不重复接收
- 停止信号：stop.flag 文件（存在即停止）

---

## License

MIT
