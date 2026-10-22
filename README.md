# Browser smoke test

Checks that the DuckDuckGo browser can open, search Google and quit, several
times in a row. It controls the real app on your screen the way a person would
(keyboard shortcuts and typing), so you can watch it run.

## Requirements

- **macOS.** The script uses AppleScript (`osascript`) and the `open` command,
  so it does not run on Linux or Windows.
- **Python 3.** It only uses the standard library, so there is nothing to
  install with pip. Check with `python3 --version`. A fresh Mac gets `python3`
  when you install the Xcode Command Line Tools (`xcode-select --install`).
- **The browser under test**, by default at `/Applications/DuckDuckGo.app`.
- **Accessibility permission** for the app that runs the script (see Setup).
- **Internet access** to reach google.com.

## Setup (once per Mac)

1. Open **System Settings → Privacy & Security → Accessibility**.
2. Turn on the app you will run the script from: **Terminal**, **iTerm** or
   **Visual Studio Code**. If it isn't listed, add it with the **+** button.
3. If that app was already open, quit it and open it again.

Without this permission the script stops at once with an
"Accessibility permission missing" message.

## Run

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

## What each run does

1. Opens the browser and waits for it to be in front with a window open.
2. Opens a new tab (⌘T) and focuses the address bar (⌘L).
3. Types `START_URL` and presses Return, then waits for the window title to be
   `START_TITLE`.
4. Types `SEARCH_QUERY` into Google's search box (it has focus when the page
   loads) and presses Return.
5. Waits for the window title to contain the search text. This means the
   results page loaded. **This is the pass check.**
6. Quits the browser. See [Pop-ups when quitting](#pop-ups-when-quitting).

A run **fails** if any wait takes longer than `TIMEOUT` seconds, if the browser
loses focus, or if an AppleScript command fails. After a failed run, the test
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

## Configuration

All settings are environment variables. Set them before the command:

```bash
RUNS=3 SEARCH_QUERY="hello world" python3 tests/smoke_search.py
```

| Variable          | Default                        | What it does |
|-------------------|--------------------------------|--------------|
| `BROWSER_APP`     | `/Applications/DuckDuckGo.app` | Path to the `.app` to test, e.g. a custom build |
| `RUNS`            | `10`                           | Number of runs in a row |
| `SEARCH_QUERY`    | `Browser smoke test`           | Text to search for |
| `START_URL`       | `https://www.google.com`       | Page to open before searching |
| `START_TITLE`     | `Google`                       | Window title that shows `START_URL` has loaded (not case-sensitive) |
| `TIMEOUT`         | `20`                           | Seconds to wait at each wait step before failing |
| `STEP_DELAY`      | `0.8`                          | Seconds to pause between steps. Raise it on a slow Mac |
| `QUIT_TIMEOUT`    | `15`                           | Seconds to wait for the browser to quit before looking for a pop-up |
| `DISMISS_BUTTONS` | `Not Now\|No Thanks\|Skip\|Dismiss\|Close\|Quit\|Agora não\|Não, obrigado\|Pular\|Fechar\|Sair` | Button names to click on a pop-up shown when quitting, separated by `\|` |

Example with a custom build:

```bash
BROWSER_APP=~/builds/MyBrowser.app python3 tests/smoke_search.py
```

### Pop-ups when quitting

DuckDuckGo sometimes shows a pop-up (such as a feedback prompt) when it quits,
which stops it from closing. If the browser is still open after `QUIT_TIMEOUT`
seconds, the test:

1. Looks for a button named in `DISMISS_BUTTONS` and clicks it.
2. If no button matches, prints the names of the buttons it found.
3. If the browser still hasn't quit, force-quits it.

If you see a force-quit warning, copy the right button name from the output
into `DISMISS_BUTTONS`. The default list covers English and Portuguese. Add
the button names in your language if your Mac uses another one. Don't add
"Cancel", because it can cancel the quit.

## Troubleshooting

| Message | Likely cause and fix |
|---------|----------------------|
| `Accessibility permission missing` | Do the [Setup](#setup-once-per-mac) steps for the app you ran the script from, then reopen that app. |
| `Not an app bundle` | `BROWSER_APP` doesn't point to a `.app`. Check the path. |
| `Browser lost focus` | Another app came to the front (a notification you clicked, or keyboard/mouse use). Run again without touching anything. |
| `Timed out ... the page titled 'Google' to load` | Google showed something other than its home page. In the EU this is often the cookie consent page: accept it once by hand in the browser. Also check your internet connection. |
| `Timed out ... results page title to contain the query` | Google may be showing a CAPTCHA ("unusual traffic") after many automated searches. Wait a while or use fewer `RUNS`. On a slow Mac, raise `TIMEOUT` or `STEP_DELAY`. |
| `browser did not quit; force-quitting` | A pop-up blocked the quit. See [Pop-ups when quitting](#pop-ups-when-quitting). |
