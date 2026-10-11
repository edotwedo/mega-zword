# Decisions

Newest first. Don't reopen these without Phil.

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
