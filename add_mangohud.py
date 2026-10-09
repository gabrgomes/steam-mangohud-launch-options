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

Everything machine/account-specific (the Steam install location, your
numeric Steam3 account ID, your library folders) is auto-detected rather
than hardcoded, so nothing personally identifying needs to live in this
file - see find_steam_root()/find_vdf_path()/find_library_folders().

Run this after installing new games. Steam must be fully closed first -
it holds localconfig.vdf open and will overwrite our edit otherwise.
(Or just leave steam-mangohud-autoconfig.service running - see README.md -
and never run this by hand at all.)
"""
import glob
import os
import re
import subprocess
import sys

import vdf

MANGOHUD_LOG_DIR = os.path.expanduser("~/.local/share/mangohud_logs")
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


def find_steam_root():
    """The active Steam client install directory. `~/.steam/root` is a
    symlink Steam itself maintains to point at whichever install is
    actually in use (native "debian-installation", plain "steam", ...), so
    preferring it means never having to hardcode which one this machine
    has. Falls back to the common fixed locations (including Flatpak's) for
    a setup where that symlink is missing."""
    root_link = os.path.expanduser("~/.steam/root")
    if os.path.islink(root_link):
        resolved = os.path.realpath(root_link)
        if os.path.isdir(resolved):
            return resolved
    for candidate in (
        "~/.steam/steam",
        "~/.local/share/Steam",
        "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
    ):
        path = os.path.expanduser(candidate)
        if os.path.isdir(os.path.join(path, "userdata")):
            return path
    return None


def find_vdf_path(steam_root):
    """This account's localconfig.vdf, found rather than hardcoding the
    numeric Steam3 ID in userdata/<id>/config/ - that ID isn't secret, but
    there's no reason to bake one specific person's account ID into a
    script other people might reuse. If userdata holds more than one
    account (a shared machine), picks whichever was written to most
    recently - the one actually in use."""
    candidates = glob.glob(os.path.join(steam_root, "userdata", "*", "config", "localconfig.vdf"))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def find_library_folders(steam_root):
    """Every Steam library's steamapps folder (the default one under
    steam_root, plus any additional drives), read from Steam's own
    libraryfolders.vdf instead of hardcoding drive paths that'll go stale
    the moment a library is added, removed, or moved."""
    vdf_path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    try:
        data = vdf.load(open(vdf_path))
    except (OSError, SyntaxError):
        return [os.path.join(steam_root, "steamapps")]
    folders = [
        os.path.join(entry["path"], "steamapps")
        for entry in data.get("libraryfolders", {}).values()
        if isinstance(entry, dict) and entry.get("path")
    ]
    return folders or [os.path.join(steam_root, "steamapps")]


def installed_appids(library_folders):
    ids = set()
    for folder in library_folders:
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

    steam_root = find_steam_root()
    if not steam_root:
        print("Couldn't find a Steam installation (no ~/.steam/root and none of the "
              "usual locations have a userdata folder).")
        return 1

    vdf_path = find_vdf_path(steam_root)
    if not vdf_path:
        print(f"No userdata/<id>/config/localconfig.vdf under {steam_root} - "
              "log into Steam at least once first.")
        return 1

    library_folders = find_library_folders(steam_root)
    appids = installed_appids(library_folders)
    if not appids:
        print(f"No installed games found in {library_folders}.")
        return 1

    data = vdf.load(open(vdf_path))
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

    vdf.dump(data, open(vdf_path, "w"), pretty=True)
    print(f"Updated {len(changed)} app(s):")
    for appid, opts in changed:
        print(f"  {appid}: {opts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
