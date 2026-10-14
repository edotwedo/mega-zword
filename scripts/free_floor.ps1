# Persistent free HTTP seats: one Windows Terminal window each, own virtual desktop.
# Does not open Claude/Codex/Grok. Does not start Night Shift.
#   pwsh -File scripts\free_floor.ps1
param(
    [string[]]$Seats = @("groq", "cloudflare", "zai", "gemini-api", "mistral")
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $env:USERPROFILE "mega-zword\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "missing $py" }

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WinKeys {
  [DllImport("user32.dll")] static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr extra);
  const uint UP = 2;
  public static void Chord(byte[] keys) {
    foreach (byte k in keys) keybd_event(k, 0, 0, UIntPtr.Zero);
    for (int i = keys.Length - 1; i >= 0; i--) keybd_event(keys[i], 0, UP, UIntPtr.Zero);
  }
}
"@
# Ctrl + Left Win + D  = new virtual desktop
function New-Desktop { [WinKeys]::Chord([byte[]](0x11, 0x5B, 0x44)); Start-Sleep -Milliseconds 900 }
# Ctrl + Left Win + Left = previous desktop
function Prev-Desktop { [WinKeys]::Chord([byte[]](0x11, 0x5B, 0x25)); Start-Sleep -Milliseconds 400 }

$env:PYTHONPATH = Join-Path $root "src"
foreach ($name in $Seats) {
    New-Desktop
    $title = "MZ $name"
    $cmd = "`$env:PYTHONPATH='$($env:PYTHONPATH)'; `$env:MEGAZWORD_SEAT='$name'; & '$py' -m megazword chat -m $name"
    Start-Process wt.exe -ArgumentList @(
        "--title", $title, "--suppressApplicationTitle",
        "new-tab", "--title", $title, "-d", $root,
        "pwsh", "-NoExit", "-Command", $cmd
    )
    Start-Sleep -Milliseconds 1200
}

1..$Seats.Count | ForEach-Object { Prev-Desktop }
"opened $($Seats.Count) free-floor windows (groq / cloudflare / zai / gemini-api / mistral)."
