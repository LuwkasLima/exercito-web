#!/usr/bin/env bash
# Runs the smoke test on its own X display, so it works from a Wayland desktop
# and the test's keystrokes can't reach your other windows.
#
#   scripts/run_linux.sh              # in a window on your desktop (Xephyr), so you can watch
#   HEADLESS=1 scripts/run_linux.sh   # on an invisible display (Xvfb), e.g. for CI
#
# Other settings (RUNS, SEARCH_QUERY, ...) are passed through to the test.
set -euo pipefail

DISPLAY_NUM="${DISPLAY_NUM:-99}"
SCREEN_SIZE="${SCREEN_SIZE:-1280x800}"
WM="${WM:-openbox}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "${HEADLESS:-0}" == 1 ]]; then
    server=(Xvfb ":$DISPLAY_NUM" -screen 0 "${SCREEN_SIZE}x24" -nolisten tcp)
else
    if [[ -z "${DISPLAY:-}" ]]; then
        echo "❌ No desktop display to show the test window on. Use HEADLESS=1." >&2
        exit 1
    fi
    server=(Xephyr ":$DISPLAY_NUM" -screen "$SCREEN_SIZE" -title "Browser smoke test" -resizeable -nolisten tcp)
fi

missing=()
for cmd in "${server[0]}" "$WM" xdotool wmctrl; do
    command -v "$cmd" >/dev/null || missing+=("$cmd")
done
if (( ${#missing[@]} )); then
    echo "❌ Missing: ${missing[*]}" >&2
    echo "   Install with: sudo apt install xdotool wmctrl openbox xserver-xephyr xvfb" >&2
    exit 1
fi
if [[ -e "/tmp/.X11-unix/X$DISPLAY_NUM" ]]; then
    echo "❌ Display :$DISPLAY_NUM is already in use. Pick another with DISPLAY_NUM=..." >&2
    exit 1
fi

pids=()
cleanup() {
    for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

"${server[@]}" >/dev/null 2>&1 &
pids+=($!)
for _ in $(seq 50); do
    [[ -e "/tmp/.X11-unix/X$DISPLAY_NUM" ]] && break
    sleep 0.1
done

export DISPLAY=":$DISPLAY_NUM"
unset WAYLAND_DISPLAY
"$WM" >/dev/null 2>&1 &
pids+=($!)
for _ in $(seq 50); do
    wmctrl -m >/dev/null 2>&1 && break
    sleep 0.1
done

python3 "$ROOT/tests/smoke_search.py"
