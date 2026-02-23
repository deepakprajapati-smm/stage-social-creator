#!/bin/bash
# Launch Chrome in CDP debug mode for STAGE Social Creator
# Run this ONCE — Chrome stays open, sessions persist forever

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE_DIR="${HOME}/.chrome-stage-debug"
CDP_PORT=9222

mkdir -p "$PROFILE_DIR"

echo "[Chrome] Launching with CDP on port $CDP_PORT..."
"$CHROME" \
  --remote-debugging-port=$CDP_PORT \
  --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --no-default-browser-check \
  --disable-blink-features=AutomationControlled \
  "https://www.facebook.com" &

echo "[Chrome] PID: $!"
echo "[Chrome] CDP URL: http://localhost:$CDP_PORT"
echo "[Chrome] Profile: $PROFILE_DIR"
