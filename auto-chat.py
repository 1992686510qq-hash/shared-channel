#!/usr/bin/env python3
"""Auto-Chat — 基于 channel.py 的自动对话编排器。

解决 Claude Code Agent 不能循环的问题：用 Python 脚本驱动轮询，
通过 claude CLI 生成回复，实现真正的"两窗口自动对话"。

用法:
    # 窗口 A（发起方）
    python auto-chat.py --as A --task "设计登录系统"

    # 窗口 B（加入方，拿到 session_id 后）
    python auto-chat.py --as B --session <SESSION_ID>

    # 可选参数
    python auto-chat.py --as A --task "..." --interval 10 --max-turns 50 --max-minutes 30

原理:
    1. 创建/加入会话
    2. 进入轮询循环：每 N 秒调用 channel.py recv 检查新消息
    3. 收到新消息 → 调用 claude CLI 生成回复 → 调用 channel.py send 发送
    4. 达到限制（max-turns / max-minutes）自动停止
    5. 对方发 stop.flag 也自动停止
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get(
    "SHARED_CHANNEL_DIR",
    r"D:\Claude Code\shared-channel\sessions"
))
CHANNEL_PY = Path(__file__).resolve().parent / "channel.py"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _env():
    return {**os.environ, "PYTHONIOENCODING": "utf-8"}


def channel_cmd(*args) -> dict | None:
    """Run channel.py, return parsed JSON or None."""
    cmd = [sys.executable, str(CHANNEL_PY)] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=10, env=_env())
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def log(sender: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{sender}] {msg}", flush=True)


def call_claude(prompt: str, role_context: str, timeout: int = 180,
                max_retries: int = 3) -> str | None:
    """Call claude CLI to generate a reply, with retry on failure."""
    full_prompt = f"""{role_context}

以下是对方发来的消息，请认真阅读并回复：
---
{prompt}
---

请直接输出你的回复内容（不要加任何前缀如"回复："）。回复要有实质内容，推进任务。"""

    for attempt in range(1, max_retries + 1):
        try:
            r = subprocess.run(
                ["claude", "-p", full_prompt],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout, env=_env()
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
            # Non-zero return or empty output — retry
            if attempt < max_retries:
                wait = attempt * 5  # 5s, 10s, 15s
                log("SYSTEM", f"claude CLI 返回异常 (attempt {attempt}/{max_retries})，{wait}s 后重试...")
                time.sleep(wait)
        except subprocess.TimeoutExpired:
            if attempt < max_retries:
                wait = attempt * 10
                log("SYSTEM", f"claude CLI 超时 (attempt {attempt}/{max_retries})，{wait}s 后重试...")
                time.sleep(wait)
            else:
                log("SYSTEM", f"claude CLI 超时，已重试 {max_retries} 次，放弃")
        except FileNotFoundError:
            log("SYSTEM", "claude CLI 未找到，请确认已安装并在 PATH 中")
            return None
        except OSError as e:
            log("SYSTEM", f"claude CLI 调用失败: {e}")
            if attempt < max_retries:
                time.sleep(attempt * 5)

    return None


def read_history(session_id: str, sender: str) -> list:
    """Read message history to understand context for claude."""
    result = channel_cmd("read", "--session", session_id, "--from", sender)
    if result and "messages" in result:
        return result["messages"]
    return []


def format_history(messages: list, max_msgs: int = 10) -> str:
    """Format recent message history for context."""
    recent = messages[-max_msgs:]
    lines = []
    for msg in recent:
        src = msg.get("from", "?")
        content = msg.get("content", "")
        # Truncate long messages
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"[{src}]: {content}")
    return "\n".join(lines)


# ── Main Loop ────────────────────────────────────────────────────────────────

def run_session(args):
    sender = args.as_name
    session_id = args.session
    task = args.task
    interval = args.interval
    max_turns = args.max_turns
    max_minutes = args.max_minutes
    claude_timeout = args.claude_timeout

    # Step 1: Create or join session
    if task:
        result = channel_cmd("init", "--task", task)
        if not result or "session_id" not in result:
            print("[ERROR] 创建会话失败", file=sys.stderr)
            sys.exit(1)
        session_id = result["session_id"]
        log(sender, f"会话已创建: {session_id}")
        log(sender, f"任务: {task}")
        # Send first message
        first_msg = f"你好，我是 {sender}。任务是：{task}。请加入会话开始协作。"
        channel_cmd("send", "--session", session_id, "--from", sender,
                     "--type", "task", "--content", first_msg)
        log(sender, f"已发送第一条消息")
    elif session_id:
        meta_path = SESSIONS_DIR / session_id / "meta.json"
        if not meta_path.exists():
            print(f"[ERROR] 会话 {session_id} 不存在", file=sys.stderr)
            sys.exit(1)
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        task = meta.get("task", "N/A")
        log(sender, f"已加入会话: {session_id}")
        log(sender, f"任务: {task}")
    else:
        print("[ERROR] 必须指定 --session 或 --task", file=sys.stderr)
        sys.exit(1)

    log(sender, f"轮询间隔: {interval}s | 最大轮次: {max_turns} | 最大时长: {max_minutes}min")
    log(sender, f"claude 超时: {claude_timeout}s | 重试: 3次")
    log(sender, "开始自动对话循环... (Ctrl+C 停止)")
    print("-" * 50, flush=True)

    # Role context for Claude
    other = "B" if sender == "A" else "A"
    role_context = f"""你是协作团队中的 {sender} 角色，正在通过 shared-channel 与搭档 {other} 协作完成任务。
任务：{task}
会话 ID：{session_id}

协作规则：
1. 每次回复都要推进任务，禁止只说"收到""好的""明白了"
2. 认真读对方的每一条消息
3. 保持独立思考，不要盲目同意
4. 发现问题要指出，给出建议
5. 如果你认为任务已完成，在回复中表达"任务完成，建议结束会话"
"""

    # Step 2: Polling loop
    turn_count = 0
    fail_count = 0
    start_time = time.time()
    last_heartbeat = time.time()

    try:
        while True:
            # Check limits
            elapsed_min = (time.time() - start_time) / 60
            if turn_count >= max_turns:
                log(sender, f"达到最大轮次 ({max_turns})，停止")
                break
            if elapsed_min >= max_minutes:
                log(sender, f"达到最大时长 ({max_minutes}min)，停止")
                break

            # Heartbeat every 5 minutes
            if time.time() - last_heartbeat > 300:
                log(sender, f"[心跳] 运行中 | 轮次: {turn_count} | 耗时: {elapsed_min:.1f}min")
                last_heartbeat = time.time()

            # Poll for new messages
            result = channel_cmd("recv", "--session", session_id, "--from", sender)

            if result is None:
                fail_count += 1
                if fail_count > 10:
                    log(sender, f"连续 {fail_count} 次 recv 失败，停止")
                    break
                log(sender, f"recv 失败 ({fail_count}/10)，重试...")
                time.sleep(interval)
                continue
            else:
                fail_count = 0  # Reset on success

            if result.get("stopped"):
                log(sender, "会话已结束 (stopped=true)")
                break

            messages = result.get("messages", [])
            if not messages:
                time.sleep(interval)
                continue

            # Process new messages
            for msg in messages:
                msg_from = msg.get("from", "?")
                msg_content = msg.get("content", "")
                msg_type = msg.get("type", "message")

                preview = msg_content[:200] + ('...' if len(msg_content) > 200 else '')
                log(msg_from, f"[{msg_type}] {preview}")

                # Generate reply via Claude (with history context)
                history = read_history(session_id, sender)
                history_text = format_history(history) if history else ""
                context_with_history = role_context
                if history_text:
                    context_with_history += f"\n\n最近对话历史：\n{history_text}"

                log(sender, "正在生成回复...")
                reply = call_claude(msg_content, context_with_history,
                                    timeout=claude_timeout)

                if reply:
                    # Send reply
                    send_result = channel_cmd("send", "--session", session_id,
                                               "--from", sender, "--content", reply)
                    if send_result:
                        turn_count += 1
                        log(sender, f"[轮次 {turn_count}] 已发送回复 ({len(reply)} 字)")
                    else:
                        log(sender, "发送回复失败")
                else:
                    log(sender, "生成回复失败，跳过本轮")

            time.sleep(interval)

    except KeyboardInterrupt:
        print()
        log(sender, "Ctrl+C — 停止轮询")

    # Summary
    elapsed = time.time() - start_time
    log(sender, f"对话结束 | 轮次: {turn_count} | 耗时: {elapsed:.0f}s")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    # Force UTF-8 stdout on Windows
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Auto-Chat — 基于 channel.py 的自动对话编排器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 窗口 A（发起方）
  python auto-chat.py --as A --task "设计登录系统"

  # 窗口 B（加入方）
  python auto-chat.py --as B --session a1b2c3d4

  # 自定义参数
  python auto-chat.py --as A --task "..." --interval 10 --max-turns 30 --max-minutes 20

  # claude CLI 超时更长的场景
  python auto-chat.py --as A --task "..." --claude-timeout 300
""")
    parser.add_argument("--as", dest="as_name", required=True,
                        help="你的身份 (A/B/...)")
    parser.add_argument("--session", help="加入已有会话的 ID")
    parser.add_argument("--task", help="创建新会话并指定任务")
    parser.add_argument("--interval", type=int, default=15,
                        help="轮询间隔（秒），默认 15")
    parser.add_argument("--max-turns", type=int, default=50,
                        help="最大对话轮次，默认 50")
    parser.add_argument("--max-minutes", type=int, default=30,
                        help="最大运行时间（分钟），默认 30")
    parser.add_argument("--claude-timeout", type=int, default=180,
                        help="claude CLI 单次调用超时（秒），默认 180")

    args = parser.parse_args()
    run_session(args)


if __name__ == "__main__":
    main()
