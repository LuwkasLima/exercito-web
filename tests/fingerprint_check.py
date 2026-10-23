#!/usr/bin/env python3
"""Fingerprint check (Linux): opens browserleaks.com in the smoke test's Firefox
setup and checks what the README says that setup shows to websites:

- with fingerprinting protection, Firefox reports UTC as its time zone, English
  as its language, and a user agent and screen size that aren't this computer's;
- the browser isn't flagged as automated (navigator.webdriver is false);
- the test profiles differ only in cookies and history: websites see the same
  browser details and the same IP address in each of them.

It visits the pages with PROFILES protected profiles, plus one control profile
with the protection off, which shows what leaks without it. The pages are read
through the AT-SPI accessibility tree. Every value read is saved to a JSON
report.

Run it with: scripts/run_linux.sh tests/fingerprint_check.py
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import browser_linux
from smoke_common import SmokeTestError, wait_for
from smoke_search import STEP_DELAY, ensure_frontmost, quit_browser, step

PROFILES = int(os.environ.get("PROFILES", "2"))
# (url, page title, a value that is only filled in once the page's scripts ran)
PAGES = [
    ("https://browserleaks.com/javascript", "JavaScript Browser Information", "Navigator Object / userAgent"),
    ("https://browserleaks.com/ip", "My IP Address", "My IP Address / IP Address"),
]
# Seconds to let the pages' slower scripts (e.g. the TLS fingerprint) finish.
SETTLE = float(os.environ.get("SETTLE", "3"))
# Values that change from moment to moment, left out when comparing profiles.
CHANGING = {
    "Date/Time / System Time",
    "Date/Time / toLocaleString",
    "Date/Time / toLocaleFormat",
    "Internationalization API / DateTimeFormat",
    "IP Address Location / Local Time",
}
# Sections about the IP address, not the browser; they also load at their own
# pace. The IP address itself is checked separately.
NOT_BROWSER = ("IP Address Whois / ",)
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "browser-smoke-test"
REPORT = Path(os.environ.get("REPORT", CACHE / time.strftime("fingerprint-%Y%m%d-%H%M%S.json")))


def to_values(rows):
    """Turns label/value table rows into {"<section> / <label>": value}."""
    values, section = {}, ""
    for cells in rows:
        if len(cells) == 1:
            # Firefox reads section headings out as e.g. "Navigator Object :".
            section = cells[0].rstrip(" :")
        elif len(cells) >= 2 and cells[0]:
            values[f"{section} / {cells[0]}"] = cells[1]
    return values


def visit(browser, url, title, ready_key):
    step(f"Opening {url}")
    ensure_frontmost(browser)
    browser.shortcut("l")
    time.sleep(STEP_DELAY)
    ensure_frontmost(browser)
    browser.type_text(url)
    browser.press_return()
    wait_for(lambda: title in browser.page_title(), f"the page titled {title!r} to load")
    wait_for(
        lambda: to_values(browser.page_rows(title)).get(ready_key),
        f"{title!r} to show its results",
        timeout=30,
    )
    time.sleep(SETTLE)
    return to_values(browser.page_rows(title))


def collect(browser, number, protected):
    browser_linux.USER_PREFS["privacy.resistFingerprinting"] = protected
    browser.select_profile(number)
    step("Launching browser")
    browser.launch()
    browser.activate()
    wait_for(browser.is_frontmost, "the browser to come to the front")
    time.sleep(STEP_DELAY)
    values = {}
    try:
        for url, title, ready_key in PAGES:
            values.update(visit(browser, url, title, ready_key))
    finally:
        step("Closing the browser")
        quit_browser(browser)
    return values


def host_timezone():
    try:
        return Path("/etc/timezone").read_text().strip()
    except OSError:
        return str(Path("/etc/localtime").resolve()).partition("zoneinfo/")[2] or "unknown"


def display_size():
    result = subprocess.run(["xdotool", "getdisplaygeometry"], capture_output=True, text=True)
    return "x".join(result.stdout.split()) or "unknown"


def screen(values):
    # The separate width/height rows are in a collapsed part of the page that
    # isn't readable; this row starts with e.g. "1280×800".
    found = re.match(r"(\d+)\s*[×x]\s*(\d+)", values.get("Screen Object / Screen Resolution") or "")
    return f"{found[1]}x{found[2]}" if found else None


def utc_offset(zone):
    try:
        return ZoneInfo(zone).utcoffset(datetime.now())
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return None


def check(protected, control):
    """Returns [(status, claim, detail)]; status is PASS, FAIL or NOTE."""
    first = protected[0]
    results = []

    def add(ok, claim, detail):
        results.append(("PASS" if ok else "FAIL", claim, detail))

    tz = "Internationalization API / timeZone"
    # Firefox reports a zone that is always UTC+0 (e.g. Atlantic/Reykjavik), not "UTC".
    add(
        utc_offset(first.get(tz)) == timedelta(0) and first.get(tz) != host_timezone(),
        "Time zone is reported as UTC+0, not this computer's",
        f"protected: {first.get(tz)}, unprotected: {control.get(tz)}, this computer: {host_timezone()}",
    )

    lang = "Navigator Object / language"
    host_lang = os.environ.get("LANG", "")
    detail = f"protected: {first.get(lang)} ({first.get('Navigator Object / languages')}), unprotected: {control.get(lang)}, this computer: {host_lang}"
    if (first.get(lang) or "").startswith("en") and host_lang.startswith("en"):
        results.append(("NOTE", "Language is reported as English (can't tell if it was changed: this computer uses English too)", detail))
    else:
        add((first.get(lang) or "").startswith("en"), "Language is reported as English", detail)

    real = display_size()
    add(
        screen(first) is not None and screen(first) != real,
        "Screen size isn't this display's",
        f"protected: {screen(first)}, unprotected: {screen(control)}, this display: {real}",
    )

    ua = "Navigator Object / userAgent"
    add(
        first.get(ua) != control.get(ua),
        "User agent differs from this Firefox's own",
        f"protected: {first.get(ua)!r}, unprotected: {control.get(ua)!r}",
    )

    wd = "Navigator Object / webdriver"
    add(
        all(v.get(wd) == "false" for v in protected + [control]),
        "Not flagged as automated (navigator.webdriver is false)",
        f"protected: {[v.get(wd) for v in protected]}, unprotected: {control.get(wd)}",
    )

    keys = sorted(k for k in set().union(*protected) - CHANGING if not k.startswith(NOT_BROWSER))
    diffs = [k for k in keys if len({v.get(k) for v in protected}) > 1]
    add(
        not diffs,
        f"All {len(protected)} protected profiles show websites the same browser details",
        f"{len(keys)} values compared"
        + "".join(f"\n      differs: {k}: {[v.get(k) for v in protected]}" for k in diffs),
    )

    ip = "My IP Address / IP Address"
    ips = {v.get(ip) for v in protected + [control]}
    add(len(ips) == 1, "Every profile shows websites the same IP address", f"seen: {sorted(map(str, ips))}")

    cpus = "Navigator Object / hardwareConcurrency"
    results.append((
        "NOTE",
        "Reported CPU count",
        f"protected: {first.get(cpus)}, unprotected: {control.get(cpus)}, this computer: {os.cpu_count()}",
    ))
    return results


def main():
    if not sys.platform.startswith("linux"):
        print("❌ The fingerprint check only runs on Linux")
        return 1
    if PROFILES < 2:
        print(f"❌ PROFILES must be at least 2 to compare profiles, not {PROFILES}")
        return 1
    try:
        browser = browser_linux.Browser()
    except SmokeTestError as e:
        print(f"❌ {e}")
        return 1
    print(f"Browser: {browser.describe()}")

    protected, control = [], None
    try:
        for number in range(1, PROFILES + 1):
            print(f"\n=== Profile {number}/{PROFILES} (fingerprinting protection on) ===")
            protected.append(collect(browser, number, protected=True))
        print("\n=== Control profile (fingerprinting protection off) ===")
        control = collect(browser, 0, protected=False)
    except (SmokeTestError, subprocess.CalledProcessError) as e:
        print(f"❌ Couldn't read the pages: {e}")
        return 1
    finally:
        browser.cleanup_profiles(keep=False)

    results = check(protected, control)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(
        {"protected": protected, "control": control, "checks": results}, indent=2, ensure_ascii=False
    ))

    print("\n=== Results ===")
    icons = {"PASS": "✅", "FAIL": "❌", "NOTE": "ℹ️ "}
    for status, claim, detail in results:
        print(f"{icons[status]} {claim}\n      {detail}")
    print(f"\nEvery value read is in {REPORT}")
    return 0 if all(status != "FAIL" for status, _, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
