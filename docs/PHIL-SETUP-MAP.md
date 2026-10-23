# Phil's setup map

This is the quick reference for the tools Phil and Mega Zword have actually set up. Provider availability and quota details live in [FREE-MODEL-ROSTER.md](FREE-MODEL-ROSTER.md); don't duplicate provider keys or secret values here.

## Proton Pass

- The Proton Pass CLI executable is at `C:\Users\mrmar\Desktop\proton-tools\pass-cli.exe` and PowerShell resolves `pass-cli.exe` from that location.
- Its available workflows include `login`, `vault`, `item`, `run`, and `inject`. Use `pass-cli.exe help <command>` to see exact options before changing vault data.
- The previously noted import file `C:\Users\mrmar\Desktop\proton-pass-import.csv` is not present now. It was a header-only CSV template, not a place where API keys were saved.
- The CLI's signed-in state and the presence of the provider keys in a Proton Pass vault have not been verified in this session. Do not describe keys as safely saved until a vault item is confirmed.
- Keep API keys in Proton Pass or Mega Zword's ignored local `.env`; never put them in this document, a CSV, Git, or a chat. Keys pasted into chat should be replaced before being trusted again.

## Phone and Mega Zword CLI

Phil's phone is a **Nothing Phone (3)** (codename `Metroid`, model `A024`, Android). The phone terminal app is **Termux**. The intended PC workflow is to connect from Termux to the Windows PC over Tailscale and SSH, then run Mega Zword on the PC:

```sh
pkg install openssh
ssh mrmar@<PC-Tailscale-IP>
megazword usage
megazword plan
megazword doctor
megazword run "your prompt"
```

This requires Tailscale on both devices and Windows OpenSSH Server on the PC. The project setup notes still treat that end-to-end phone-to-PC connection as a setup/check step; don't assume SSH is working until Phil has tested it. The phone's separate local Ollama model is not the same thing as running the Mega Zword CLI on the PC.

Useful PC commands:

```powershell
megazword usage
megazword plan
megazword backends
megazword run "your prompt"
```

## Phone clipboard to PC

Phone Link's cross-device clipboard does not deliver phone -> PC here (its read comes back empty), so this runs over adb instead:

- adb is at `C:\Users\mrmar\platform-tools\adb.exe`. Wireless debugging on the phone turns itself off and must be re-enabled before a session (`adb connect <ip:port>`).
- The phone has **Termux:API** (`com.termux.api`, side-loaded from F-Droid 0.53.0) and the `termux-api` package (`0.60.0`) inside Termux; together they provide `termux-clipboard-get`.
- `C:\Users\mrmar\Scripts\phone-clip.ps1` copies the phone clipboard to the Windows clipboard: it wakes the phone, runs `termux-clipboard-get > /sdcard/clip.txt` in Termux, then pipes the file into `Set-Clipboard`. Run `powershell -File C:\Users\mrmar\Scripts\phone-clip.ps1`.
- Caveat: each run flashes Termux to the foreground on the phone for ~2 seconds. Android clears the clipboard after a while, so copy the source text close to running it.

## Office app

The office clone Phil meant has not been identified from the project notes or Start-menu app list, and it is not installed. A top-level name check of Desktop and Downloads found no obvious office-named installer. Record its name and official download page here once identified; don't mark an office suite as installed before verifying it.

## Next checks

1. Confirm the correct office-suite name/download page, then install it if Phil still wants it.
2. Test Termux -> Tailscale -> SSH -> `megazword usage` once, and mark the phone workflow verified only after the command works.
3. Confirm Proton Pass CLI login and vault item presence without copying any secret into this repo. Replace credentials previously pasted into chat before relying on them.
