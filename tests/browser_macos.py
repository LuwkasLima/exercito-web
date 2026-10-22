"""macOS driver: controls the browser through macOS UI automation (System Events
keystrokes via osascript), since it has no WebDriver/AppleScript support.

Requires Accessibility permission for the app running the test
(System Settings > Privacy & Security > Accessibility).
"""
import os
import plistlib
import signal
import subprocess
from pathlib import Path

from smoke_common import SmokeTestError

APP = Path(os.environ.get("BROWSER_APP", "/Applications/DuckDuckGo.app"))

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


def bundle_id(app):
    info = app / "Contents" / "Info.plist"
    if not info.exists():
        raise SmokeTestError(f"Not an app bundle: {app}")
    with info.open("rb") as f:
        return plistlib.load(f)["CFBundleIdentifier"]


class Browser:
    def __init__(self):
        self.bid = bundle_id(APP)

    def describe(self):
        return f"{APP} ({self.bid})"

    def launch(self):
        subprocess.run(["open", "-a", str(APP)], check=True)

    def activate(self):
        osascript(f'tell application id "{self.bid}" to activate')

    def is_frontmost(self):
        return osascript(FRONTMOST_SCRIPT) == self.bid

    def has_window(self):
        return osascript(WINDOW_TITLE_SCRIPT, self.bid) != ""

    def page_title(self):
        return osascript(WINDOW_TITLE_SCRIPT, self.bid)

    def shortcut(self, key):
        osascript(SHORTCUT_SCRIPT, key)

    def type_text(self, text):
        osascript(TYPE_SCRIPT, text)

    def press_return(self):
        osascript(RETURN_SCRIPT)

    def is_running(self):
        return osascript(f'application id "{self.bid}" is running') == "true"

    def request_quit(self):
        # Don't block on the reply: a pop-up shown on quit would hold it for minutes.
        osascript(QUIT_SCRIPT, self.bid)

    def dismiss_popup(self, buttons):
        return osascript(DISMISS_POPUP_SCRIPT, self.bid, *buttons)

    def force_quit(self):
        pid = osascript(PID_SCRIPT, self.bid)
        if pid:
            os.kill(int(pid), signal.SIGKILL)
