#!/usr/bin/env python3
"""Simple two-person chat — zero dependencies, pure Python stdlib.

Run:  python3 chat.py    (then open the two links it prints)

How it works: messages are POSTed to /send. Each browser polls GET /messages
every second for anything new. Polling (not streaming) is used because some
hosts/proxies buffer streamed responses, which breaks live delivery. No
database; messages live in memory.
"""

import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse, parse_qs

PORT = int(os.environ.get("PORT", 3000))

_lock = threading.Lock()
_history = []          # recent messages so a fresh link sees context
_counter = 0           # monotonic id so clients can ask "anything after id N?"
HISTORY_LIMIT = 200


def add_message(name, text):
    global _counter
    with _lock:
        _counter += 1
        msg = {
            "id": _counter,
            "name": str(name)[:30],
            "text": text,
            "time": int(time.time() * 1000),
        }
        _history.append(msg)
        del _history[:-HISTORY_LIMIT]
        return msg


def messages_after(since_id):
    with _lock:
        return [m for m in _history if m["id"] > since_id]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def _json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Poll for new messages: /messages?since=<id>
        if path == "/messages":
            qs = parse_qs(parsed.query)
            try:
                since = int(qs.get("since", ["0"])[0])
            except ValueError:
                since = 0
            self._json({"messages": messages_after(since)})
            return

        # Any other path → the chat page. Name comes from the path: /You, /Guest…
        name = unquote(path.lstrip("/")) or "Guest"
        body = PAGE.replace("__NAME__", name.replace('"', "")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/send":
            self.send_response(404)
            self.end_headers()
            return
        length = min(int(self.headers.get("Content-Length", 0)), 10000)
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
            text = str(data.get("text", ""))[:1000].strip()
            if text:
                add_message(data.get("name", "Anon"), text)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
        except Exception:
            self.send_response(400)
            self.end_headers()


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Chat</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, system-ui, sans-serif;
         background: #0f1115; color: #e7e9ee; height: 100dvh;
         display: flex; flex-direction: column; }
  header { padding: 14px 18px; background: #171a21; border-bottom: 1px solid #262b36;
           font-weight: 600; display: flex; align-items: center; gap: 8px; }
  header .dot { width: 9px; height: 9px; border-radius: 50%; background: #34d399; }
  #log { flex: 1; overflow-y: auto; padding: 18px; display: flex;
         flex-direction: column; gap: 10px; }
  .msg { max-width: 75%; padding: 9px 13px; border-radius: 14px; line-height: 1.4;
         word-wrap: break-word; }
  .msg .who { font-size: 11px; opacity: .6; margin-bottom: 2px; }
  .mine { align-self: flex-end; background: #2563eb; border-bottom-right-radius: 4px; }
  .theirs { align-self: flex-start; background: #262b36; border-bottom-left-radius: 4px; }
  form { display: flex; gap: 8px; padding: 12px; background: #171a21;
         border-top: 1px solid #262b36; }
  input { flex: 1; padding: 12px 14px; border-radius: 10px; border: 1px solid #2c3340;
          background: #0f1115; color: #e7e9ee; font-size: 15px; outline: none; }
  input:focus { border-color: #2563eb; }
  button { padding: 0 18px; border: 0; border-radius: 10px; background: #2563eb;
           color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; }
  button:active { transform: scale(.97); }
</style>
</head>
<body>
  <header><span class="dot"></span> Chatting as <span id="me">__NAME__</span></header>
  <div id="log"></div>
  <form id="f">
    <input id="t" placeholder="Type a message…" autocomplete="off" autofocus />
    <button>Send</button>
  </form>
<script>
  const me = document.getElementById("me").textContent;
  const log = document.getElementById("log");
  let lastId = 0;

  function add(m) {
    const el = document.createElement("div");
    el.className = "msg " + (m.name === me ? "mine" : "theirs");
    el.innerHTML = '<div class="who"></div><div class="body"></div>';
    el.querySelector(".who").textContent = m.name;
    el.querySelector(".body").textContent = m.text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
  }

  async function poll() {
    try {
      const r = await fetch("/messages?since=" + lastId, { cache: "no-store" });
      const data = await r.json();
      for (const m of data.messages) {
        add(m);
        if (m.id > lastId) lastId = m.id;
      }
    } catch (e) { /* ignore a missed poll; try again next tick */ }
  }

  // Poll about once a second for new messages.
  setInterval(poll, 1000);
  poll();

  document.getElementById("f").addEventListener("submit", async (e) => {
    e.preventDefault();
    const t = document.getElementById("t");
    const text = t.value.trim();
    if (!text) return;
    t.value = "";
    await fetch("/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: me, text }),
    });
    poll(); // show our own message immediately
  });
</script>
</body>
</html>"""


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


if __name__ == "__main__":
    # If the preferred port is busy, walk up until we find a free one.
    server = None
    port = PORT
    for port in range(PORT, PORT + 20):
        try:
            server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit(f"Could not find a free port in {PORT}-{PORT + 19}.")

    ip = lan_ip()
    print("\n  ✅ Chat server running!\n")
    if port != PORT:
        print(f"  (port {PORT} was busy — using {port} instead)\n")
    print(f"  Your link:    http://{ip}:{port}/You")
    print(f"  Share link:   http://{ip}:{port}/Guest")
    print("\n  (On the same Wi-Fi, the other person opens the Share link.)")
    print("  Stop with Ctrl+C.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Bye! 👋\n")
