# Linux scheduling

On Windows, three jobs use Task Scheduler through `schtasks`:

| Job | Windows task | Linux user service and timer on this box |
| --- | --- | --- |
| Night Shift (`night`) | `MegaZword-NightShift` | `megazword-night.service` / `megazword-night.timer`: runs `megazword night run`, every 10 minutes; currently disabled |
| Roadmap heartbeat (`heartbeat`) | `MegaZword-Heartbeat` | No heartbeat service or timer is installed. Its execution command is `megazword heartbeat run`; the local driver below is not the roadmap heartbeat. |
| Usage guard (`usage_guard.py`, CLI `guard`) | `MegaZword-Guard` | `megazword-guard.service` / `megazword-guard.timer`: runs `megazword guard run`, every 30 minutes; currently enabled |

The enabled `megazword-nightlocal.timer` activates
`megazword-nightlocal.service` every 15 minutes. That service runs
`scripts/night_local.py` against this working tree instead of the normal Night
Shift queue runner. Unit files live in `~/.config/systemd/user/`.
These are the installed configuration as inspected on 2026-10-27; inspect live
state before changing anything. The CLI's `install` and `remove` actions for
these three jobs still call Windows `schtasks`; manage Linux schedules with
systemd instead.

## Inspect

```sh
systemctl --user list-timers --all
systemctl --user cat megazword-night.timer megazword-night.service
systemctl --user cat megazword-nightlocal.timer megazword-nightlocal.service
systemctl --user cat megazword-guard.timer megazword-guard.service
journalctl --user -u megazword-nightlocal.service -u megazword-guard.service -n 50 --no-pager
```

`list-timers` shows the next and last activation and the service each timer
activates. Disabled, unloaded timers may not appear even with `--all`; `cat`
still shows their installed files.

## Pause and resume

Normal Night Shift and the roadmap heartbeat share
`~/.megazword/night/STOP`. Pause them after the current job, and skip future
runs, with:

```sh
megazword night stop
megazword night status
```

Resume with:

```sh
megazword night resume
```

The usage guard deliberately has its own `~/.megazword/guard/STOP`:

```sh
megazword guard stop
```

Resume it with:

```sh
megazword guard resume
```

The local driver checks `~/.megazword/STOP` at invocation start. Pause its
future work with:

```sh
mkdir -p ~/.megazword
touch ~/.megazword/STOP
```

Resume it with:

```sh
rm -f ~/.megazword/STOP
```

This root STOP file is also shared by other invocations of `night_local.py`.
It does not interrupt a job already running. STOP files leave timers scheduled;
the invoked runner checks the marker and skips work. Paths above assume the
default home; `MEGAZWORD_HOME`, when set for the runner, replaces
`~/.megazword`.

## Disable or remove

To disable these schedules while retaining their unit files:

```sh
systemctl --user disable --now megazword-night.timer megazword-nightlocal.timer megazword-guard.timer
```

Stopping a timer does not stop a service it already activated. To terminate
those services too (this can interrupt work):

```sh
systemctl --user stop megazword-night.service megazword-nightlocal.service megazword-guard.service
```

For permanent removal, disable and stop them as above, then delete their files
and reload the user manager:

```sh
rm -f ~/.config/systemd/user/megazword-night.timer ~/.config/systemd/user/megazword-night.service
rm -f ~/.config/systemd/user/megazword-nightlocal.timer ~/.config/systemd/user/megazword-nightlocal.service
rm -f ~/.config/systemd/user/megazword-guard.timer ~/.config/systemd/user/megazword-guard.service
systemctl --user daemon-reload
systemctl --user list-timers --all
```

## Session lifetime

A user timer runs only while the user's systemd manager is running: the login
session or linger must allow it. It is not an always-on system service. Check:

```sh
loginctl show-user "$USER" -p Linger
```

This box currently reports `Linger=no`; do not assume timers keep running after
the last session ends, or while the machine is powered off.
