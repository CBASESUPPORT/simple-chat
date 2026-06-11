#!/usr/bin/env bash
#
# Launches the chat server + an ngrok tunnel together, then prints the
# ready-to-share public links. Stop everything with Ctrl+C.
#
set -euo pipefail
cd "$(dirname "$0")"

PORT=3000
NGROK="$(command -v ngrok || echo /opt/homebrew/bin/ngrok)"
PYTHON="$(command -v python3 || echo /Library/Frameworks/Python.framework/Versions/3.14/bin/python3)"

# --- Free the port if a previous run left something behind ---
OLD=$(lsof -nP -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null || true)
if [ -n "$OLD" ]; then
  echo "  (freeing port $PORT — killing leftover process $OLD)"
  kill $OLD 2>/dev/null || true
  sleep 1
fi

# --- Clean up both background processes on exit ---
CHAT_PID=""
NGROK_PID=""
cleanup() {
  echo ""
  echo "  Shutting down…"
  [ -n "$NGROK_PID" ] && kill "$NGROK_PID" 2>/dev/null || true
  [ -n "$CHAT_PID" ]  && kill "$CHAT_PID"  2>/dev/null || true
  echo "  Bye! 👋"
}
trap cleanup EXIT INT TERM

# --- Start the chat server ---
PORT=$PORT "$PYTHON" chat.py >/tmp/simple-chat.log 2>&1 &
CHAT_PID=$!
sleep 1

# --- Start ngrok ---
"$NGROK" http $PORT --log=stdout >/tmp/simple-chat-ngrok.log 2>&1 &
NGROK_PID=$!

# --- Wait for ngrok to report its public URL (via its local API) ---
echo "  Starting tunnel…"
URL=""
for i in $(seq 1 30); do
  URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null \
        | grep -o '"public_url":"https://[^"]*' \
        | head -n1 | cut -d'"' -f4 || true)
  [ -n "$URL" ] && break
  sleep 0.5
done

if [ -z "$URL" ]; then
  echo ""
  echo "  ⚠️  Couldn't get the ngrok URL automatically."
  echo "     Check /tmp/simple-chat-ngrok.log — you may need to run 'ngrok config add-authtoken …' once."
  echo "     The chat is still running locally on http://localhost:$PORT"
  wait
fi

echo ""
echo "  ✅ Chat is LIVE on the internet!"
echo ""
echo "  ────────────────────────────────────────────"
echo "   YOUR link:      $URL/You"
echo "   SHARE this one: $URL/Guest"
echo "  ────────────────────────────────────────────"
echo ""
echo "  Send the SHARE link to anyone, anywhere."
echo "  (First visit shows an ngrok 'Visit Site' page — that's normal.)"
echo ""
echo "  Stop everything with Ctrl+C."
echo ""

# Keep running until Ctrl+C.
wait
