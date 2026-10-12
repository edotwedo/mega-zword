# Decisions

Newest first. Don't reopen these without Phil.

## 2026-10-12
- Phil lost Kestrel's chat. Tally-11 (Claude cloud chat) takes Kestrel's seat as Mega Zword lead: owns main, merges and assignments. Other Claude sessions pick their own designation.
- Phil: the Hive room must not waste tokens re-reading everything to get the bots on the same page. Efficiency rules are part of B1 (SPEC section R, "Token budget").

## 2026-10-11
- Phil: "the calendar work should be near zero unless needed." B10 and B11 are parked; build calendar features only when Phil asks. This narrows the Calendar line below.
- Phil, revised: Mistral (and other trains-on-data free AIs) gets the lightest rules, not strict ones. It's routed normally and takes the small repetitive jobs first; edit mode is allowed; the sandbox is optional for big batches; one light secret guard stays. This replaces the stricter B15 line below. His terms: fine as long as it's legal (no piracy) and they don't resell his work.
- Phil OKs free AIs that train on what we send (first: Mistral Experiment tier). His words: he doesn't mind training as long as they don't package and sell it, and he has no valuable data yet. Rules (STATUS B15): never auto-routed; a prompt guard blocks secrets, logins and private folders; any file-changing work runs only in a sandbox; a trusted AI reviews the diff before it's applied.
- Phil: Mega Zword is proprietary and private, all rights reserved. He shares it with whom he chooses. This replaces the 2026-10-10 AGPL decision. At the switch the repo had no forks, stars, outside contributors or outside clones. Don't add an open-source license or make the repo public without Phil.
- Workshop BUDGET.md limits are retired (Phil). Automatic runs are allowed; every AI may use its own usage. Two more AIs now have their own usage (Gemini via agy is one).
- Sentinel: Mega Zword logs disconnects/reconnects, logins and login attempts, and reboots, and alerts Phil when production is hit (SPEC section S). Calendar: Google Calendar, Dial-In's lane, built into Mega Zword (SPEC section C).
- Phil wants Beta 2 to add: a bot group chat inside the app (separate from Q, lightweight, bots prompt each other, Phil leads when he speaks, prime directive = work the primary project and use up spare usage, learn from each session, summary to Q), bot-per-tab chats, and a Windows 11 look with Linux/1337 flair. Work split across bots like the overnight run. 
- Phil called Beta 1: everything on the remote merged to main and tagged `v0.1.0-beta.1` (package version 0.1.0b1). Work still on someone's PC goes into the next beta.
- Kestrel (Claude Code session) is in charge of Mega Zword: owns main, merges and assignments. Other workers use their own branches.

## 2026-10-10
- When Mega Zword launches Grok it sets the model and reasoning effort from the task rating: easy -> grok-4.6 low, medium (coding) -> grok-4.6 medium, hard (design) -> grok-4.7 high. Override in ~/.megazword/config.toml under [grok.<level>]. A forced `-m grok` uses medium. A retry never uses low.
- Routing: cheapest adequate AI first. Spend a stronger plan's leftover usage only when its reset is close (1h for 5-hour windows, 24h for weekly, >=20% unused).
- Claude's unexplained "iguana_necktie" usage window is likely Phil's Claude Cloud credit; unknown windows are shown but never block routing.
- Repo is public. License: AGPL-3.0 for all versions before 1.0. Phil may choose different terms for 1.0+; to keep that option, outside contributions need a contributor agreement before merging (not set up yet).
- Name is **Mega Zword**; terminal command `megazword`.
- Mega Zword replaces the whole Hive coordination system; it doesn't build on it.
- CLI first, usable from the phone via Tailscale + SSH. Dashboard window later.
- Python, repo under edotwedo (made public the same day, see above).
- Model choice is automatic and always shown; difficulty rated by a free model.
- Escalate on failure rather than picking once or handing off mid-task.
- Low-usage policy: reset-aware pacing ("use it or lose it" with a pace check).
- Phone model is an optional backend reached over Tailscale; no ADB.
- Handoff between AIs happens only through this repo (STATUS.md + small pushed commits).
