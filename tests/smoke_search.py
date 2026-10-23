#!/usr/bin/env python3
"""Smoke test: open the browser, go to Google, search, confirm results load,
and quit the browser. Repeats for RUNS consecutive runs.

The browser is driven through the desktop's UI automation (keyboard shortcuts
and typing), the same way a person would use it. The platform-specific parts
live in browser_macos.py (DuckDuckGo via System Events) and browser_linux.py
(Firefox via xdotool on an X11 display).
"""
import os
import subprocess
import sys
import time

from smoke_common import SmokeTestError, wait_for

START_URL = os.environ.get("START_URL", "https://www.google.com")
START_TITLE = os.environ.get("START_TITLE", "Google")
QUERY = os.environ.get("SEARCH_QUERY", "Browser smoke test")
STEP_DELAY = float(os.environ.get("STEP_DELAY", "0.8"))
RUNS = int(os.environ.get("RUNS", "10"))
QUIT_TIMEOUT = float(os.environ.get("QUIT_TIMEOUT", "15"))
# Browser profiles the runs take turns using; by default each run gets a new one.
# At the end, profiles are deleted, except those that had a failed run (Linux only).
PROFILES = int(os.environ.get("PROFILES", RUNS))
RESET_PROFILE = os.environ.get("RESET_PROFILE", "1") == "1"
# Buttons that dismiss pop-ups shown on quit. Avoid "Cancel": it can cancel the quit.
DISMISS_BUTTONS = [
    b.strip()
    for b in os.environ.get(
        "DISMISS_BUTTONS",
        "Not Now|No Thanks|Skip|Dismiss|Close|Quit|Agora não|Não, obrigado|Pular|Fechar|Sair",
    ).split("|")
    if b.strip()
]


def step(message):
    print(f"→ {message}", flush=True)


def ensure_frontmost(browser):
    # Keystrokes go to whatever app is in front; never type into the wrong window.
    if not browser.is_frontmost():
        raise SmokeTestError("Browser lost focus; aborting so keystrokes don't go elsewhere")


def quit_browser(browser):
    if not browser.is_running():
        return
    browser.request_quit()
    try:
        wait_for(lambda: not browser.is_running(), "the browser to quit", timeout=QUIT_TIMEOUT)
        return
    except SmokeTestError:
        pass

    # Still running: most likely a pop-up (e.g. a feedback prompt) is in the way.
    print(f"  pop-up detected → {browser.dismiss_popup(DISMISS_BUTTONS)}")
    try:
        wait_for(lambda: not browser.is_running(), "the browser to quit", timeout=QUIT_TIMEOUT)
        return
    except SmokeTestError:
        pass

    print("  ⚠ browser did not quit; force-quitting so the next run starts clean")
    browser.force_quit()
    wait_for(lambda: not browser.is_running(), "the browser to be force-quit")


def run(browser):
    step("Launching browser")
    browser.launch()
    browser.activate()
    wait_for(browser.is_frontmost, "the browser to come to the front")
    wait_for(browser.has_window, "a browser window")
    time.sleep(STEP_DELAY)

    step("Opening a new tab")
    ensure_frontmost(browser)
    browser.shortcut("t")
    time.sleep(STEP_DELAY)

    step("Focusing the address bar")
    ensure_frontmost(browser)
    browser.shortcut("l")
    time.sleep(STEP_DELAY)

    step(f"Navigating to {START_URL}")
    ensure_frontmost(browser)
    browser.type_text(START_URL)
    browser.press_return()
    wait_for(
        lambda: browser.page_title().strip().lower() == START_TITLE.lower(),
        f"the page titled {START_TITLE!r} to load",
    )
    # Google focuses its search box on load; give it a moment to settle.
    time.sleep(STEP_DELAY * 2)

    step(f"Typing {QUERY!r} into the Google search box")
    ensure_frontmost(browser)
    browser.type_text(QUERY)
    time.sleep(STEP_DELAY)

    step("Submitting search")
    ensure_frontmost(browser)
    browser.press_return()

    step("Waiting for results page")
    wait_for(
        lambda: QUERY.lower() in browser.page_title().lower(),
        "the results page title to contain the query",
    )
    print(f"  window title: {browser.page_title()!r}")

    time.sleep(STEP_DELAY)
    step("Closing the browser")
    quit_browser(browser)


def cleanup_profiles(browser):
    for note in browser.cleanup_profiles(keep=not RESET_PROFILE):
        print(f"  {note}")


def load_browser():
    if sys.platform == "darwin":
        import browser_macos as driver
    elif sys.platform.startswith("linux"):
        import browser_linux as driver
    else:
        raise SmokeTestError(f"Unsupported platform: {sys.platform}")
    return driver.Browser()


def main():
    try:
        browser = load_browser()
    except SmokeTestError as e:
        print(f"❌ {e}")
        return 1
    print(f"Browser: {browser.describe()}")
    print(f"Query:   {QUERY!r}")
    print(f"Runs:    {RUNS}")

    # Only the Linux driver runs the browser in profiles of its own.
    uses_profiles = hasattr(browser, "select_profile")
    if uses_profiles:
        if PROFILES < 1:
            print(f"❌ PROFILES must be at least 1, not {PROFILES}")
            return 1
        print(f"Profiles: {min(PROFILES, RUNS)}, taken in turns")

    results = []
    for i in range(1, RUNS + 1):
        profile = (i - 1) % PROFILES + 1 if uses_profiles else None
        print(f"\n=== Run {i}/{RUNS}" + (f" (profile {profile})" if profile else "") + " ===")
        started = time.monotonic()
        try:
            if uses_profiles:
                browser.select_profile(profile)
            run(browser)
            error = None
        except (SmokeTestError, subprocess.CalledProcessError) as e:
            error = str(e)
            if uses_profiles:
                browser.mark_failed()
            # Start the next run from a clean state.
            try:
                quit_browser(browser)
            except SmokeTestError as quit_error:
                print(f"  (could not quit browser: {quit_error})")
        except KeyboardInterrupt:
            print("\nInterrupted; closing the browser")
            try:
                quit_browser(browser)
            except SmokeTestError as quit_error:
                print(f"  (could not quit browser: {quit_error})")
            if uses_profiles:
                cleanup_profiles(browser)
            return 130
        elapsed = time.monotonic() - started
        results.append((i, profile, error, elapsed))
        if error:
            print(f"❌ Run {i} FAIL ({elapsed:.1f}s): {error}")
        else:
            print(f"✅ Run {i} PASS ({elapsed:.1f}s)")

    if uses_profiles:
        print()
        cleanup_profiles(browser)

    passed = sum(1 for _, _, error, _ in results if error is None)
    print(f"\n=== Summary: {passed}/{RUNS} passed ===")
    for i, profile, error, elapsed in results:
        status = "PASS" if error is None else f"FAIL - {error}"
        where = f" [profile {profile}]" if profile else ""
        print(f"  Run {i}{where}: {status} ({elapsed:.1f}s)")
    return 0 if passed == RUNS else 1


if __name__ == "__main__":
    sys.exit(main())
