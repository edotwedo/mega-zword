# Linux

Mega Zword's command line, dashboard, and hive room run on Linux. The Windows Terminal workspace does not: no `wt.exe` launch, no Hive virtual desktop, no console relay, and no face enrollment.

## Install

Python 3.11 or newer.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Put `.venv/bin` on `PATH` and open a new shell. Check the install with `megazword doctor`.

This tree has no `scripts/install.sh`. The Windows installer is `scripts/install.ps1`.

## App window

At a terminal, plain `megazword` opens the dashboard app window and leaves it running after the shell exits. `megazword start` is the text screen. `MEGAZWORD_NO_APP=1` keeps scripts and pipes on the text screen.

```bash
megazword dashboard --app
```

`pip install pywebview` uses a native window (`megazword[app]`). Without it, the dashboard looks for Edge or a Chromium-family browser on `PATH` (`msedge`, `microsoft-edge`, `google-chrome`, `chrome`, `chromium`, `chromium-browser`) and opens `--app=` mode. If none is found, it opens a normal browser tab.

`megazword app install` and `megazword app remove` write a Windows Start menu shortcut. On Linux they stop, and they do not write `~/.local/share/applications/megazword.desktop`.

## Keys

Linux does not use Windows Credential Manager. `credential_store.available()` is false here, and `load_user_env` copies nothing. Set keys in the environment before you launch. `megazword keys` prints each name as `env`, `vault`, or `missing`. It does not print secret values.

The hive room needs `HIVE_ROOM_URL` plus `HIVE_ROOM_TOKEN`, or a per-seat `HIVE_ROOM_KEY_<SEAT>` (hyphens in the seat name become underscores). Do not commit secrets.

## Scheduled tasks

`megazword night install`, `megazword heartbeat install`, and `megazword guard install` register Windows Task Scheduler jobs through `schtasks`. This tree does not install systemd user timers. On Linux, run the jobs yourself:

```bash
megazword night run
megazword heartbeat run
megazword guard run
```

## Windows-only UI

Importing the CLI or constructing the dashboard does not import `megazword.workspace`, `megazword.workspace_terminal`, winpty, OpenCV, or NumPy. `OwnerCamera`, `enroll`, and `watch` no-op. These calls raise `OSError` off Windows:

- `user_protect` (DPAPI)
- `ConsoleInput` (console events)
- `desktop` (`VirtualDesktopAccessor.dll`)
- `run_tab` (the winpty relay)

`restore` still builds a `wt.exe` command. Tests drive that path with mocks. Do not point a Linux login item at `python -m megazword.workspace boot`.

## Text

There is no gettext catalog. The strings are English.

## Checks

Run the suite from the Linux virtualenv before you push:

```bash
.venv/bin/python -m pytest
```

`megazword gate --install` points Git at `.githooks/pre-push`. If that hook prints `NOTHING WAS VERIFIED`, it did not run the suite. `MZ_SKIP_GATE=1` skips the hook and the skip is printed. `tests/test_terminal_input.py` skips its winpty tests off Windows. On Windows that file can flake when consoles contend; run it alone before blaming another change.
