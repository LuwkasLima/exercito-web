#!/usr/bin/env python3
"""Smoke test: open the DuckDuckGo browser, go to Google, search, confirm results load,
and quit the browser. Repeats for RUNS consecutive runs.

The browser has no WebDriver/AppleScript support, so it is driven through macOS
UI automation (System Events keystrokes), the same way a person would use it.

Requires Accessibility permission for the app running this script
(System Settings > Privacy & Security > Accessibility).
"""
import os
import plistlib
import signal
import subprocess
import sys
import time
from pathlib import Path

APP = Path(os.environ.get("BROWSER_APP", "/Applications/DuckDuckGo.app"))
START_URL = os.environ.get("START_URL", "https://www.google.com")
START_TITLE = os.environ.get("START_TITLE", "Google")
QUERY = os.environ.get("SEARCH_QUERY", "Browser smoke test")
TIMEOUT = float(os.environ.get("TIMEOUT", "20"))
STEP_DELAY = float(os.environ.get("STEP_DELAY", "0.8"))
RUNS = int(os.environ.get("RUNS", "10"))
QUIT_TIMEOUT = float(os.environ.get("QUIT_TIMEOUT", "15"))
# Buttons that dismiss pop-ups shown on quit. Avoid "Cancel": it can cancel the quit.
DISMISS_BUTTONS = [
    b.strip()
    for b in os.environ.get(
        "DISMISS_BUTTONS",
        "Not Now|No Thanks|Skip|Dismiss|Close|Quit|Agora não|Não, obrigado|Pular|Fechar|Sair",
    ).split("|")
    if b.strip()
]

FRONTMOST_SCRIPT = """
tell application "System Events" to get bundle identifier of first process whose frontmost is true
"""

WINDOW_TITLE_SCRIPT = """
on run argv
    tell application "System Events"
        tell (first process whose bundle identifier is (item 1 of argv))
            if (count of windows) is 0 then return ""
            return name of front window
        end tell
    end tell
end run
"""

SHORTCUT_SCRIPT = """
on run argv
    tell application "System Events" to keystroke (item 1 of argv) using command down
end run
"""

TYPE_SCRIPT = """
on run argv
    tell application "System Events" to keystroke (item 1 of argv)
end run
"""

RETURN_SCRIPT = """
tell application "System Events" to key code 36
"""

QUIT_SCRIPT = """
on run argv
    ignoring application responses
        tell application id (item 1 of argv) to quit
    end ignoring
end run
"""

PID_SCRIPT = """
on run argv
    tell application "System Events"
        if not (exists (first process whose bundle identifier is (item 1 of argv))) then return ""
        return unix id of (first process whose bundle identifier is (item 1 of argv))
    end tell
end run
"""

# Clicks the first button whose name is in argv[2..]; otherwise lists the buttons found.
DISMISS_POPUP_SCRIPT = """
on run argv
    set wanted to rest of argv
    set found to {}
    tell application "System Events"
        tell (first process whose bundle identifier is (item 1 of argv))
            repeat with w in windows
                try
                    repeat with e in (entire contents of w)
                        if class of e is button then
                            set n to name of e
                            if n is not missing value then
                                if wanted contains n then
                                    click e
                                    return "clicked '" & n & "'"
                                end if
                                set end of found to n
                            end if
                        end if
                    end repeat
                end try
            end repeat
        end tell
    end tell
    set AppleScript's text item delimiters to ", "
    return "no known button; buttons found: " & (found as text)
end run
"""


class SmokeTestError(Exception):
    pass


def osascript(script, *args):
    result = subprocess.run(
        ["osascript", "-e", script, *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        if "assistive access" in err or "-25211" in err or "-1719" in err:
            raise SmokeTestError(
                "Accessibility permission missing. Allow the app running this "
                "script (Terminal / VS Code) under System Settings > Privacy & "
                "Security > Accessibility, then re-run."
            )
        raise SmokeTestError(f"osascript failed: {err}")
    return result.stdout.strip()


def step(message):
    print(f"→ {message}", flush=True)


def wait_for(condition, description, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.25)
    raise SmokeTestError(f"Timed out after {timeout:.0f}s waiting for {description}")


def bundle_id(app):
    info = app / "Contents" / "Info.plist"
    if not info.exists():
        raise SmokeTestError(f"Not an app bundle: {app}")
    with info.open("rb") as f:
        return plistlib.load(f)["CFBundleIdentifier"]


def is_frontmost(bid):
    return osascript(FRONTMOST_SCRIPT) == bid


def ensure_frontmost(bid):
    # Keystrokes go to whatever app is in front; never type into the wrong window.
    if not is_frontmost(bid):
        raise SmokeTestError("Browser lost focus; aborting so keystrokes don't go elsewhere")


def is_running(bid):
    return osascript(f'application id "{bid}" is running') == "true"


def quit_browser(bid):
    if not is_running(bid):
        return
    # Don't block on the reply: a pop-up shown on quit would hold it for minutes.
    osascript(QUIT_SCRIPT, bid)
    try:
        wait_for(lambda: not is_running(bid), "the browser to quit", timeout=QUIT_TIMEOUT)
        return
    except SmokeTestError:
        pass

    # Still running: most likely a pop-up (e.g. a feedback prompt) is in the way.
    print(f"  pop-up detected → {osascript(DISMISS_POPUP_SCRIPT, bid, *DISMISS_BUTTONS)}")
    try:
        wait_for(lambda: not is_running(bid), "the browser to quit", timeout=QUIT_TIMEOUT)
        return
    except SmokeTestError:
        pass

    print("  ⚠ browser did not quit; force-quitting so the next run starts clean")
    pid = osascript(PID_SCRIPT, bid)
    if pid:
        os.kill(int(pid), signal.SIGKILL)
    wait_for(lambda: not is_running(bid), "the browser to be force-quit")


def run(bid):
    step("Launching browser")
    subprocess.run(["open", "-a", str(APP)], check=True)
    osascript(f'tell application id "{bid}" to activate')
    wait_for(lambda: is_frontmost(bid), "the browser to come to the front")
    wait_for(lambda: osascript(WINDOW_TITLE_SCRIPT, bid) != "", "a browser window")
    time.sleep(STEP_DELAY)

    step("Opening a new tab")
    ensure_frontmost(bid)
    osascript(SHORTCUT_SCRIPT, "t")
    time.sleep(STEP_DELAY)

    step("Focusing the address bar")
    ensure_frontmost(bid)
    osascript(SHORTCUT_SCRIPT, "l")
    time.sleep(STEP_DELAY)

    step(f"Navigating to {START_URL}")
    ensure_frontmost(bid)
    osascript(TYPE_SCRIPT, START_URL)
    osascript(RETURN_SCRIPT)
    wait_for(
        lambda: osascript(WINDOW_TITLE_SCRIPT, bid).strip().lower() == START_TITLE.lower(),
        f"the page titled {START_TITLE!r} to load",
    )
    # Google focuses its search box on load; give it a moment to settle.
    time.sleep(STEP_DELAY * 2)

    step(f"Typing {QUERY!r} into the Google search box")
    ensure_frontmost(bid)
    osascript(TYPE_SCRIPT, QUERY)
    time.sleep(STEP_DELAY)

    step("Submitting search")
    ensure_frontmost(bid)
    osascript(RETURN_SCRIPT)

    step("Waiting for results page")
    wait_for(
        lambda: QUERY.lower() in osascript(WINDOW_TITLE_SCRIPT, bid).lower(),
        "the results page title to contain the query",
    )
    print(f"  window title: {osascript(WINDOW_TITLE_SCRIPT, bid)!r}")

    time.sleep(STEP_DELAY)
    step("Closing the browser")
    quit_browser(bid)


def main():
    try:
        bid = bundle_id(APP)
    except SmokeTestError as e:
        print(f"❌ {e}")
        return 1
    print(f"Browser: {APP} ({bid})")
    print(f"Query:   {QUERY!r}")
    print(f"Runs:    {RUNS}")

    results = []
    for i in range(1, RUNS + 1):
        print(f"\n=== Run {i}/{RUNS} ===")
        started = time.monotonic()
        try:
            run(bid)
            error = None
        except (SmokeTestError, subprocess.CalledProcessError) as e:
            error = str(e)
            # Start the next run from a clean state.
            try:
                quit_browser(bid)
            except SmokeTestError as quit_error:
                print(f"  (could not quit browser: {quit_error})")
        elapsed = time.monotonic() - started
        results.append((i, error, elapsed))
        if error:
            print(f"❌ Run {i} FAIL ({elapsed:.1f}s): {error}")
        else:
            print(f"✅ Run {i} PASS ({elapsed:.1f}s)")

    passed = sum(1 for _, error, _ in results if error is None)
    print(f"\n=== Summary: {passed}/{RUNS} passed ===")
    for i, error, elapsed in results:
        status = "PASS" if error is None else f"FAIL - {error}"
        print(f"  Run {i}: {status} ({elapsed:.1f}s)")
    return 0 if passed == RUNS else 1


if __name__ == "__main__":
    sys.exit(main())
