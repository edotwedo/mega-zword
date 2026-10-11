# Decisions

Newest first. Don't reopen these without Phil.

## 2026-10-10
- Name is **Mega Zword**; terminal command `megazword`.
- Mega Zword replaces the whole Hive coordination system; it doesn't build on it.
- CLI first, usable from the phone via Tailscale + SSH. Dashboard window later.
- Python, private repo under edotwedo.
- Model choice is automatic and always shown; difficulty rated by a free model.
- Escalate on failure rather than picking once or handing off mid-task.
- Low-usage policy: reset-aware pacing ("use it or lose it" with a pace check).
- Phone model is an optional backend reached over Tailscale; no ADB.
- Handoff between AIs happens only through this repo (STATUS.md + small pushed commits).
