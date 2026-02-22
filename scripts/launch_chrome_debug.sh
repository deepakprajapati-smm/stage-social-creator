#!/bin/bash
# scripts/launch_chrome_debug.sh
# Launch Chrome with remote debugging enabled for FB + YT automation.
#
# Run ONCE before using create_profiles.py or the API.
# Then log into STAGE's Facebook + Google accounts in the Chrome window.
# Leave Chrome running — sessions persist.
#
# Chrome 136+: Must use a non-default profile (NOT the Default profile).

PROFILE_DIR="$HOME/.chrome-stage-debug"
DEBUG_PORT=9222

echo "Launching Chrome with CDP on port $DEBUG_PORT..."
echo "Profile: $PROFILE_DIR"
echo ""
echo "After Chrome opens:"
echo "  1. Log into STAGE Facebook account"
echo "  2. Log into STAGE Google/YouTube account"
echo "  3. Leave this window open (do not close)"
echo ""

# macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if [ ! -f "$CHROME" ]; then
        echo "ERROR: Chrome not found at $CHROME"
        echo "Install Chrome from: https://chrome.google.com"
        exit 1
    fi
    "$CHROME" \
        --remote-debugging-port=$DEBUG_PORT \
        --user-data-dir="$PROFILE_DIR" \
        --no-first-run \
        --no-default-browser-check \
        2>/dev/null &

# Linux
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    google-chrome \
        --remote-debugging-port=$DEBUG_PORT \
        --user-data-dir="$PROFILE_DIR" \
        --no-first-run \
        --no-default-browser-check \
        2>/dev/null &
fi

echo "Chrome launched (PID: $!)"
echo "CDP available at: http://localhost:$DEBUG_PORT"
echo ""
echo "Verify with: curl http://localhost:$DEBUG_PORT/json/version"
