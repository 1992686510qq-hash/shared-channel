#!/usr/bin/env python3
"""Browser-based real-time viewer for Shared Channel sessions.

Usage:
    python viewer.py --session SESSION_ID          # Start server, auto-open browser
    python viewer.py --session SESSION_ID --port 8765  # Specify port
    python viewer.py --session SESSION_ID --no-browser  # Don't open browser
"""

import argparse
import json
import os
import sys
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

SESSIONS_DIR = Path(os.environ.get(
    "SHARED_CHANNEL_DIR",
    r"D:\Claude Code\shared-channel\sessions"
))

# ──────────────────────────────────────────────────────────────────────────────
# HTML template — single-page chat app
# ──────────────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shared Channel — {session_id}</title>
<style>
* {{
    margin: 0; padding: 0; box-sizing: border-box;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", "Helvetica Neue", sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
}}

/* ── Header ──────────────────────────────────────────────────────────── */

.header {{
    background: #16213e;
    border-bottom: 1px solid #0f3460;
    padding: 16px 24px;
    flex-shrink: 0;
}}

.header h1 {{
    font-size: 18px;
    font-weight: 600;
    color: #e94560;
    margin-bottom: 4px;
}}

.header .meta {{
    font-size: 13px;
    color: #8899aa;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
}}

.header .meta span {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
}}

/* ── Stopped banner ──────────────────────────────────────────────────── */

.banner {{
    background: #e94560;
    color: #fff;
    text-align: center;
    padding: 10px;
    font-size: 14px;
    font-weight: 600;
    flex-shrink: 0;
    display: none;
}}

.banner.visible {{
    display: block;
}}

/* ── Message area ─────────────────────────────────────────────────────── */

.messages {{
    flex: 1;
    overflow-y: auto;
    padding: 20px 24px;
}}

.message-row {{
    display: flex;
    margin-bottom: 12px;
    align-items: flex-end;
    gap: 8px;
}}

.message-row.from-A {{
    justify-content: flex-start;
}}

.message-row.from-B {{
    justify-content: flex-end;
}}

.message-row.from-other {{
    justify-content: flex-start;
}}

.bubble {{
    max-width: 70%;
    padding: 10px 14px;
    border-radius: 16px;
    font-size: 15px;
    line-height: 1.5;
    word-break: break-word;
    position: relative;
}}

.from-A .bubble {{
    background: #0f3460;
    color: #e0e0e0;
    border-bottom-left-radius: 4px;
}}

.from-B .bubble {{
    background: #1a6b3c;
    color: #e0e0e0;
    border-bottom-right-radius: 4px;
}}

.from-other .bubble {{
    background: #533483;
    color: #e0e0e0;
    border-bottom-left-radius: 4px;
}}

.bubble .sender-tag {{
    display: block;
    font-size: 11px;
    font-weight: 700;
    margin-bottom: 4px;
    opacity: 0.85;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

.from-A .sender-tag {{ color: #64b5f6; }}
.from-B .sender-tag {{ color: #81c784; }}
.from-other .sender-tag {{ color: #ce93d8; }}

.bubble .type-tag {{
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    background: rgba(255,255,255,0.15);
    padding: 1px 6px;
    border-radius: 8px;
    margin-right: 4px;
}}

.time-stamp {{
    font-size: 11px;
    color: #556677;
    white-space: nowrap;
    flex-shrink: 0;
    padding-bottom: 4px;
}}

.from-A .time-stamp {{ order: 2; }}
.from-B .time-stamp {{ order: -1; text-align: right; }}
.from-other .time-stamp {{ order: 2; }}

/* ── No messages ──────────────────────────────────────────────────────── */

.empty-state {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #445566;
    font-size: 16px;
    gap: 8px;
}}

.empty-state .icon {{
    font-size: 48px;
    opacity: 0.5;
}}

/* ── Footer ───────────────────────────────────────────────────────────── */

.footer {{
    background: #16213e;
    border-top: 1px solid #0f3460;
    padding: 12px 24px;
    font-size: 12px;
    color: #556677;
    text-align: center;
    flex-shrink: 0;
}}

.footer .dot {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 6px;
    background: #4caf50;
    animation: pulse 1.5s infinite;
}}

.footer .dot.stopped {{
    background: #e94560;
    animation: none;
}}

@keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.4; }}
}}

/* ── Scrollbar ────────────────────────────────────────────────────────── */

.messages::-webkit-scrollbar {{
    width: 6px;
}}

.messages::-webkit-scrollbar-track {{
    background: transparent;
}}

.messages::-webkit-scrollbar-thumb {{
    background: #0f3460;
    border-radius: 3px;
}}

.messages::-webkit-scrollbar-thumb:hover {{
    background: #1a4a7a;
}}
</style>
</head>
<body>

<div class="header">
    <h1>Shared Channel</h1>
    <div class="meta">
        <span>📋 {session_id}</span>
        <span>📝 {task}</span>
        <span>🕐 {created}</span>
    </div>
</div>

<div class="banner" id="stoppedBanner">⚡ 会话已结束</div>

<div class="messages" id="messagesContainer">
    <div class="empty-state" id="emptyState">
        <div class="icon">💬</div>
        <div>暂无消息</div>
    </div>
</div>

<div class="footer">
    <span class="dot" id="statusDot"></span>
    <span id="statusText">监听中...</span>
    <span style="margin-left: 12px;">|</span>
    <span style="margin-left: 12px;" id="msgCount">0 条消息</span>
</div>

<script>
const sessionId = "{session_id}";
let lastTs = 0;
let stopped = false;
let msgCount = 0;
const POLL_INTERVAL = 2000;

const container = document.getElementById("messagesContainer");
const emptyState = document.getElementById("emptyState");
const stoppedBanner = document.getElementById("stoppedBanner");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const msgCountEl = document.getElementById("msgCount");

function formatTs(ts) {{
    const d = new Date(ts * 1000);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    return hh + ":" + mm + ":" + ss;
}}

function getRowClass(sender) {{
    if (sender === "A") return "from-A";
    if (sender === "B") return "from-B";
    return "from-other";
}}

function createMessageRow(msg) {{
    const row = document.createElement("div");
    row.className = "message-row " + getRowClass(msg.from);

    const timeSpan = document.createElement("span");
    timeSpan.className = "time-stamp";
    timeSpan.textContent = formatTs(msg.ts);

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    const senderTag = document.createElement("span");
    senderTag.className = "sender-tag";
    senderTag.textContent = msg.from;

    bubble.appendChild(senderTag);

    if (msg.type && msg.type !== "message") {{
        const typeTag = document.createElement("span");
        typeTag.className = "type-tag";
        typeTag.textContent = msg.type;
        bubble.appendChild(typeTag);
    }}

    const contentSpan = document.createElement("span");
    contentSpan.textContent = msg.content;
    bubble.appendChild(contentSpan);

    row.appendChild(timeSpan);
    row.appendChild(bubble);

    return row;
}}

function appendMessages(msgs) {{
    if (msgs.length === 0) return;
    // Remove empty state if present
    if (emptyState) emptyState.style.display = "none";
    for (const msg of msgs) {{
        container.appendChild(createMessageRow(msg));
        msgCount++;
        if (msg.ts > lastTs) lastTs = msg.ts;
    }}
    container.scrollTop = container.scrollHeight;
    msgCountEl.textContent = msgCount + " 条消息";
}}

function setStopped() {{
    stopped = true;
    stoppedBanner.classList.add("visible");
    statusDot.classList.add("stopped");
    statusText.textContent = "已结束";
}}

async function poll() {{
    if (stopped) return;
    try {{
        const resp = await fetch("/api/messages?session=" + sessionId + "&after=" + lastTs);
        const data = await resp.json();
        if (data.stopped) {{
            setStopped();
        }}
        appendMessages(data.messages || []);
        // Also check if any new messages from others might have come
        if (data.last_message_ts && data.last_message_ts > lastTs) {{
            // Re-fetch with corrected bounds — but appendMessages already handles
        }}
    }} catch (e) {{
        console.error("Poll error:", e);
    }}
}}

function init() {{
    // Initial load: use after=0 to get all messages
    fetch("/api/messages?session=" + sessionId + "&after=0")
        .then(r => r.json())
        .then(data => {{
            if (data.stopped) setStopped();
            appendMessages(data.messages || []);
            lastTs = data.last_message_ts || lastTs;
        }})
        .catch(e => console.error("Init error:", e));

    // Start polling
    setInterval(poll, POLL_INTERVAL);
}}

document.addEventListener("DOMContentLoaded", init);
</script>

</body>
</html>"""

# ──────────────────────────────────────────────────────────────────────────────
# Request handler
# ──────────────────────────────────────────────────────────────────────────────

class ViewerHandler(BaseHTTPRequestHandler):
    """Serve the chat UI and a JSON API for messages."""

    session_id: str = ""  # Set by factory

    def log_message(self, format, *args):
        """Suppress default stderr logging; use our own format."""
        pass  # Silent — use print only for startup

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._serve_index()
        elif path == "/api/messages":
            self._api_messages(qs)
        else:
            self.send_error(404)

    def _serve_index(self):
        sdir = SESSIONS_DIR / self.session_id
        if not sdir.exists():
            html = "<html><body><h2>Session not found</h2></body></html>"
            self._send_html(html, 404)
            return

        meta = self._read_meta(sdir)
        task = meta.get("task", "N/A")
        created_ts = meta.get("created", 0)
        created_str = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(created_ts)
        ) if created_ts else "N/A"

        html = HTML_TEMPLATE.format(
            session_id=self.session_id,
            task=task,
            created=created_str,
        )
        self._send_html(html)

    def _api_messages(self, qs):
        sdir = SESSIONS_DIR / self.session_id
        if not sdir.exists():
            self._send_json({"error": "Session not found"}, 404)
            return

        # Parse 'after' parameter (float timestamp)
        after_str = qs.get("after", ["0"])[0]
        try:
            after = float(after_str)
        except ValueError:
            after = 0.0

        meta = self._read_meta(sdir)
        stopped = (sdir / "stop.flag").exists()

        messages = []
        last_message_ts = after

        msg_path = sdir / "messages.jsonl"
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
                    ts = msg.get("ts", 0)
                    if ts > after:
                        messages.append(msg)
                        if ts > last_message_ts:
                            last_message_ts = ts

        self._send_json({
            "session_id": self.session_id,
            "task": meta.get("task"),
            "created": meta.get("created"),
            "participants": meta.get("participants", []),
            "stopped": stopped,
            "messages": messages,
            "last_message_ts": last_message_ts,
        })

    @staticmethod
    def _read_meta(sdir: Path) -> dict:
        meta_path = sdir / "meta.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}


def make_handler(session_id: str):
    """Factory to inject session_id into the handler class."""
    class Handler(ViewerHandler):
        pass
    Handler.session_id = session_id
    return Handler


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Browser-based real-time viewer for Shared Channel"
    )
    parser.add_argument("--session", required=True, help="Session ID to view")
    parser.add_argument("--port", type=int, default=8765, help="HTTP server port (default: 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")

    args = parser.parse_args()

    # Validate session exists
    sdir = SESSIONS_DIR / args.session
    if not sdir.exists():
        print(f"[ERROR] 会话 {args.session} 不存在", file=sys.stderr)
        sys.exit(1)

    handler_class = make_handler(args.session)
    server = HTTPServer(("127.0.0.1", args.port), handler_class)

    url = f"http://localhost:{args.port}"
    print(f"Viewer running at {url}")
    print(f"Session: {args.session}")
    print("Press Ctrl+C to stop")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
