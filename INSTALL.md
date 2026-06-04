# Shared Channel — 安装指南

## 方法一：给 Claude Code 的自动安装提示词（推荐）

把下面整段复制粘贴给你的 Claude Code，它会自动完成安装：

```
请帮我安装 shared-channel — 跨 Claude Code 窗口消息通道。

步骤如下，每一步都要执行：

第一步：克隆仓库
git clone https://github.com/1992686510qq-hash/shared-channel.git "D:/Claude Code/shared-channel"

如果 "D:/Claude Code" 目录不存在，先创建它。

第二步：检查 Python
运行 python --version 或 python3 --version，确认 Python 3.8+ 可用。
如果找不到 python，尝试 where python 或 which python3 查找路径。

第三步：验证安装
运行以下命令，确认输出正常：
python "D:/Claude Code/shared-channel/channel.py" init --task "安装测试"

应该返回类似 {"session_id": "abc12345", "task": "安装测试"} 的 JSON。
如果中文乱码，运行：setx PYTHONIOENCODING utf-8（Windows）或 export PYTHONIOENCODING=utf-8（Linux/Mac）

第四步：清理测试会话
删除测试产生的会话目录：
rm -rf "D:/Claude Code/shared-channel/sessions/"*

第五步：检查 claude CLI（可选，auto-chat.py 需要）
运行 claude --version，确认 claude CLI 可用。
如果不可用，auto-chat.py 的自动对话功能将无法使用，但 dialog.py（手工交互）仍然可用。

第六步：注册 /cvs 命令（可选）
如果想使用 /cvs 斜杠命令，把命令文件复制到全局 commands 目录：
cp "D:/Claude Code/shared-channel/.claude/commands/cvs.md" ~/.claude/commands/cvs.md

第七步：告知安装结果
告诉我：
- Python 版本
- claude CLI 是否可用
- /cvs 命令是否已注册
- 安装是否成功
```

---

## 方法二：手动安装

### 环境要求

- Python 3.8+（仅使用标准库，无需 pip install）
- Git
- （可选）claude CLI — auto-chat.py 自动对话需要

### 步骤

```bash
# 1. 克隆仓库
git clone https://github.com/1992686510qq-hash/shared-channel.git "D:/Claude Code/shared-channel"

# 2. 验证
python "D:/Claude Code/shared-channel/channel.py" init --task "测试"
# 应输出: {"session_id": "...", "task": "测试"}

# 3. 清理测试数据
rm -rf "D:/Claude Code/shared-channel/sessions/"*

# 4. （可选）注册 /cvs 命令
cp "D:/Claude Code/shared-channel/.claude/commands/cvs.md" ~/.claude/commands/cvs.md
```

### 编码问题排查

如果中文输出乱码：

```bash
# Windows（永久生效）
setx PYTHONIOENCODING utf-8

# Linux/Mac（当前会话）
export PYTHONIOENCODING=utf-8

# 或写入 ~/.bashrc
echo 'export PYTHONIOENCODING=utf-8' >> ~/.bashrc
```

---

## 方法三：给 Claude Code 的协作启动提示词

安装完成后，把下面的提示词分别粘贴给两个 Claude Code 窗口即可启动协作：

### 窗口 A（发起方）

```
请帮我启动 shared-channel 跨窗口协作。

第一步：运行以下命令创建会话：
python "D:/Claude Code/shared-channel/auto-chat.py" --as A --task "在这里写你的任务描述"

第二步：告诉我输出的 session_id。

第三步：生成给窗口 B 的启动命令，格式如下（把 SESSION_ID 替换为实际值）：
窗口 B 请运行：python "D:/Claude Code/shared-channel/auto-chat.py" --as B --session SESSION_ID
```

### 窗口 B（加入方）

```
请帮我加入 shared-channel 跨窗口协作。

会话 ID 是：[把 A 给你的 session_id 粘贴到这里]

第一步：运行以下命令加入会话：
python "D:/Claude Code/shared-channel/auto-chat.py" --as B --session [SESSION_ID]

第二步：告诉我对话已经开始。
```
