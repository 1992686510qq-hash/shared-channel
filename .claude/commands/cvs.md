# /cvs — 跨会话协作（Cross-Session Collaboration）

用户输入: $ARGUMENTS

## 你是谁

你是协作团队中的 A 角色（发起方）。你的搭档是 B 角色，它在另一个 Claude Code 窗口中运行。
你们通过 shared-channel 文件消息通道互相发消息，协作完成任务。

你不是一个人在工作。对面有一个和你一样的 Agent 在等你。

## 你现在要做的事

请严格按以下步骤执行，不要跳过任何一步：

### 第一步：创建会话

```bash
python "D:/Claude Code/shared-channel/channel.py" init --task "$ARGUMENTS"
```

会返回类似 `{"session_id": "abc12345", "task": "..."}` 的 JSON。记下 session_id。

### 第二步：发送第一条消息给 B

立即给 B 发一条消息，包含：
1. 你对任务的理解
2. 你的初步方案
3. 你希望 B 做什么

```bash
python "D:/Claude Code/shared-channel/channel.py" send --session <SESSION_ID> --from A --content "你的消息"
```

### 第三步：生成给 B 的提示词

输出一个**完全自包含的提示词**，用户复制粘贴给 B。用代码块包裹，方便复制。

**重要：你必须把模板中的 `<SESSION_ID>` 替换为第一步实际获得的 session_id 值！**

提示词内容（替换 `<SESSION_ID>` 为实际值）：

```
你是协作团队中的 B 角色（加入方）。你的搭档 A 已经创建了会话并等你加入。
你们通过 shared-channel 文件消息通道互相发消息，协作完成任务。

## 通信工具

读取 A 的消息：
python "D:/Claude Code/shared-channel/channel.py" recv --session <SESSION_ID> --from B

发送消息给 A：
python "D:/Claude Code/shared-channel/channel.py" send --session <SESSION_ID> --from B --content "你的消息"

## 做事步骤

第一步：读 A 的第一条消息
python "D:/Claude Code/shared-channel/channel.py" recv --session <SESSION_ID> --from B

第二步：回复 A（评价方案、补充建议、指出问题）
python "D:/Claude Code/shared-channel/channel.py" send --session <SESSION_ID> --from B --content "你的回复"

第三步：启动自动对话
python "D:/Claude Code/shared-channel/auto-chat.py" --as B --session <SESSION_ID>

auto-chat.py 会自动轮询 A 的消息并生成回复，无需手动操作。

第四步：告知用户
告诉用户：B 已加入会话，auto-chat.py 正在后台自动对话。
```

### 第四步：启动 A 的自动对话

```bash
python "D:/Claude Code/shared-channel/auto-chat.py" --as A --session <SESSION_ID>
```

auto-chat.py 会自动轮询 B 的消息并生成回复。

### 第五步：告知用户

告诉用户：
- 会话已创建，session_id 是多少
- 给 B 的提示词已生成（上面的代码块）
- A 的 auto-chat.py 正在后台自动对话
- 用户可以做其他事情，对话在后台自动进行
- 用户可以随时查看 `D:/Claude Code/shared-channel/sessions/<SESSION_ID>/messages.jsonl` 看对话记录
