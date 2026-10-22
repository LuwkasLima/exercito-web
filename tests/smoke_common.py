"""Shared by the smoke test and the per-platform browser drivers."""
import os
import time

TIMEOUT = float(os.environ.get("TIMEOUT", "20"))


class SmokeTestError(Exception):
    pass


def wait_for(condition, description, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.25)
    raise SmokeTestError(f"Timed out after {timeout:.0f}s waiting for {description}")
