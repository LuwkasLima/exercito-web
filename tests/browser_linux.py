"""Linux driver: controls Firefox through X11 UI automation (xdotool keystrokes,
wmctrl window lists), the same way a person would use it.

Wayland doesn't let one app type into another or read its window titles, so the
browser must run on an X11 display: an Xorg session, or the Xephyr/Xvfb display
that scripts/run_linux.sh starts.

Firefox runs in test profile folders the test creates, which runs can take
turns using (see select_profile). Only windows of the Firefox started by this
test are touched, so other Firefox windows on the same display are left alone.
"""
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from smoke_common import SmokeTestError, wait_for

BROWSER_CMD = shlex.split(os.environ.get("BROWSER_CMD", "firefox"))
LAUNCH_TIMEOUT = float(os.environ.get("LAUNCH_TIMEOUT", "60"))

# Written to user.js on every launch: skip first-run pages, quit prompts and
# crash recovery.
USER_PREFS = {
    "browser.shell.checkDefaultBrowser": False,
    "browser.aboutwelcome.enabled": False,
    "browser.startup.homepage_override.mstone": "ignore",
    "startup.homepage_welcome_url": "",
    "startup.homepage_welcome_url.additional": "",
    "browser.startup.page": 0,
    "datareporting.policy.dataSubmissionPolicyBypassNotification": True,
    "toolkit.telemetry.reportingpolicy.firstRun": False,
    "browser.warnOnQuit": False,
    "browser.warnOnQuitShortcut": False,
    "browser.tabs.warnOnClose": False,
    "browser.sessionstore.resume_from_crash": False,
    # Firefox's built-in fingerprinting protection: reports a common user agent,
    # screen size, time zone (UTC) and language instead of this machine's.
    "privacy.resistFingerprinting": os.environ.get("RESIST_FINGERPRINTING", "1") == "1",
    # Request English pages without showing a prompt bar about it.
    "privacy.spoof_english": 2,
}

TITLE_SUFFIX = re.compile(r"(^|\s+[—–-]\s+)Mozilla Firefox$")


def default_profile_dir():
    if os.environ.get("FIREFOX_PROFILE_DIR"):
        return Path(os.environ["FIREFOX_PROFILE_DIR"]).expanduser()
    # The snap can't see the host's /tmp or hidden folders in $HOME.
    if Path("/snap/bin/firefox").exists() and Path(BROWSER_CMD[0]).name == "firefox":
        return Path.home() / "snap/firefox/common/smoke-test-profiles"
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache / "browser-smoke-test/profiles"


# The test's profile folders, and their Firefox logs next to them, are created in here.
PROFILE_DIR = default_profile_dir()


def tool(*args, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    if check and result.returncode != 0:
        raise SmokeTestError(f"{args[0]} failed: {result.stderr.strip()}")
    return result


class Browser:
    def __init__(self):
        missing = [t for t in ("xdotool", "wmctrl") if not shutil.which(t)]
        if missing:
            raise SmokeTestError(
                f"Missing {', '.join(missing)}. Install with: sudo apt install xdotool wmctrl"
            )
        if not shutil.which(BROWSER_CMD[0]):
            raise SmokeTestError(f"Browser not found: {BROWSER_CMD[0]}")
        if os.environ.get("WAYLAND_DISPLAY"):
            raise SmokeTestError(
                "This is a Wayland session, where keystrokes can't be sent to other "
                "apps. Run scripts/run_linux.sh, which starts a separate X display."
            )
        if not os.environ.get("DISPLAY"):
            raise SmokeTestError("No X display (DISPLAY is not set). Run scripts/run_linux.sh.")
        if tool("wmctrl", "-m", check=False).returncode != 0:
            raise SmokeTestError(
                f"No window manager on display {os.environ['DISPLAY']}; "
                "focus can't be checked without one. Run scripts/run_linux.sh."
            )
        self.proc = None
        self.profiles = {}  # profile number -> folder, created on first use
        self.failed = set()  # folders of profiles that had a failed run
        self.profile = None  # the folder the next launch uses
        self.log = None  # Firefox's output with that profile, for when it fails to start

    def describe(self):
        return f"{' '.join(BROWSER_CMD)} on display {os.environ['DISPLAY']}\nProfiles: in {PROFILE_DIR}"

    def select_profile(self, number):
        """Makes the next launch use profile `number`, creating a new, empty
        folder for it on first use. Later runs with it keep its cookies etc."""
        if number not in self.profiles:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            self.profiles[number] = Path(tempfile.mkdtemp(prefix=f"profile{number}-", dir=PROFILE_DIR))
        self.profile = self.profiles[number]
        self.log = self.profile.with_name(self.profile.name + ".log")

    def mark_failed(self):
        """Records that a run with the current profile failed, so it's kept."""
        if self.profile is not None:
            self.failed.add(self.profile)

    def cleanup_profiles(self, keep):
        """Deletes the profile folders and logs created so far, except those of
        failed runs (or all, if `keep`). Returns a note for each one kept."""
        notes = []
        running = self.is_running()
        for profile in self.profiles.values():
            log = profile.with_name(profile.name + ".log")
            if keep or running or profile in self.failed:
                notes.append(f"profile kept: {profile} (log: {log})")
            else:
                shutil.rmtree(profile, ignore_errors=True)
                log.unlink(missing_ok=True)
        self.profiles.clear()
        self.profile = self.log = None
        return notes

    def _ours(self, pid):
        # Firefox and its helpers stay in the process group started in launch().
        try:
            return self.proc is not None and os.getpgid(pid) == self.proc.pid
        except (ProcessLookupError, PermissionError):
            return False

    def _windows(self):
        """Returns [(window id, title)] for this browser's windows, oldest first."""
        windows = []
        for line in tool("wmctrl", "-lp").stdout.splitlines():
            parts = line.split(None, 4)
            if len(parts) >= 4 and self._ours(int(parts[2])):
                windows.append((int(parts[0], 16), parts[4] if len(parts) == 5 else ""))
        return windows

    def _active_window(self):
        result = tool("xdotool", "getactivewindow", check=False)
        return int(result.stdout) if result.returncode == 0 else None

    def launch(self):
        if self.profile is None:
            self.select_profile(1)
        (self.profile / "user.js").write_text(
            "".join(f'user_pref("{k}", {json.dumps(v)});\n' for k, v in USER_PREFS.items())
        )
        # DISABLE_WAYLAND stops the snap's launcher from forcing GDK_BACKEND=wayland
        # whenever the desktop's Wayland socket exists.
        env = dict(os.environ, MOZ_ENABLE_WAYLAND="0", DISABLE_WAYLAND="1", GNOME_ACCESSIBILITY="1")
        # Appended, so a failed run's output isn't lost to later runs with the profile.
        with self.log.open("a") as log:
            self.proc = subprocess.Popen(
                [*BROWSER_CMD, "--no-remote", "--profile", str(self.profile)],
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        wait_for(
            lambda: self._windows() or not self.is_running(),
            "Firefox to open a window",
            timeout=LAUNCH_TIMEOUT,
        )
        if not self._windows():
            last_lines = "\n    ".join(self.log.read_text(errors="replace").splitlines()[-5:])
            raise SmokeTestError(f"Firefox exited without opening a window. From {self.log}:\n    {last_lines}")

    def activate(self):
        tool("xdotool", "windowactivate", str(self._windows()[-1][0]), check=False)

    def is_frontmost(self):
        active = self._active_window()
        return any(wid == active for wid, _ in self._windows())

    def has_window(self):
        return bool(self._windows())

    def page_title(self):
        windows = self._windows()
        if not windows:
            return ""
        active = self._active_window()
        title = next((t for wid, t in windows if wid == active), windows[-1][1])
        return TITLE_SUFFIX.sub("", title)

    def shortcut(self, key):
        tool("xdotool", "key", "--clearmodifiers", f"ctrl+{key}")

    def type_text(self, text):
        tool("xdotool", "type", "--clearmodifiers", "--delay", "30", "--", text)

    def press_return(self):
        tool("xdotool", "key", "--clearmodifiers", "Return")

    def is_running(self):
        if self.proc is None:
            return False
        self.proc.poll()  # reap the launcher if it has exited
        try:
            os.killpg(self.proc.pid, 0)
            return True
        except PermissionError:
            return True  # e.g. snap's setuid-root launcher is still in the group
        except ProcessLookupError:
            return False

    def request_quit(self):
        # Closing the last window quits Firefox, like the Quit menu item.
        for wid, _ in self._windows():
            tool("wmctrl", "-i", "-c", hex(wid), check=False)

    def _atspi_apps(self):
        """Returns (Atspi, GLib, [this browser's apps in the AT-SPI accessibility
        tree]); Atspi is None if the AT-SPI Python bindings aren't installed."""
        try:
            import gi

            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi, GLib
        except (ImportError, ValueError):
            return None, None, []
        apps = []
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            try:
                if app is not None and self._ours(app.get_process_id()):
                    apps.append(app)
            except GLib.Error:
                continue
        return Atspi, GLib, apps

    def page_rows(self, title):
        """Returns the text of each table row on the open page titled `title`, as
        a list of cell texts, read through the AT-SPI accessibility tree."""
        Atspi, GLib, apps = self._atspi_apps()
        if Atspi is None:
            raise SmokeTestError("Can't read pages: install python3-gi and gir1.2-atspi-2.0")

        def text(node):
            # A node's own text has U+FFFC where each child's text goes.
            parts = []
            iface = node.get_text_iface()
            if iface is not None:
                parts.append(Atspi.Text.get_text(iface, 0, -1).replace("￼", " "))
            parts += [text(node.get_child_at_index(j)) for j in range(node.get_child_count())]
            return " ".join(" ".join(parts).split())

        rows = []
        stack = list(apps)
        while stack:
            node = stack.pop()
            try:
                role = node.get_role()
                if role == Atspi.Role.DOCUMENT_WEB and title not in (node.get_name() or ""):
                    continue  # another tab's page
                if role == Atspi.Role.TABLE_ROW:
                    rows.append([text(node.get_child_at_index(j)) for j in range(node.get_child_count())])
                    continue
                stack += reversed([node.get_child_at_index(j) for j in range(node.get_child_count())])
            except GLib.Error:
                continue
        return rows

    def dismiss_popup(self, buttons):
        """Clicks the first button named in `buttons`, found through the AT-SPI
        accessibility tree; otherwise lists the buttons found."""
        Atspi, GLib, apps = self._atspi_apps()
        if Atspi is None:
            return "can't look for buttons: install python3-gi and gir1.2-atspi-2.0"

        found = []
        for app in apps:
            stack = [app]
            while stack:
                node = stack.pop()
                try:
                    role = node.get_role()
                    # Never click buttons on the web page itself.
                    if role == Atspi.Role.DOCUMENT_WEB:
                        continue
                    if role == Atspi.Role.PUSH_BUTTON and node.get_name():
                        name = node.get_name()
                        if name in buttons:
                            node.get_action_iface().do_action(0)
                            return f"clicked '{name}'"
                        found.append(name)
                    for j in range(node.get_child_count()):
                        child = node.get_child_at_index(j)
                        if child is not None:
                            stack.append(child)
                except GLib.Error:
                    continue
        return "no known button; buttons found: " + ", ".join(found)

    def force_quit(self):
        # The snap's AppArmor profile rejects signals from some apps, e.g. VS Code's
        # terminal, so also cut Firefox off from the X server, which makes it exit.
        for wid, _ in self._windows():
            tool("xdotool", "windowkill", str(wid), check=False)
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
