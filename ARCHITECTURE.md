# Shared Channel — 架构与实现详解

## 一句话概括

通过本地文件系统在两个 Claude Code 窗口之间建一条消息通道，让两个 AI 实例能互相发消息协作。

---

## 分层架构

```
┌─────────────────────────────────────────────────────┐
│  用户层                                              │
│  两个 Claude Code 窗口 + 终端                         │
└──────────┬──────────────────────────┬───────────────┘
           │                          │
     ┌─────▼─────────────┐    ┌──────▼──────────────┐
     │  auto-chat.py     │    │  dialog.py          │
     │  自动对话编排器     │    │  手工交互封装        │
     │  (Python轮询循环)  │    │  (stdin/stdout)     │
     └─────┬─────────────┘    └──────┬──────────────┘
           │  subprocess 调用        │
     ┌─────▼─────────────────────────▼───────────────┐
     │  channel.py                                    │
     │  底层消息通道（init / send / recv 三个原子操作）  │
     └─────┬─────────────────────────────────────────┘
           │
     ┌─────▼─────────────────────────────────────────┐
     │  文件系统                                       │
     │  sessions/<id>/messages.jsonl  (JSON Lines)    │
     │  sessions/<id>/meta.json       (会话元信息)     │
     │  sessions/<id>/cursor-A.json   (A的读取游标)    │
     │  sessions/<id>/cursor-B.json   (B的读取游标)    │
     │  sessions/<id>/stop.flag       (停止信号)       │
     │  sessions/<id>/.lock           (文件锁)         │
     └───────────────────────────────────────────────┘
```

---

## 三层各做什么

### 第一层：channel.py — 原子操作

只有三个命令，职责极简：

| 命令 | 做什么 | 关键机制 |
|------|--------|----------|
| `init` | 创建会话目录、写 meta.json、返回 session_id | uuid4 取前8位hex |
| `send` | 往 messages.jsonl 追加一条 JSON | FileLock 保证串行写入 |
| `recv` | 读 messages.jsonl，过滤出未读消息 | cursor 机制增量读取 |

设计哲学：**channel.py 不知道"对话"是什么，它只管存消息、取消息。**

### 第二层：对话管理器

两种模式，共用同一个 channel.py：

| 模式 | 文件 | 适合场景 |
|------|------|---------|
| 手工交互 | `dialog.py` | 人坐在两个窗口前打字 |
| 自动对话 | `auto-chat.py` | 无人值守，AI 自动回复 |

`dialog.py` 用 stdin 循环 + 后台轮询线程，靠 subprocess 调用 channel.py。

`auto-chat.py` 用 Python 主循环轮询，收到消息后调 `claude -p` 生成回复。

### 第三层：文件系统

所有状态都在 `sessions/<session_id>/` 目录下，零外部依赖：

```
messages.jsonl     ← 追加写入，每行一条 JSON（JSON Lines 格式）
meta.json          ← {task, created, participants}
cursor-A.json      ← {last_read_id, last_read_ts}  → 增量读取不重复
cursor-B.json      ← 同上
stop.flag          ← 文件存在 = 会话结束（极简停止信号）
.lock              ← 跨平台文件锁的载体
```

---

## 核心机制详解

### 1. 消息格式（JSON Lines）

每条消息一行 JSON，追加到 `messages.jsonl`：

```json
{"id": "550e8400-...", "from": "A", "ts": 1780564355.604, "type": "message", "content": "你好"}
```

- `id`：UUID，唯一标识
- `from`：发送者（A/B/...）
- `ts`：Unix 时间戳（浮点数，精度到微秒）
- `type`：`message` / `task` / `status`
- `content`：纯文本，支持中文

### 2. 游标机制（不重复读取）

每个参与者有自己的 cursor 文件，记录"我读到哪了"：

```json
// cursor-A.json
{"last_read_id": "550e8400-...", "last_read_ts": 1780564355.604}
```

`recv --from A` 的逻辑：
1. 读 cursor-A.json 拿到 last_read_ts
2. 扫描 messages.jsonl，筛出 `ts > last_read_ts` 且 `from != A` 的消息
3. 有新消息 → 更新 cursor
4. 返回给调用方

这样 A 调多少次 recv，同一条消息只会收到一次。

### 3. 跨平台文件锁

```python
class FileLock:
    # Windows: msvcrt.locking（字节范围锁）
    # Linux/macOS: fcntl.flock（建议锁）
```

锁 `.lock` 文件的第1个字节。保证 send 和 recv 的 cursor 更新不会互相踩踏。

### 4. 停止信号

不需要网络、不需要进程间通信——创建一个空文件就行：

```bash
touch sessions/<id>/stop.flag
```

所有参与者下次 recv 时检查 `stop.flag` 是否存在，存在则返回 `"stopped": true`。

---

## auto-chat.py 的工作流

```
┌──────────────────────────────────────────────┐
│  auto-chat.py --as A --task "设计登录系统"     │
└──────┬───────────────────────────────────────┘
       │
       ▼
  ① channel.py init → 得到 session_id
  ② channel.py send → 发第一条消息
  ③ 进入轮询循环 ──────────────────────────┐
       │                                    │
       ▼                                    │
  ④ channel.py recv → 检查新消息            │
       │                                    │
       ├── messages 为空 → sleep(interval) ──┘
       │                                    │
       ├── stopped=true → 退出循环          │
       │                                    │
       └── 有新消息 ──┐                     │
                      ▼                     │
              ⑤ claude -p "消息内容"         │
              （调 Claude CLI 生成回复）      │
                      │                     │
                      ▼                     │
              ⑥ channel.py send → 发送回复   │
                      │                     │
                      ▼                     │
              ⑦ 检查限制（轮次/时间）─────────┘
                      │
                      ▼ 达到限制
              ⑧ 退出，打印统计
```

安全限制：默认最多 50 轮、30 分钟，防止 token 失控。

---

## 并发模型

```
窗口 A                          窗口 B
┌─────────────┐                ┌─────────────┐
│ auto-chat   │                │ auto-chat   │
│ Python 进程  │                │ Python 进程  │
│   ↓         │                │   ↓         │
│ recv/send   │                │ recv/send   │
└──────┬──────┘                └──────┬──────┘
       │                              │
       │    ┌──────────────────┐      │
       └────►  messages.jsonl  ◄──────┘
            └──────────────────┘
                   ↑
            FileLock 保证
          两个进程不会同时写
```

两个进程独立运行，通过文件锁协调。不需要 HTTP 服务器、WebSocket 或任何网络组件。

---

## 命令速查

### channel.py（底层通道）

```bash
python channel.py init --task "任务描述"
python channel.py send --session <ID> --from A --content "消息"
python channel.py recv --session <ID> --from A
```

### dialog.py（手工交互）

```bash
python dialog.py start --as A --task "任务描述"     # 创建会话
python dialog.py start --as B --session <ID>        # 加入会话
python dialog.py view --session <ID>                # 查看消息
python dialog.py view --session <ID> --follow       # 实时跟踪
python dialog.py status --session <ID>              # 会话状态
python dialog.py stop --session <ID>                # 停止会话
```

### auto-chat.py（自动对话）

```bash
python auto-chat.py --as A --task "任务描述"         # 发起方
python auto-chat.py --as B --session <ID>           # 加入方
python auto-chat.py --as A --task "..." --interval 10 --max-turns 30 --max-minutes 20
```

### viewer.py（浏览器查看）

```bash
python viewer.py --session <ID>                     # 打开浏览器
python viewer.py --session <ID> --port 9000         # 指定端口
python viewer.py --session <ID> --no-browser        # 不自动打开
```

---

## 设计取舍

| 决策 | 为什么这么选 | 代价 |
|------|-------------|------|
| 文件系统而非网络 | 零依赖、跨平台、最简单 | 单机限制 |
| JSON Lines 而非数据库 | 追加写入极简、人类可读 | 不支持复杂查询 |
| 轮询而非推送 | 实现简单、无额外依赖 | 有延迟（默认15秒） |
| 文件锁而非进程锁 | 跨平台兼容 | 需要锁文件 |
| stop.flag 而非信号 | 极简、任何语言都能创建 | 不支持优雅关闭 |
| claude CLI 而非 API | 不需要 API key、直接可用 | 依赖 PATH 中有 claude |

---

## 已知限制

- **单机限制**：只能在同一台机器上使用（基于本地文件系统）
- **轮询延迟**：默认 15 秒间隔，最坏情况要等 15 秒
- **仅支持文本**：不支持文件、图片等二进制数据
- **无加密**：消息以明文存储在文件系统中
- **无历史搜索**：只能按时间顺序查看

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SHARED_CHANNEL_DIR` | `D:\Claude Code\shared-channel\sessions` | 会话存储目录 |
| `PYTHONIOENCODING` | `utf-8` | 子进程编码（建议设置） |

---

## 文件清单

```
shared-channel/
├── channel.py           ← 底层消息通道（init/send/recv）
├── dialog.py            ← 手工交互封装（start/stop/status/view）
├── auto-chat.py         ← 自动对话编排器（轮询 + claude CLI）
├── session-agent.py     ← 简化轮询器（仅打印，不生成回复）
├── viewer.py            ← 浏览器可视化查看器（HTTP + HTML）
├── prompt-template.md   ← 提示词模板（复制粘贴用）
├── AGENT-PROMPT.md      ← Agent 系统提示词
├── ARCHITECTURE.md      ← 本文档
├── README.md            ← 项目说明
├── .claude/
│   └── commands/
│       └── cvs.md       ← /cvs 斜杠命令
└── sessions/            ← 会话数据目录
    └── <session_id>/
        ├── messages.jsonl
        ├── meta.json
        ├── cursor-A.json
        ├── cursor-B.json
        ├── stop.flag
        └── .lock
```
