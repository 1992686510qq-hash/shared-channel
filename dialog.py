#!/usr/bin/env python3
"""Dialog mode manager — interactive two-window chat over the message channel.

Usage:
    python dialog.py start --as A --task "任务描述"   (Window A, creates session)
    python dialog.py start --as B --session abc12345  (Window B, joins session)
    python dialog.py stop  --session abc12345
    python dialog.py status --session abc12345
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

SESSIONS_DIR = Path(os.environ.get(
    "SHARED_CHANNEL_DIR",
    r"D:\Claude Code\shared-channel\sessions"
))
CHANNEL_PY = Path(__file__).resolve().parent / "channel.py"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_channel(*args) -> dict | None:
    """Run channel.py as a subprocess, return parsed JSON or None."""
    cmd = [sys.executable, str(CHANNEL_PY)] + list(args)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, env=env)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


# ── Polling thread ────────────────────────────────────────────────────────────

def _poll(session_id: str, sender: str, stop: threading.Event):
    """Background thread: poll recv every 2s, print new messages."""
    while not stop.is_set():
        result = _run_channel("recv", "--session", session_id, "--from", sender)
        if result and result.get("messages"):
            for msg in result["messages"]:
                src = msg.get("from", "?")
                content = msg.get("content", "")
                mtype = msg.get("type", "message")
                if mtype in ("task", "status"):
                    print(f"[MSG] {src} ({mtype}): {content}", flush=True)
                else:
                    print(f"[MSG] {src}: {content}", flush=True)
        if result and result.get("stopped"):
            print("[STOP] 会话已结束", flush=True)
            stop.set()
            return
        stop.wait(2)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_start(args):
    """Enter interactive dialog mode."""
    sender = args.as_name
    session_id = args.session
    task = args.task

    # ── Create or join session ────────────────────────────────────────────────
    if task:
        result = _run_channel("init", "--task", task)
        if not result or "session_id" not in result:
            print("[ERROR] 创建会话失败", file=sys.stderr)
            sys.exit(1)
        session_id = result["session_id"]
        print(f"[SESSION] 会话ID: {session_id}", flush=True)
        print(f"[SESSION] 任务: {task}", flush=True)
    elif session_id:
        print(f"[SESSION] 会话ID: {session_id}", flush=True)
        meta_path = SESSIONS_DIR / session_id / "meta.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            print(f"[SESSION] 任务: {meta.get('task', 'N/A')}", flush=True)
    else:
        print("[ERROR] 必须指定 --session 或 --task", file=sys.stderr)
        sys.exit(1)

    print(f"[SESSION] 你是: {sender}", flush=True)
    print("[SESSION] 输入消息后回车发送，/quit 退出", flush=True)
    print("---", flush=True)

    # ── Check stop flag ───────────────────────────────────────────────────────
    stop_flag = SESSIONS_DIR / session_id / "stop.flag"
    if stop_flag.exists():
        print("[STOP] 会话已结束", flush=True)
        return

    # ── Start polling ─────────────────────────────────────────────────────────
    stop_event = threading.Event()
    poller = threading.Thread(target=_poll, args=(session_id, sender, stop_event), daemon=True)
    poller.start()

    # ── Stdin loop ────────────────────────────────────────────────────────────
    try:
        while not stop_event.is_set():
            try:
                line = input()
            except EOFError:
                break

            line = line.strip()
            if not line:
                continue

            if line.lower() in ("/quit", "/exit", "/stop"):
                _run_channel("send",
                             "--session", session_id,
                             "--from", sender,
                             "--type", "status",
                             "--content", "会话结束")
                stop_flag.touch()
                print("[STOP] 会话已结束", flush=True)
                stop_event.set()
                break

            ok = _run_channel("send",
                              "--session", session_id,
                              "--from", sender,
                              "--type", "message",
                              "--content", line)
            if not ok:
                print("[ERROR] 发送失败", file=sys.stderr, flush=True)

    except KeyboardInterrupt:
        print("\n[STOP] Ctrl+C — 退出", flush=True)
        stop_flag.touch()
        stop_event.set()


def cmd_view(args):
    """View session messages, optionally follow for live updates."""
    sdir = SESSIONS_DIR / args.session
    if not sdir.exists():
        print(f"[ERROR] 会话 {args.session} 不存在")
        sys.exit(1)

    # ── Read meta ────────────────────────────────────────────────────────────
    meta_path = sdir / "meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    else:
        meta = {}

    task = meta.get("task", "N/A")
    created_ts = meta.get("created", 0)
    created_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_ts)) if created_ts else "N/A"
    participants = meta.get("participants", [])

    # ── Print header ─────────────────────────────────────────────────────────
    print("=" * 70)
    print(f"📋 会话: {args.session}")
    print(f"📝 任务: {task}")
    print(f"🕐 创建: {created_str}")
    print(f"👥 参与者: {', '.join(participants) if participants else 'N/A'}")
    print("=" * 70)
    print()

    # ── Print messages ───────────────────────────────────────────────────────
    msg_path = sdir / "messages.jsonl"
    last_id = None

    if msg_path.exists():
        with open(msg_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                src = msg.get("from", "?")
                ts = msg.get("ts", 0)
                content = msg.get("content", "")
                mtype = msg.get("type", "message")
                ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else ""
                if mtype in ("task", "status"):
                    print(f"[{src}] {ts_str} [{mtype}] {content}")
                else:
                    print(f"[{src}] {ts_str} {content}")
                last_id = msg.get("id")

    # Check if stopped
    stop_flag = sdir / "stop.flag"
    if stop_flag.exists():
        print()
        print("[STOP] 会话已结束")
        return

    # ── Follow mode ──────────────────────────────────────────────────────────
    if not args.follow:
        return

    print()
    print("[FOLLOW] 实时跟踪中，Ctrl+C 退出...")
    print()

    try:
        while True:
            # Re-read messages, find new ones after last_id
            found_last = (last_id is None)
            new_msgs = []
            if msg_path.exists():
                with open(msg_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not found_last:
                            if msg.get("id") == last_id:
                                found_last = True
                            continue
                        new_msgs.append(msg)

            for msg in new_msgs:
                src = msg.get("from", "?")
                ts = msg.get("ts", 0)
                content = msg.get("content", "")
                mtype = msg.get("type", "message")
                ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else ""
                if mtype in ("task", "status"):
                    print(f"[{src}] {ts_str} [{mtype}] {content}")
                else:
                    print(f"[{src}] {ts_str} {content}")
                last_id = msg.get("id")

            if (sdir / "stop.flag").exists():
                print()
                print("[STOP] 会话已结束")
                return

            time.sleep(2)
    except KeyboardInterrupt:
        print()
        print("[STOP] Ctrl+C — 退出")
        return


def cmd_stop(args):
    """Create stop.flag to end a session."""
    sdir = SESSIONS_DIR / args.session
    if not sdir.exists():
        print(json.dumps({"error": f"会话 {args.session} 不存在"}), flush=True)
        sys.exit(1)
    (sdir / "stop.flag").touch()
    print(json.dumps({"status": "stopped", "session_id": args.session}, ensure_ascii=False), flush=True)


def cmd_status(args):
    """Print session status as JSON."""
    sdir = SESSIONS_DIR / args.session
    if not sdir.exists():
        print(f"[ERROR] 会话 {args.session} 不存在")
        sys.exit(1)

    meta_path = sdir / "meta.json"
    if not meta_path.exists():
        print(f"[ERROR] meta.json 缺失")
        sys.exit(1)

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    stopped = (sdir / "stop.flag").exists()
    msg_count = 0
    msg_path = sdir / "messages.jsonl"
    if msg_path.exists():
        with open(msg_path, "r", encoding="utf-8") as f:
            msg_count = sum(1 for line in f if line.strip())

    print(json.dumps({
        "session_id": args.session,
        "task": meta.get("task"),
        "created": meta.get("created"),
        "participants": meta.get("participants", []),
        "status": "stopped" if stopped else "active",
        "message_count": msg_count,
    }, ensure_ascii=False, indent=2))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Dialog mode manager")
    sub = parser.add_subparsers(dest="command")

    # start
    p = sub.add_parser("start", help="Enter interactive dialog mode")
    p.add_argument("--as", dest="as_name", required=True, help="Your ID (A/B/...)")
    p.add_argument("--session", help="Join an existing session")
    p.add_argument("--task", help="Create a new session with this task")

    # stop
    p = sub.add_parser("stop", help="Stop a session")
    p.add_argument("--session", required=True, help="Session ID")

    # status
    p = sub.add_parser("status", help="Show session status")
    p.add_argument("--session", required=True, help="Session ID")

    # view
    p = sub.add_parser("view", help="View session messages")
    p.add_argument("--session", required=True, help="Session ID")
    p.add_argument("--follow", action="store_true", help="Follow mode: keep polling for new messages")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "view":
        cmd_view(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
