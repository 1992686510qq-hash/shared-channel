#!/usr/bin/env python3
"""Cross-window message channel for Claude Code sessions.

Usage:
    python channel.py init --task "任务描述"
    python channel.py send --session SESSION_ID --from A --type task --content "消息内容"
    python channel.py recv --session SESSION_ID --from A
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

# Base directory for sessions
SESSIONS_DIR = Path(os.environ.get(
    "SHARED_CHANNEL_DIR",
    r"D:\Claude Code\shared-channel\sessions"
))


# ── Cross-platform file locking ──────────────────────────────────────────────

class FileLock:
    """Context manager for cross-platform file locking.

    Windows: msvcrt.locking (byte-range lock)
    Linux/macOS: fcntl.flock  (advisory lock)
    """

    def __init__(self, path: Path):
        self.path = path
        self._f = None

    def __enter__(self):
        # Ensure lock file exists
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            import msvcrt
            self._f = open(self.path, "a+b")
            # Lock 1 byte from position 0; retries up to ~1s internally
            msvcrt.locking(self._f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            self._f = open(self.path, "a+")
            fcntl.flock(self._f.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._f is not None:
            if sys.platform == "win32":
                import msvcrt
                try:
                    msvcrt.locking(self._f.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError as e:
                    import warnings
                    warnings.warn(f"Failed to release lock {self.path}: {e}")
            else:
                import fcntl
                fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
            self._f.close()
            self._f = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _session_dir(session_id: str) -> Path:
    if not re.fullmatch(r'[0-9a-f]{8}', session_id):
        raise ValueError(f"Invalid session ID: {session_id!r}")
    return SESSIONS_DIR / session_id


def _check_session(session_id: str) -> Path:
    d = _session_dir(session_id)
    if not d.exists():
        print(json.dumps({"error": f"Session {session_id} not found"}))
        sys.exit(1)
    return d


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_init(args):
    """Initialize a new session and print its ID."""
    session_id = uuid.uuid4().hex[:8]
    sdir = _session_dir(session_id)
    sdir.mkdir(parents=True, exist_ok=True)

    meta = {
        "task": args.task,
        "created": time.time(),
        "participants": [],
    }
    with open(sdir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # Create empty messages file
    (sdir / "messages.jsonl").touch()

    print(json.dumps({"session_id": session_id, "task": args.task}, ensure_ascii=False), flush=True)


def cmd_send(args):
    """Append a message to the session log."""
    sdir = _check_session(args.session)
    lock = sdir / ".lock"

    msg = {
        "id": str(uuid.uuid4()),
        "from": args.sender,
        "ts": time.time(),
        "type": args.type,
        "content": args.content,
    }

    with FileLock(lock):
        # Refuse to write if session is stopped (check inside lock)
        if (sdir / "stop.flag").exists():
            print(json.dumps({"error": "Session has been stopped"}), flush=True)
            sys.exit(1)

        with open(sdir / "messages.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        # Update participants in meta
        meta_path = sdir / "meta.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if args.sender not in meta.get("participants", []):
                meta.setdefault("participants", []).append(args.sender)
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)

    print(json.dumps({"status": "sent", "id": msg["id"]}, ensure_ascii=False), flush=True)


def cmd_recv(args):
    """Return unread messages for *sender* (messages not from self, after cursor)."""
    sdir = _check_session(args.session)
    cursor_path = sdir / f"cursor-{args.sender}.json"
    msg_path = sdir / "messages.jsonl"
    stopped = (sdir / "stop.flag").exists()

    if not msg_path.exists():
        print(json.dumps({"messages": [], "stopped": stopped}, ensure_ascii=False), flush=True)
        return

    # Entire read+update inside lock to prevent duplicate delivery
    with FileLock(sdir / ".lock"):
        # Read cursor
        last_read_ts = 0.0
        last_read_id = ""
        if cursor_path.exists():
            try:
                with open(cursor_path, "r", encoding="utf-8") as f:
                    cursor = json.load(f)
                last_read_ts = cursor.get("last_read_ts", 0.0)
                last_read_id = cursor.get("last_read_id", "")
            except (json.JSONDecodeError, OSError):
                last_read_ts = 0.0
                last_read_id = ""

        # Collect unread messages (not from self, after cursor)
        unread = []
        with open(msg_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("from") == args.sender:
                    continue
                msg_ts = msg.get("ts", 0)
                msg_id = msg.get("id", "")
                if msg_ts > last_read_ts:
                    unread.append(msg)
                elif msg_ts == last_read_ts and msg_id != last_read_id:
                    # Same timestamp but different message — don't skip
                    unread.append(msg)

        # Update cursor
        if unread:
            cursor = {
                "last_read_id": unread[-1]["id"],
                "last_read_ts": unread[-1]["ts"],
            }
            with open(cursor_path, "w", encoding="utf-8") as f:
                json.dump(cursor, f, indent=2)

    stopped = (sdir / "stop.flag").exists()
    print(json.dumps({"messages": unread, "stopped": stopped}, ensure_ascii=False), flush=True)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Cross-window message channel for Claude Code"
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p = sub.add_parser("init", help="Create a new session")
    p.add_argument("--task", required=True, help="Task description")

    # send
    p = sub.add_parser("send", help="Send a message")
    p.add_argument("--session", required=True, help="Session ID")
    p.add_argument("--from", dest="sender", required=True, help="Sender (A/B/...)")
    p.add_argument("--type", default="message", help="Message type")
    p.add_argument("--content", required=True, help="Message content")

    # recv
    p = sub.add_parser("recv", help="Receive unread messages")
    p.add_argument("--session", required=True, help="Session ID")
    p.add_argument("--from", dest="sender", required=True, help="Recipient (A/B/...)")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "send":
        cmd_send(args)
    elif args.command == "recv":
        cmd_recv(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
