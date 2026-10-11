# Status

**Active:** none
**Last updated:** 2026-10-10 23:06 by Grok (branch grok/escalate). Grok stopped here.

## Done
- Repo created with handoff rules (AGENTS.md), spec, status and decision log.
- Repo made public; AGPL-3.0 license and README added.
- Step 1 part 1: package + `megazword run -m <ai>` + `megazword backends`. Backends for claude, codex, grok all answer a real prompt (tested 2026-10-10). 6 tests pass with fake backends.
- Step 1 part 2: `megazword run "..."` with no `-m` rates difficulty with local qwen2.5:1.5b via Ollama (keyword rule can raise to hard; falls back to the rule if Ollama is down), picks the first installed AI from the route table, prints why, and logs each run to `~/.megazword/log.jsonl`. Overrides in `~/.megazword/config.toml`. 13 tests pass.
- Step 2 part 1: `megazword usage` shows live plan meters. Claude: Anthropic usage endpoint with the saved Claude Code login (Phil approved 2026-10-10; token never printed). Codex: rate_limits snapshot from ~/.codex/sessions logs. Grok: no local meter exists, shows 'not tracked yet'. Code in `src/megazword/usage_sources.py`.
- Step 2 pacing (Codex wrote `pacing.py`, Claude reviewed/merged): auto-pick now skips AIs that are out (>=95%) or over pace (hard tasks only) and otherwise keeps the route order (cheapest first). Exception (Phil, 2026-10-10): a plan within 1h (5-hour window) or 24h (weekly) of reset with >=20% unused is used first, so leftover usage isn't wasted. Unrecognized windows never block (Phil: Claude's "iguana_necktie" is likely his Claude Cloud credit).
- Step 4 shared memory (Claude): `megazword note`, `decide`, `history`; `run --context` prepends decisions + recent activity; every run logs a 'done' entry. Stored in ~/.megazword/projects/<project>/memory.jsonl. 26 tests pass.
- Step 3 code only, not wired in (Grok, branch grok/escalate, on top of 14d09e2): `src/megazword/escalate.py`, `tests/test_escalate.py`, and `OllamaBackend` added to `src/megazword/backends.py`. `default_backends()` does not include it. `cli.py` still calls one backend and stops. Not merged to main. 84 tests pass on this branch (fake backends only).

## In progress
- Nothing. Branch `grok/escalate` is ready to merge. Nobody should edit `cli.py` for this until that merge, or the escalate module will be missing.

## Next step
Merge `grok/escalate` into main, then wire escalation into `megazword run`. Do not redo pacing or memory; those are on main.

1. Merge the branch. It should be a clean merge: `escalate.py` and `test_escalate.py` are new, and `backends.py` only adds `OllamaBackend` plus `from . import ollama`. `default_backends()` is unchanged.
2. In `cli.py` `main`, for `run` without `-m`: build the ordered list from the same names `pick()` already uses (`cfg.route[rating.level]`, then `pacing.rank(statuses, names, rating.level)` when statuses exist). Keep installed backends only, in that order. Call `escalate(prompt_sent, ordered, on_attempt=...)` from `megazword.escalate`. `prompt_sent` is the string already passed to `backend.run` (including `with_context` when `--context` is set). `on_attempt(name, result, reason)` prints `[megazword] {name} rejected: {reason}` to stderr when `reason` is set. Log, `memory.add`, and the printed answer come from `outcome.result`, not the first backend. If `outcome.result` is None, print each attempt's reason to stderr and return 1.
3. With `-m`, do not escalate. One backend, as now.
4. Do not add a "try again" flag. `escalate(..., start_after=name, prior_answer=text)` already skips that AI and everything cheaper and passes the old answer. Phil has not asked for a command for it.
5. Register the local model as `OllamaBackend("ollama", model=cfg.rater_model)`. `available()` only checks that the Ollama server answers. Do not add `ollama` to the route lists until Phil says local models should answer tasks. The rater already uses that model.
6. Extend `tests/test_cli.py` with fake backends. No real AIs and no network. Cover: first good answer is kept, a refusal moves to the next ranked backend, every backend failing returns 1, and `-m` does not move on.

Public API on the branch (signatures):

    looks_failed(text: str) -> str | None
    build_retry_prompt(prompt: str, attempts: list[Attempt]) -> str
    escalate(prompt, backends, judge=looks_failed, on_attempt=None,
             start_after=None, prior_answer=None) -> EscalationResult

`EscalationResult` has `result` (Result or None), `attempts` (list of Attempt), and `escalated` (bool). `Attempt` has `name`, `ok`, `reason` (None if kept), `answer`. Judge reasons are `"empty answer"` and `"looks like a refusal"`. A crashed backend is `"failed: <error>"` and the judge is not called. A user rejection is `"not good enough"`. Rejected answers pasted into the next prompt are cut at 1500 characters. `escalated` is true only when a backend ran after an earlier rejection.

Later, not this step: Grok still has no plan meter. Track it from `~/.megazword/log.jsonl` and ask Phil which Grok plan he has. Phone access is spec step 5.

## How to run (dev)
    python -m venv .venv
    .venv/Scripts/python -m pip install -e ".[dev]"
    .venv/Scripts/python -m pytest -q
    .venv/Scripts/megazword backends
    .venv/Scripts/megazword run "your prompt" -m claude   # or codex / grok

## Machine facts (checked 2026-10-10)
- Installed: claude 2.1.296, codex-cli 0.162.1, grok 1.0.50, Python 3.11.9, git, gh.
- Ollama 0.40.2 installed via winget 2026-10-10; model qwen2.5:1.5b pulled (rater). First rater call after idle takes up to ~60s while the model loads; warm calls ~1s. Phil turned on "Expose Ollama to the network"; it listens on all interfaces. Lock down when doing phone access (step 5).
- Not installed: gemini CLI.

## Problems / notes
- The Grok session that wrote step 3 stopped with about 9% of its own Grok 4.7 weekly limit left (the meter in the Grok CLI status bar, not a Mega Zword plan). Do not wait on that session.
