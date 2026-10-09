#!/usr/bin/env python3
"""Runs add_mangohud.py automatically instead of by hand after installing a
new game - add_mangohud.py itself still refuses to touch localconfig.vdf
while Steam is running (Steam holds the file open and overwrites it on
exit), so the only safe automatic trigger is "Steam just closed".

Loop: poll whether Steam is running; whenever it transitions from running to
not-running, run add_mangohud.py. Also runs once at startup if Steam is
already not running, so a game installed just before this service started
(or while it wasn't running) still gets picked up without needing Steam
opened and closed again first.

Meant to run as a long-lived systemd --user service (see
steam-mangohud-autoconfig.service) - started at login and left running, not
invoked per-run.
"""
import sys
import time

import add_mangohud

POLL_INTERVAL_S = 5


def run_once():
    print("Steam closed - checking launch options...", flush=True)
    try:
        add_mangohud.main()
    except Exception as e:  # keep the daemon alive on an unexpected vdf/IO
        # error (e.g. localconfig.vdf briefly mid-write) - it'll just try
        # again next time Steam closes, same recovery style as a transient
        # error in risemode_driver's main loop.
        print(f"add_mangohud.py failed: {e!r} (will retry next time Steam closes)", flush=True)


def main():
    print("Watching for Steam to close (poll every "
          f"{POLL_INTERVAL_S}s)...", flush=True)
    was_running = add_mangohud.steam_is_running()
    if not was_running:
        run_once()  # catch a game installed before this service last ran
    while True:
        time.sleep(POLL_INTERVAL_S)
        running = add_mangohud.steam_is_running()
        if was_running and not running:
            run_once()
        was_running = running


if __name__ == "__main__":
    sys.exit(main())
