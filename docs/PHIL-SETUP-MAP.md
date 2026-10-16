# Phil's setup map

This is the quick reference for the tools Phil and Mega Zword have actually set up. Provider availability and quota details live in [FREE-MODEL-ROSTER.md](FREE-MODEL-ROSTER.md); don't duplicate provider keys or secret values here.

## Proton Pass

- The Proton Pass CLI executable is at `C:\Users\mrmar\Desktop\proton-tools\pass-cli.exe` and PowerShell resolves `pass-cli.exe` from that location.
- Its available workflows include `login`, `vault`, `item`, `run`, and `inject`. Use `pass-cli.exe help <command>` to see exact options before changing vault data.
- The previously noted import file `C:\Users\mrmar\Desktop\proton-pass-import.csv` is not present now. It was a header-only CSV template, not a place where API keys were saved.
- The CLI's signed-in state and the presence of the provider keys in a Proton Pass vault have not been verified in this session. Do not describe keys as safely saved until a vault item is confirmed.
- Keep API keys in Proton Pass or Mega Zword's ignored local `.env`; never put them in this document, a CSV, Git, or a chat. Keys pasted into chat should be replaced before being trusted again.

## Phone and Mega Zword CLI

The phone terminal app is **Termux**. The intended PC workflow is to connect from Termux to the Windows PC over Tailscale and SSH, then run Mega Zword on the PC:

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

## Office app

The office clone Phil meant has not been identified from the project notes or Start-menu app list, and it is not installed. A top-level name check of Desktop and Downloads found no obvious office-named installer. Record its name and official download page here once identified; don't mark an office suite as installed before verifying it.

## Next checks

1. Confirm the correct office-suite name/download page, then install it if Phil still wants it.
2. Test Termux -> Tailscale -> SSH -> `megazword usage` once, and mark the phone workflow verified only after the command works.
3. Confirm Proton Pass CLI login and vault item presence without copying any secret into this repo. Replace credentials previously pasted into chat before relying on them.
