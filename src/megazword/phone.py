"""Discover a connected Tailscale address without changing network settings."""

import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess


def tailscale_path() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    # A newly installed Windows app may not be in this terminal's PATH yet.
    candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tailscale/tailscale.exe"
    return str(candidate) if candidate.is_file() else None


def address() -> str:
    executable = tailscale_path()
    if not executable:
        raise ValueError("Tailscale is not installed. Install it from "
                         "https://tailscale.com/download on the PC and phone, sign in "
                         "to the same account, then run this command again.")
    try:
        result = subprocess.run(
            [executable, "status", "--json"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Cannot reach Tailscale. Open the Tailscale app on the PC, "
                         "connect it, then try again.") from None
    if result.returncode:
        raise ValueError("Tailscale is not ready. Open its PC app and sign in/connect, "
                         "then try again.")
    try:
        state = json.loads(result.stdout)
    except ValueError:
        raise ValueError("Tailscale returned unreadable status. Open its PC app and "
                         "check the connection.") from None
    if not isinstance(state, dict) or state.get("BackendState") != "Running":
        raise ValueError("Tailscale is disconnected or needs sign-in. Open its PC app "
                         "and connect; connect the phone to the same account.")
    ips = state.get("TailscaleIPs", [])
    if isinstance(ips, list):
        for raw in ips:
            if not isinstance(raw, str):
                continue
            try:
                ip = ipaddress.ip_address(raw)
            except ValueError:
                continue
            if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
                return str(ip)
    raise ValueError("Tailscale has no usable IPv4 address yet. Reconnect its PC app "
                     "and try again.")
