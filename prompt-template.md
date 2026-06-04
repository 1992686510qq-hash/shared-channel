# Shared Channel 提示词模板

两条 Claude Code 窗口（窗口 A 和窗口 B）通过文件消息通道协作完成任务。
复制对应窗口的提示词粘贴给 Claude Code 即可启动。

---

## 工具清单

底层通道 `channel.py`（三种模式共用）：

```bash
# 创建新会话
python "D:/Claude Code/shared-channel/channel.py" init --task "任务描述"
# 返回: {"session_id": "abc12345", "task": "..."}

# 发送消息
python "D:/Claude Code/shared-channel/channel.py" send --session <ID> --from <A/B> --content "消息内容（中文 UTF-8）"

# 检查对方的新消息（返回 JSON）
python "D:/Claude Code/shared-channel/channel.py" recv --session <ID> --from <A/B>
# 返回: {"messages": [...], "stopped": false}
# 注意: --from A 返回的是 B 发的消息（反之亦然），cursor 机制保证不重复读取

# 停止会话
python "D:/Claude Code/shared-channel/dialog.py" stop --session <ID>
```

自动对话编排器 `auto-chat.py`：

```bash
# 创建会话并自动对话（窗口 A）
python "D:/Claude Code/shared-channel/auto-chat.py" --as A --task "任务描述"

# 加入会话并自动对话（窗口 B）
python "D:/Claude Code/shared-channel/auto-chat.py" --as B --session <ID>
```

另有 `dialog.py`（手工交互封装）和 `viewer.py`（浏览器查看器），详见 README。

---

# 方式一：手工交互模式

人坐在两个窗口前，亲手打字对话。适合需要人类判断的场景。

## 窗口 A（发起方）

```
请执行以下命令进入对话模式：

python "D:/Claude Code/shared-channel/dialog.py" start --as A --task "在这里写你的任务描述"

进入后：
- 直接输入文字回车发送消息
- 收到 [MSG] 开头的行是对方发来的消息
- 输入 /quit 退出并结束会话
```

## 窗口 B（加入方）

等窗口 A 启动后会输出 `[SESSION] 会话ID: abc12345`，把 `abc12345` 替换到下面：

```
请执行以下命令加入对话：

python "D:/Claude Code/shared-channel/dialog.py" start --as B --session abc12345

进入后：
- 直接输入文字回车发送消息
- 收到 [MSG] 开头的行是对方发来的消息
- 输入 /quit 退出并结束会话
```

## 辅助命令

```bash
# 查看会话状态
python "D:/Claude Code/shared-channel/dialog.py" status --session abc12345

# 一次性查看所有消息
python "D:/Claude Code/shared-channel/dialog.py" view --session abc12345

# 实时跟踪新消息
python "D:/Claude Code/shared-channel/dialog.py" view --session abc12345 --follow

# 停止会话
python "D:/Claude Code/shared-channel/dialog.py" stop --session abc12345
```

---

# 方式二：auto-chat.py 自动对话模式

两个窗口各启动一个 `auto-chat.py`，自动轮询、自动回复，无人值守完成协作。

**核心原理：**
- 窗口 A 用 `--task` 创建会话，自动发送第一条消息，然后进入轮询循环
- 窗口 B 用 `--session` 加入会话，读取 A 的第一条消息并回复，然后进入轮询循环
- 两个进程独立运行、互不阻塞，通过 channel.py 交换消息
- 每次收到新消息 → 调用 claude CLI 生成回复 → 自动发送
- 达到限制（轮次/时间）或对方停止时自动退出

**适用场景：**
- 前后端协作设计
- 代码审查和修改迭代
- 方案对比和决策
- 任何需要两个 Claude Code 实例协作的复杂任务

**安全限制：**
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--interval` | 15s | 轮询间隔 |
| `--max-turns` | 50 | 最大对话轮次 |
| `--max-minutes` | 30 | 最大运行时间 |

---

## 窗口 A（发起方）— 完整提示词

以下提示词可直接复制粘贴给窗口 A 的 Claude Code：

```
## 任务

我们将通过 shared-channel 与另一个 Claude Code 实例（窗口 B）协作完成任务。
你是参与者 A（发起方），负责创建会话、提出初步方案、主导任务推进。

### 第一步：创建会话并启动自动对话

运行以下命令（把任务描述替换为实际内容）：

python "D:/Claude Code/shared-channel/auto-chat.py" --as A --task "<任务描述>"

这会自动：
1. 创建会话并输出 session_id
2. 发送第一条消息给 B
3. 进入自动轮询循环（每 15 秒检查一次 B 的回复）

### 第二步：告知用户

告诉用户：
- session_id 是多少（用户需要把它给窗口 B）
- A 的 auto-chat 正在后台运行
- 用户可以做其他事情

### 第三步：等待 B 加入

auto-chat.py 会自动处理后续对话。你不需要手动轮询。
```

### 窗口 A 角色示例

可以根据任务类型调整角色设定：

```
你的角色是【前端专家】。你负责：
- 页面布局和组件设计
- 用户交互流程
- 前端技术选型（React/Vue/原生）
- UI/UX 决策
- 调用 B 设计的 API 接口

B 是【后端专家】，负责 API 设计、数据库、服务端逻辑。
```

```
你的角色是【算法工程师】。你负责：
- 核心算法设计和复杂度分析
- 数据结构和处理流程
- 性能优化方案

B 是【系统架构师】，负责整体架构、部署方案、技术选型决策。
```

---

## 窗口 B（加入方）— 完整提示词

以下提示词可直接复制粘贴给窗口 B 的 Claude Code：

```
## 任务

我们将通过 shared-channel 与另一个 Claude Code 实例（窗口 A）协作完成任务。
你是参与者 B（加入方），A 已经创建了会话并发送了第一条消息。

### 会话信息

会话 ID：<等 A 创建后填写>
你的身份：B
任务描述：<等 A 告知后填写>

### 启动自动对话

运行以下命令（把 <SESSION_ID> 替换为实际值）：

python "D:/Claude Code/shared-channel/auto-chat.py" --as B --session <SESSION_ID>

这会自动：
1. 读取 A 的第一条消息并回复
2. 进入自动轮询循环（每 15 秒检查一次 A 的回复）
3. 收到新消息时调用 claude CLI 生成回复并发送

### 告知用户

告诉用户：B 的 auto-chat 正在后台运行，对话自动进行。
```

### 窗口 B 角色示例

```
你的角色是【后端专家】。你负责：
- API 接口设计和文档
- 数据库表结构和查询优化
- 服务端业务逻辑
- 认证、鉴权、安全方案
- 响应 A 提出的前端需求，确认接口契约

A 是【前端专家】，负责页面和交互。
```

```
你的角色是【系统架构师】。你负责：
- 整体系统架构设计
- 技术栈选型和决策依据
- 部署和运维方案
- 对 A 的算法方案进行工程可行性评估

A 是【算法工程师】，负责核心算法设计。
```

---

# 完整示例：前后端协作设计登录系统

## 窗口 A 的实际输入

```
我们将通过 shared-channel 与另一个 Claude Code 实例协作完成任务。
你是参与者 A（前端专家），负责创建会话、提出方案。

你的角色是【前端专家】。你负责页面布局、用户交互、前端技术选型。
B 是【后端专家】，负责 API 设计、数据库、服务端逻辑。

第一步：创建会话并启动自动对话

python "D:/Claude Code/shared-channel/auto-chat.py" --as A --task "设计一个用户登录注册系统，包括前端页面和后端 API"

第二步：告诉我 session_id，我会把 B 的启动命令也准备好。
```

## 窗口 A 自动执行流程

1. `auto-chat.py` 创建会话，输出 `session_id: a1b2c3d4`
2. 自动发送第一条消息：任务描述
3. 进入轮询循环，等待 B 的回复

## 窗口 B 的实际输入

```
我们将通过 shared-channel 与另一个 Claude Code 实例协作完成任务。
你是参与者 B（后端专家），A 已经创建了会话。

会话 ID：a1b2c3d4
你的角色是【后端专家】，负责 API、数据库、安全方案。
A 是【前端专家】，负责页面和交互。

启动自动对话：

python "D:/Claude Code/shared-channel/auto-chat.py" --as B --session a1b2c3d4
```

## 预期对话流程

```
[17:08:02] [A] 会话已创建: a1b2c3d4
[17:08:02] [A] 已发送第一条消息
[17:08:17] [A] 收到 B 的消息: 同意方案，以下是后端设计...
[17:08:17] [A] 正在生成回复...
[17:08:25] [A] [轮次 1] 已发送回复 (342 字)
[17:08:40] [B] 收到 A 的消息: 关于 refresh token 的存储...
[17:08:40] [B] 正在生成回复...
[17:08:48] [B] [轮次 1] 已发送回复 (256 字)
...
[17:15:00] [A] 达到最大轮次 (50)，停止
```

---

# 辅助工具

## 查看对话进度

```bash
# 在第三个终端窗口实时查看
python "D:/Claude Code/shared-channel/dialog.py" view --session <ID> --follow

# 或在浏览器查看
python "D:/Claude Code/shared-channel/viewer.py" --session <ID>
```

## 手动干预

如果需要手动发送消息引导方向：

```bash
# 直接发送消息
python "D:/Claude Code/shared-channel/channel.py" send --session <ID> --from A --content "建议调整方向..."

# 查看状态
python "D:/Claude Code/shared-channel/dialog.py" status --session <ID>
```

## 多组对话同时进行

每个任务创建独立 session，互不干扰：

```bash
python channel.py init --task "任务一"  # -> session_id: aaa111
python channel.py init --task "任务二"  # -> session_id: bbb222
```

## auto-chat.py 中断后如何恢复

直接重新运行 `auto-chat.py` 即可。cursor 机制保证不会重复处理已读消息。

---

# 常见问题

## auto-chat.py 依赖什么？

- Python 3.8+
- claude CLI（需要在 PATH 中）
- 仅使用标准库

## 如何选择轮询间隔？

| 间隔 | 适用场景 |
|------|---------|
| 10s | 紧密协作、需要快速反馈 |
| 15s | 正常协作（推荐，平衡响应速度和 token 消耗） |
| 30s | 松散协作、每轮思考量大的任务 |
| 60s | 异步讨论、不追求实时性 |

## 对话卡住了怎么办？

1. Ctrl+C 停止当前 auto-chat.py
2. 运行 `dialog.py view --session <ID>` 查看消息历史
3. 手动 send 一条消息引导方向
4. 重新运行 auto-chat.py 继续

## token 消耗如何控制？

auto-chat.py 默认限制：
- 最大 50 轮对话
- 最大 30 分钟

可通过参数调整：
```bash
python auto-chat.py --as A --task "..." --max-turns 20 --max-minutes 15
```
