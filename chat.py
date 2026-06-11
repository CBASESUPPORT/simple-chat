#!/usr/bin/env python3
"""Simple two-person chat — zero dependencies, pure Python stdlib.

Run:  python3 chat.py    (then open the two links it prints)

How it works: messages are POSTed to /send and pushed to everyone listening
on the SSE stream GET /events. No database; messages live in memory.
"""

import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", 3000))

_lock = threading.Lock()
_clients = []          # list of wfile streams for connected SSE listeners
_history = []          # recent messages so a fresh link sees context
HISTORY_LIMIT = 50


def broadcast(msg):
    payload = ("data: " + json.dumps(msg) + "\n\n").encode("utf-8")
    with _lock:
        _history.append(msg)
        del _history[:-HISTORY_LIMIT]
        dead = []
        for wfile in _clients:
            try:
                wfile.write(payload)
                wfile.flush()
            except Exception:
                dead.append(wfile)
        for d in dead:
            _clients.remove(d)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self.wfile.write(b"\n")
                with _lock:
                    for m in _history:
                        self.wfile.write(("data: " + json.dumps(m) + "\n\n").encode())
                    self.wfile.flush()
                    _clients.append(self.wfile)
                # Hold the connection open; heartbeat keeps it alive.
                while True:
                    time.sleep(15)
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                with _lock:
                    if self.wfile in _clients:
                        _clients.remove(self.wfile)
            return

        # Any other path → the chat page. Name comes from the path: /You, /Guest…
        from urllib.parse import unquote
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
                broadcast({
                    "name": str(data.get("name", "Anon"))[:30],
                    "text": text,
                    "time": int(time.time() * 1000),
                })
            self.send_response(200)
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
  const seen = new Set();

  function add(m) {
    const key = m.time + m.name + m.text;
    if (seen.has(key)) return;
    seen.add(key);
    const el = document.createElement("div");
    el.className = "msg " + (m.name === me ? "mine" : "theirs");
    el.innerHTML = '<div class="who"></div><div class="body"></div>';
    el.querySelector(".who").textContent = m.name;
    el.querySelector(".body").textContent = m.text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
  }

  const es = new EventSource("/events");
  es.onmessage = (e) => add(JSON.parse(e.data));

  document.getElementById("f").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = document.getElementById("t");
    const text = t.value.trim();
    if (!text) return;
    t.value = "";
    fetch("/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: me, text }),
    });
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
