# Browser smoke test

Checks that a browser can open, search Google and quit, several times in a
row. It controls the real browser the way a person would (keyboard shortcuts
and typing), so you can watch it run.

The test runs in two environments:

|                    | macOS                                   | Ubuntu                                                        |
|--------------------|-----------------------------------------|---------------------------------------------------------------|
| Browser tested     | DuckDuckGo app                          | Firefox (DuckDuckGo has no Linux browser)                     |
| How it's driven    | AppleScript / System Events (`osascript`) | X11 tools (`xdotool`, `wmctrl`)                             |
| Where it runs      | On your desktop                         | On a separate display: a window on your desktop, or invisible |
| Command            | `python3 tests/smoke_search.py`         | `scripts/run_linux.sh`                                        |
| Can you use the computer meanwhile? | No                     | Yes                                                           |
| Shortcuts          | ⌘T, ⌘L                                  | Ctrl+T, Ctrl+L                                                |

The script picks the right environment by itself. Follow the section for your
system, then see [What each run does](#what-each-run-does) and the shared
sections after it.

- [macOS](#macos)
- [Ubuntu](#ubuntu)
- [What each run does](#what-each-run-does) · [Output](#output) ·
  [Settings](#settings) · [Pop-ups when quitting](#pop-ups-when-quitting) ·
  [Troubleshooting](#troubleshooting)

## macOS

### macOS requirements

- **macOS.**
- **Python 3.** It only uses the standard library, so there is nothing to
  install with pip. Check with `python3 --version`. A fresh Mac gets `python3`
  when you install the Xcode Command Line Tools (`xcode-select --install`).
- **The DuckDuckGo app**, by default at `/Applications/DuckDuckGo.app`.
- **Accessibility permission** for the app that runs the script (see below).
- **Internet access** to reach google.com.

### Setup (once per Mac)

1. Open **System Settings → Privacy & Security → Accessibility**.
2. Turn on the app you will run the script from: **Terminal**, **iTerm** or
   **Visual Studio Code**. If it isn't listed, add it with the **+** button.
3. If that app was already open, quit it and open it again.

Without this permission the script stops at once with an
"Accessibility permission missing" message.

### Run on macOS

From the project folder:

```bash
python3 tests/smoke_search.py
```

By default this does 10 runs, which takes a few minutes.

**Before you start:**

- Save your work in DuckDuckGo. The test quits the browser at the end of each
  run, including any windows you already had open. If it doesn't quit cleanly,
  the test force-quits it.
- Don't touch the keyboard or mouse while the test runs. Keystrokes go to
  whichever app is in front, so if another app takes focus the run stops (and
  is marked as failed) instead of typing into the wrong window.

### macOS settings

In addition to the [shared settings](#settings):

| Variable      | Default                        | What it does |
|---------------|--------------------------------|--------------|
| `BROWSER_APP` | `/Applications/DuckDuckGo.app` | Path to the `.app` to test, e.g. a custom build |

```bash
BROWSER_APP=~/builds/MyBrowser.app python3 tests/smoke_search.py
```

### macOS troubleshooting

See also the [shared troubleshooting](#troubleshooting).

| Message | Likely cause and fix |
|---------|----------------------|
| `Accessibility permission missing` | Do the [Setup](#setup-once-per-mac) steps for the app you ran the script from, then reopen that app. |
| `Not an app bundle` | `BROWSER_APP` doesn't point to a `.app`. Check the path. |

## Ubuntu

The test drives **Firefox**, since DuckDuckGo makes no desktop browser for
Linux. It checks the same steps as on macOS, but in Firefox: it says nothing
about the DuckDuckGo app.

Ubuntu's default desktop (Wayland) doesn't let one app type into another or
read its window titles. So `scripts/run_linux.sh` starts a separate X11
display, runs the test on it and closes it at the end. The test's keystrokes
can't reach your other windows, so you can keep using your computer while it
runs.

### Ubuntu requirements

- **Ubuntu 24.04** (other recent Ubuntu and Debian versions should work).
- **Firefox.** The Ubuntu snap is fine.
- **Python 3** with `python3-gi`, both installed by default.
- **These packages**, installed once:

  ```bash
  sudo apt install xdotool wmctrl openbox xserver-xephyr xvfb
  ```

- **Internet access** to reach google.com.

No permission setup is needed.

### Run on Ubuntu

From the project folder:

```bash
scripts/run_linux.sh            # in a window on your desktop, so you can watch
HEADLESS=1 scripts/run_linux.sh # on an invisible display, e.g. for CI
```

By default this does 10 runs. Settings are passed through, e.g.
`RUNS=3 scripts/run_linux.sh`.

If you're logged in to an **"Ubuntu on Xorg"** session, you can instead run
`python3 tests/smoke_search.py` directly on your desktop, like on macOS. Then
don't touch the keyboard or mouse while it runs.

### Test profile

Firefox runs with its own profile, not your everyday one, so your tabs and
settings are left alone, and the test only touches the Firefox it started
itself. The test writes a `user.js` into the profile that turns off first-run
pages, quit prompts and crash recovery.

The profile is kept between runs, so if Google shows a cookie consent page you
only need to accept it once: start Firefox with
`firefox --no-remote --profile <profile path>` and accept it.

Firefox's output from the latest run goes to `firefox.log` next to the profile
folder.

### Ubuntu settings

In addition to the [shared settings](#settings):

| Variable             | Default | What it does |
|----------------------|---------|--------------|
| `BROWSER_CMD`        | `firefox` | Command that starts Firefox, e.g. `~/firefox-nightly/firefox` |
| `FIREFOX_PROFILE`    | `~/snap/firefox/common/smoke-test-profile` for the snap, otherwise `~/.cache/browser-smoke-test/firefox-profile` | Profile folder for the test. The snap can only use folders under `~/snap/firefox/` or non-hidden folders in your home |
| `LAUNCH_TIMEOUT`     | `60` | Seconds to wait for the Firefox window. The snap can be slow on its first start |
| `HEADLESS`           | `0` | `1` to use an invisible display (Xvfb) instead of a window (Xephyr). `run_linux.sh` only |
| `SCREEN_SIZE`        | `1280x800` | Size of the test display. `run_linux.sh` only |
| `DISPLAY_NUM`        | `99` | X display number for the test display. `run_linux.sh` only |
| `WM`                 | `openbox` | Window manager to run on the test display. `run_linux.sh` only |

### Ubuntu troubleshooting

See also the [shared troubleshooting](#troubleshooting).

| Message | Likely cause and fix |
|---------|----------------------|
| `Missing: ...` or `Missing xdotool, wmctrl` | Install the packages from [Ubuntu requirements](#ubuntu-requirements). |
| `This is a Wayland session` | You ran `tests/smoke_search.py` directly on a Wayland desktop. Use `scripts/run_linux.sh`. |
| `No window manager on display` | The test display has no window manager, so focus can't be checked. Use `scripts/run_linux.sh`, or install `openbox`. |
| `Display :99 is already in use` | Another X server uses that number, maybe one left from an interrupted run. Use `DISPLAY_NUM=98`. |
| `Firefox exited without opening a window` | The message shows the last lines of `firefox.log`. `cannot open display` means Firefox can't reach the test display. `already running` means a Firefox using the test profile is still open: close it. |
| `Timed out ... Firefox to open a window` | Firefox is slow to start. Raise `LAUNCH_TIMEOUT`. |
## What each run does

The same in both environments:

1. Opens the browser and waits for it to be in front with a window open.
2. Opens a new tab (⌘T / Ctrl+T) and focuses the address bar (⌘L / Ctrl+L).
3. Types `START_URL` and presses Return, then waits for the window title to be
   `START_TITLE`. On Ubuntu, Firefox's " — Mozilla Firefox" title suffix is
   ignored.
4. Types `SEARCH_QUERY` into Google's search box (it has focus when the page
   loads) and presses Return.
5. Waits for the window title to contain the search text. This means the
   results page loaded. **This is the pass check.**
6. Quits the browser. See [Pop-ups when quitting](#pop-ups-when-quitting).

A run **fails** if any wait takes longer than `TIMEOUT` seconds, if the browser
loses focus, or if a UI automation command fails. After a failed run, the test
still quits the browser so the next run starts clean.

## Output

The test prints each step as it goes, then a summary:

```
=== Run 1/10 ===
→ Launching browser
→ Opening a new tab
...
  window title: 'Browser smoke test - Google Search'
→ Closing the browser
✅ Run 1 PASS (12.4s)
...
=== Summary: 10/10 passed ===
  Run 1: PASS (12.4s)
  ...
```

The exit code is `0` if every run passed and `1` if any run failed, so you can
use it in other scripts or CI.

## Settings

All settings are environment variables. Set them before the command:

```bash
RUNS=3 SEARCH_QUERY="hello world" python3 tests/smoke_search.py   # macOS
RUNS=3 SEARCH_QUERY="hello world" scripts/run_linux.sh            # Ubuntu
```

These work in both environments. Each environment has a few more: see
[macOS settings](#macos-settings) and [Ubuntu settings](#ubuntu-settings).

| Variable          | Default                        | What it does |
|-------------------|--------------------------------|--------------|
| `RUNS`            | `10`                           | Number of runs in a row |
| `SEARCH_QUERY`    | `Browser smoke test`           | Text to search for |
| `START_URL`       | `https://www.google.com`       | Page to open before searching |
| `START_TITLE`     | `Google`                       | Window title that shows `START_URL` has loaded (not case-sensitive) |
| `TIMEOUT`         | `20`                           | Seconds to wait at each wait step before failing |
| `STEP_DELAY`      | `0.8`                          | Seconds to pause between steps. Raise it on a slow computer |
| `QUIT_TIMEOUT`    | `15`                           | Seconds to wait for the browser to quit before looking for a pop-up |
| `DISMISS_BUTTONS` | `Not Now\|No Thanks\|Skip\|Dismiss\|Close\|Quit\|Agora não\|Não, obrigado\|Pular\|Fechar\|Sair` | Button names to click on a pop-up shown when quitting, separated by `\|` |

## Pop-ups when quitting

The browser sometimes shows a pop-up when it quits (DuckDuckGo, for example,
can show a feedback prompt), which stops it from closing. If the browser is
still open after `QUIT_TIMEOUT` seconds, the test:

1. Looks for a button named in `DISMISS_BUTTONS` and clicks it.
2. If no button matches, prints the names of the buttons it found.
3. If the browser still hasn't quit, force-quits it.

How it finds the buttons differs:

- **macOS:** through System Events, in all of the browser's windows.
- **Ubuntu:** through the Linux accessibility interface (AT-SPI). Buttons on
  web pages are skipped. On Ubuntu the test asks Firefox to quit by closing
  its windows.

If you see a force-quit warning, copy the right button name from the output
into `DISMISS_BUTTONS`. The default list covers English and Portuguese. Add
the button names in your language if your system uses another one. Don't add
"Cancel", because it can cancel the quit.

## Troubleshooting

These apply in both environments. See also
[macOS troubleshooting](#macos-troubleshooting) and
[Ubuntu troubleshooting](#ubuntu-troubleshooting).

| Message | Likely cause and fix |
|---------|----------------------|
| `Browser lost focus` | Another window came to the front: a notification you clicked, or keyboard/mouse use. Run again without touching anything. On Ubuntu with `run_linux.sh`, don't click inside the test window. |
| `Timed out ... the page titled 'Google' to load` | Google showed something other than its home page. In the EU this is often the cookie consent page: accept it once by hand in the browser (on Ubuntu, in the [test profile](#test-profile)). Also check your internet connection. |
| `Timed out ... results page title to contain the query` | Google may be showing a CAPTCHA ("unusual traffic") after many automated searches. Wait a while or use fewer `RUNS`. On a slow computer, raise `TIMEOUT` or `STEP_DELAY`. |
| `browser did not quit; force-quitting` | A pop-up blocked the quit. See [Pop-ups when quitting](#pop-ups-when-quitting). |
