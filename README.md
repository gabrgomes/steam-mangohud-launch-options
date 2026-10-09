# steam-mangohud-launch-options

Bulk-sets a MangoHud launch-options wrapper on every installed Steam game, so
FPS logging (used by the [risemode-smart-screen-linux-driver](../risemode-smart-screen-linux-driver)
panel's FPS/1% low/frame time sensors) works without configuring it per-game
by hand. See `add_mangohud.py`'s own docstring for exactly what the wrapper
does and why (the broken `MangoHud.conf` file, the `no_display` logging bug,
the Proton sandbox filesystem exposure).

## Automatic (recommended)

```
./install.sh
```

Installs a systemd `--user` service (`steam-mangohud-autoconfig.service`,
`mangohud_autoconfig.py`) that runs in the background and watches for Steam
to close. `add_mangohud.py` itself refuses to touch `localconfig.vdf` while
Steam is running — Steam holds the file open and overwrites any edit on its
own exit — so "Steam just closed" is the only safe moment to apply it, and
that's exactly what the service waits for. In practice: install a game,
close Steam fully (including the tray icon) as usual, and the wrapper is
applied within `POLL_INTERVAL_S` (5s) of it closing — no more remembering to
run anything by hand. A game that was already installed before the service
was first started gets picked up too, the first time Steam next closes (or
immediately, if Steam is already closed when the service starts).

```
systemctl --user status steam-mangohud-autoconfig    # check it's running
journalctl --user -u steam-mangohud-autoconfig -f     # watch it react live
```

## Manual

```
./venv/bin/python3 add_mangohud.py
```

Close Steam fully first — same restriction as above. Re-running is always
safe: it's idempotent, only rewrites `LaunchOptions` for an app whose current
value isn't already exactly right, and reports "Nothing to do" if every
installed game is already up to date.

## Setup

`STEAM_ROOT`, `VDF_PATH` and `LIBRARY_FOLDERS` at the top of `add_mangohud.py`
are hardcoded to this machine's Steam install and library locations — update
them if either changes.
