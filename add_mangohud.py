#!/usr/bin/env python3
"""
Bulk-adds a MangoHud launch wrapper to the Launch Options of every currently
installed Steam game, so MangoHud logging (used by the
risemode-smart-screen-linux-driver panel's FPS reading) works without setting
it per-game by hand.

We tried making this fully global via ~/.config/environment.d instead of
per-game Launch Options, but systemd --user's environment on this machine
kept silently reverting to stale values (root cause not fully pinned down -
not just a login-timing issue, it happened without any new login too), so
per-game Launch Options via this script is the reliable mechanism.

The wrapper also carries two things that don't work as plain `mangohud`:
  - MANGOHUD_CONFIG: overrides the (broken, unread) file-based MangoHud.conf
    for this manually-built v0.8.4 install, and drops `no_display` in favor
    of `fps_only` + near-zero alpha - MangoHud has a known upstream bug where
    no_display disables logging entirely, not just the overlay
    (https://github.com/flightlessmango/MangoHud/issues/1782).
  - PRESSURE_VESSEL_FILESYSTEMS_RO/RW: exposes the manually-installed
    /usr/lib/mangohud path and the log output dir into Proton's sandbox,
    which doesn't see non-standard host lib paths otherwise.

Run this after installing new games. Steam must be fully closed first -
it holds localconfig.vdf open and will overwrite our edit otherwise.
"""
import glob
import re
import subprocess
import sys

import vdf

STEAM_ROOT = "/home/gabriel/.steam/debian-installation"
VDF_PATH = f"{STEAM_ROOT}/userdata/118970669/config/localconfig.vdf"
LIBRARY_FOLDERS = [
    f"{STEAM_ROOT}/steamapps",
    "/media/data/SteamLibrary/steamapps",
]

MANGOHUD_LOG_DIR = "/home/gabriel/.local/share/mangohud_logs"
MANGOHUD_CONFIG = (
    f"output_folder={MANGOHUD_LOG_DIR},autostart_log=1,log_duration=999999,"
    "log_interval=200,fps_only,font_size=10,hud_no_margin,background_alpha=0,"
    "alpha=0.15,position=top-left,text_color=000000,fps_color_change=0,"
    "engine_color=000000,offset_x=-3000,offset_y=-3000"
)
ENV_PREFIX = (
    f"MANGOHUD_CONFIG={MANGOHUD_CONFIG} "
    "PRESSURE_VESSEL_FILESYSTEMS_RO=/usr/lib/mangohud "
    f"PRESSURE_VESSEL_FILESYSTEMS_RW={MANGOHUD_LOG_DIR}"
)
WRAPPER = f"{ENV_PREFIX} mangohud"


def steam_is_running():
    # -x matches the exact process name (comm), not the full command line -
    # pgrep -f self-matches whenever its own search string appears in the
    # invoking shell's command text (e.g. this script's own path, or the
    # search string itself when run through certain shell wrappers).
    out = subprocess.run(["pgrep", "-x", "steam"], capture_output=True, text=True)
    return bool(out.stdout.strip())


def installed_appids():
    ids = set()
    for folder in LIBRARY_FOLDERS:
        for path in glob.glob(f"{folder}/appmanifest_*.acf"):
            m = re.search(r"appmanifest_(\d+)\.acf", path)
            if m:
                ids.add(m.group(1))
    return ids


def main():
    if steam_is_running():
        print("Steam is still running - close it fully first (it will "
              "overwrite this file otherwise). Aborting.")
        return 1

    appids = installed_appids()
    if not appids:
        print("No installed games found - check LIBRARY_FOLDERS in this script.")
        return 1

    data = vdf.load(open(VDF_PATH))
    apps = data["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"]

    changed = []
    for appid in appids:
        if appid not in apps or not isinstance(apps[appid], dict):
            apps[appid] = vdf.VDFDict()
        cfg = apps[appid]
        current = cfg.get("LaunchOptions", "")
        # Strip any prior wrapper (old MANGOHUD_CONFIG= value or a plain
        # `mangohud`) so re-running this script after tweaking MANGOHUD_CONFIG
        # above always converges on the latest wrapper instead of skipping.
        rest = re.sub(
            r"(MANGOHUD_CONFIG=\S+ PRESSURE_VESSEL_FILESYSTEMS_RO=\S+ "
            r"PRESSURE_VESSEL_FILESYSTEMS_RW=\S+ )?mangohud ?",
            "",
            current,
        ).strip()
        if not rest:
            new_options = f"{WRAPPER} %command%"
        elif "%command%" in rest:
            new_options = f"{WRAPPER} {rest}"
        else:
            new_options = f"{WRAPPER} %command% {rest}"
        if new_options == current:
            continue  # already exactly up to date
        cfg["LaunchOptions"] = new_options
        changed.append((appid, cfg["LaunchOptions"]))

    if not changed:
        print("Nothing to do - all installed games already have mangohud set.")
        return 0

    vdf.dump(data, open(VDF_PATH, "w"), pretty=True)
    print(f"Updated {len(changed)} app(s):")
    for appid, opts in changed:
        print(f"  {appid}: {opts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
