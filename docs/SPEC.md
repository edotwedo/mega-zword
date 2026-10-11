# Mega Zword spec

## What it is
One terminal tool that runs all of Phil's AIs and decides which one does each
piece of work. It mixes in free models to save paid usage, tracks usage on every
plan, and hands work between models by itself.

It **replaces** the old Hive coordination system (Q on edotwedo/workshop PR #33,
the `megazord` hive_* tools, handoff files). It does not build on it or depend
on it. The old system is only a place to copy open work from, then retire.

## Decisions
| Area | Decision |
|---|---|
| Interface | Terminal (CLI) first. A dashboard window may come later on the same core. |
| Remote use | Must work from Phil's phone: Tailscale on PC and phone, Windows OpenSSH server, Termux as the SSH client. |
| Paid AIs | Claude Code, Codex (ChatGPT plan), Grok, Gemini CLI (not installed yet). |
| Free sources | Local models (Ollama / LM Studio), OpenRouter free tier, Gemini free tier, Groq and other free APIs. |
| Choosing a model | Automatic, but always prints which model it chose and why. A flag overrides. |
| Judging difficulty | A fast free/local model rates each request easy / medium / hard. |
| Mid-task | Escalate on failure: start with the cheapest adequate model, move up if it fails or Phil rejects the answer. Mega Zword passes the context along itself. |
| Low usage | Reset-aware pacing ("use it or lose it"): compare % used with % of time elapsed in each plan's window. Under pace: spend freely. Over pace: paid plans only take hard tasks. |
| Coordination | Mega Zword assigns work, keeps shared project memory and a who-did-what log, and does handoffs itself. |
| Language / repo | Python, public repo edotwedo/mega-zword, AGPL-3.0 before 1.0. |

## Hardware
- PC: GTX 1660 (6 GB VRAM). Good for the small difficulty-rating model and 7-8B
  models at 4-bit.
- Phone: 16 GB RAM, the stronger local box, but not always online. Runs a model
  server (Ollama or llama.cpp in Termux). Mega Zword checks it's reachable over
  Tailscale before each task and falls back if not. ADB is not needed.

## Known limits
- Most subscription CLIs don't report remaining quota to other programs. Usage
  tracking combines what each CLI reports (status/usage commands, local logs)
  with Mega Zword's own counting, so some numbers are estimates.
- Paid CLIs are driven through their one-shot modes: `claude -p`,
  `codex exec`, `grok -p`, `gemini -p`.

## Build order
1. Core: run one task through any backend, rate difficulty, pick a model, log it.
2. Usage tracking and reset-aware pacing.
3. Escalate-on-failure with context passing.
4. Shared project memory and work log (the coordination layer).
5. Phone access setup (Tailscale + SSH) and the phone model backend.
6. Import open work from the old Hive, then retire it.
7. Optional dashboard window.

## Open
- Exact pacing thresholds (tune once it's running).
