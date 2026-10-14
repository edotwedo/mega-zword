# Decisions

Newest first. Don't reopen these without Phil.

## 2026-10-14
- Phil (Testlog-14 chat): build a return-to-terminal briefing from each seat's current task, last completed work, blockers and next steps. Start with a catch-up button and add optional local camera presence with a cooldown. Briefings read saved cards without waking every AI.
- Phil (Cedar-14 chat): savings from free backends means preserving paid usage and credits, not reducing existing subscription payments. Report free-completed work and paid oversight separately; do not invent quota percentages.
- Phil (Cedar-14 chat): free HTTP bot jobs should eventually let him watch and intervene like other instances. Keep working on real job completion first; retain observation and intervention as the next requirement.

## 2026-10-13
- Phil (Sorrel-12 chat, ~13:00 PT): **What Phil says in one chat holds only for that chat's job.** "Don't hold anything back." Holds like "Codex waits" or "X is lead" end with that session; after it, work goes to whoever has the most usage room (`megazword plan`). **All leaders, no rulers:** the seat Phil is talking to leads its own job; a claim with no push for 2 hours is stale; if seats disagree, vote in Q (Phil overrules). Google's free API (`-m gemini-api`, AI Studio key) is the Gemini backup when agy is out.
- Phil unfroze features 2026-10-12; 2026-10-13 the bots keep working overnight while Phil sleeps (Quill-12 lead).

## 2026-10-12
- Phil: **Feature freeze is off.** The Hive floor (`megazword floor`, `docs/FLOOR.md`) is the next layer. The Beta 3.0 checklist in STATUS.md no longer blocks feature work. This replaces the "Feature freeze" entries below.
- Phil (this Grok chat): **Nimbus-12 (Grok Build on Phil's PC) is Mega Zword lead.** Tally-11 is released. Owns main, merges and assignments. Codex's 5-hour refresh is Phil's call; no Codex Mega Zword work until he says so. Feature freeze for Beta 3.0 still stands.
- Phil (13:05 PT): **Feature freeze; ship Beta 3.0 from what's on main now.** Codex's 5-hour is tapped and its week runs out until Oct 17, so slow Codex usage way down. No new features until Beta 3.0 is out: fixes, tests, docs and packaging only. Beta 3.0 includes all the Beta 2 work. Every bot on Mega Zword is told in Q and coordinates through the Beta 3.0 checklist in STATUS.md.
- Phil: labor rules follow live usage and are re-planned whenever it changes; nothing is fixed (replaces the "lanes frozen" rule). Tools: `megazword plan`, the usage hook, and `scripts/install_usage_hook.py` for his PC.
- Phil lost Kestrel's chat. Tally-11 (Claude cloud chat) takes Kestrel's seat as Mega Zword lead: owns main, merges and assignments. Other Claude sessions pick their own designation.
- Phil: the Hive room must not waste tokens re-reading everything to get the bots on the same page. Efficiency rules are part of B1 (SPEC section R, "Token budget").

## 2026-10-11
- Phil: "the calendar work should be near zero unless needed." B10 and B11 are parked; build calendar features only when Phil asks. This narrows the Calendar line below.
- Phil (Larch-11 chat): stop repeat permission requests for routine authorized project work, especially folder/file reads. Correct launcher project scopes and stale approval instructions. This does not authorize unrelated destructive actions or spending.
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
