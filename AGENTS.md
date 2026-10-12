# Mega Zword: rules for every AI working here

This file is for Claude Code, Codex and Grok alike. Phil (the owner) may switch
between them at any time, including mid-task when one runs out of usage. The
repo is the only handoff. Nothing lives only in a chat.

## Read first, in this order
1. `docs/STATUS.md`: what's done, what's in progress, the exact next step.
2. `docs/SPEC.md`: what we're building and the decisions behind it.
3. `docs/DECISIONS.md`: dated log of choices; don't reopen these without Phil.

## Working rules
- **Usage first, every time (Phil).** Before you start, claim or hand out any work: run `megazword usage`
  (on Phil's PC) or read the usage board in Q
  (https://github.com/edotwedo/workshop/pull/33#issuecomment-6115098816; over 30 minutes old means the
  PC is asleep, so say so). Then write a labor plan: which AI does which part, by spare usage and fit,
  with the reading quoted. `megazword plan` ranks them. Plans and lanes follow the live reading: re-plan
  when it changes; nothing in STATUS is fixed. Do this before any work, not partway through.
- **One AI at a time.** Before editing, put your tool name and the time in the
  "Active" line of `docs/STATUS.md`, then commit and push it. If that line names
  another AI and is less than 2 hours old, stop and ask Phil before continuing.
- **Small steps, pushed often.** Commit and push after each working step. A
  step that isn't pushed doesn't exist for the next AI.
- **Keep STATUS.md true.** Update it with every push: what changed, what's
  next, anything half-done or broken. Write the next step so precisely that a
  different AI with no chat history can start on it immediately.
- **Running low on usage?** Stop early enough to update STATUS.md, commit and
  push. Clear the "Active" line when you stop.
- **Decisions** made with Phil go in `docs/DECISIONS.md` with the date.
- **Never commit secrets** (API keys, tokens, logins). Use `.env`, which is
  git-ignored. Document needed variables in `.env.example`.
- Phil's instructions control scope. Ask him when something is truly his call.
- Write plainly for Phil: short sentences, no jargon without a quick explanation.

## Project basics
- Python 3.11, Windows 11 is the main machine. Command: `megazword`.
- Code goes in `src/megazword/`, tests in `tests/`.
