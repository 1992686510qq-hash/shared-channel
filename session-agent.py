#!/usr/bin/env python3
"""Session Agent — 快速轮询会话，打印新消息。

用法:
    python session-agent.py --session <ID> --from <A/B> [--interval 2]

每 2 秒检查一次新消息，有新消息就打印出来。
停止条件：对方发送了 stop.flag，或手动 Ctrl+C。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get(
    "SHARED_CHANNEL_DIR",
    r"D:\Claude Code\shared-channel\sessions"
))
CHANNEL_PY = Path(__file__).resolve().parent / "channel.py"


def _env():
    """Return env dict forcing UTF-8 for subprocess."""
    return {**os.environ, "PYTHONIOENCODING": "utf-8"}


def recv(session_id: str, sender: str) -> dict | None:
    """调用 channel.py recv，返回解析后的 JSON。"""
    cmd = [sys.executable, str(CHANNEL_PY), "recv", "--session", session_id, "--from", sender]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, env=_env())
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def send(session_id: str, sender: str, content: str) -> bool:
    """调用 channel.py send。"""
    cmd = [sys.executable, str(CHANNEL_PY), "send", "--session", session_id, "--from", sender, "--content", content]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, env=_env())
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def main():
    parser = argparse.ArgumentParser(description="Session Agent — 快速轮询会话")
    parser.add_argument("--session", required=True, help="会话 ID")
    parser.add_argument("--from", dest="sender", required=True, help="你的身份 (A/B/C/...)")
    parser.add_argument("--interval", type=float, default=2.0, help="轮询间隔（秒），默认 2")
    args = parser.parse_args()

    session_id = args.session
    sender = args.sender
    interval = args.interval

    # 检查会话是否存在
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        print(f"[ERROR] 会话 {session_id} 不存在", file=sys.stderr)
        sys.exit(1)

    # 读取任务描述
    meta_path = session_dir / "meta.json"
    task = "N/A"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        task = meta.get("task", "N/A")

    print(f"[AGENT] 会话 ID: {session_id}", flush=True)
    print(f"[AGENT] 任务: {task}", flush=True)
    print(f"[AGENT] 你是: {sender}", flush=True)
    print(f"[AGENT] 轮询间隔: {interval} 秒", flush=True)
    print(f"[AGENT] 开始监听... (Ctrl+C 停止)", flush=True)
    print("---", flush=True)

    stop_flag = session_dir / "stop.flag"
    msg_count = 0

    try:
        while True:
            # 检查停止标志
            if stop_flag.exists():
                print("[AGENT] 会话已结束 (stop.flag)", flush=True)
                break

            # 检查新消息
            result = recv(session_id, sender)
            if result and result.get("messages"):
                for msg in result["messages"]:
                    msg_count += 1
                    src = msg.get("from", "?")
                    content = msg.get("content", "")
                    print(f"[MSG #{msg_count}] {src}: {content}", flush=True)

            # 检查 stopped 状态
            if result and result.get("stopped"):
                print("[AGENT] 会话已结束 (stopped=true)", flush=True)
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n[AGENT] 已停止监听 (共收到 {msg_count} 条消息)", flush=True)


if __name__ == "__main__":
    main()
