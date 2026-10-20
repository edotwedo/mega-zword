# Provider terms: what Mega Zword may do (v1 gate)

Compiled 2026-10-19/20 by Lumen-20 from Beacon-17's Claude check plus new checks for
xAI (Grok) and Google (Gemini). **Not legal advice.** This decides what v1 may ship.

## The rule we hold ourselves to

1. **Run the vendor's own unmodified CLI**, with the user's own login and subscription.
2. **Never read, store or intermediate provider credentials** (OAuth tokens, session
   cookies, `.credentials.json`).
3. **Never call the provider's API or web endpoints directly** on the user's behalf.
4. **Only read files the CLI itself writes** (logs, session files) for the usage meters.
5. **Never put a provider's name or logo in our product name or branding.** Plain text
   like "runs Claude Code / Codex / Grok" is fine (Anthropic says so explicitly).

## Per provider

| Provider | Drive the CLI (own login) | Our meter source | Verdict |
|---|---|---|---|
| **Claude** (Anthropic) | **Allowed** — Commercial Terms permit a product running the unmodified `claude` binary where each user signs in themselves. | was: read `~/.claude/.credentials.json` + `api.anthropic.com/api/oauth/usage` | **was a violation — fixed.** Meter is opt-in, off by default (`MEGAZWORD_CLAUDE_METER=1`); shipped builds never read credentials. |
| **Codex** (OpenAI) | No explicit ban found; OpenAI docs recommend API keys for programmatic workflows. | Codex's own app server (`account/rateLimits/read`) and `~/.codex/sessions` snapshots. | **OK** — reads files/endpoints the CLI itself provides, no credentials intercepted. |
| **Grok** (xAI) | Consumer Terms + Acceptable Use Policy; **no explicit statement found** on scripted CLI use. | `~/.grok/logs/unified.jsonl` — the billing line the CLI writes. | **Low risk, unconfirmed.** Local log file only. |
| **Gemini** (Google) | Official CLI ToS page maps auth method to Google/GCP terms and contains **no explicit third-party ban**. A third-party mirror states that directly accessing the services powering the CLI (e.g. via Gemini Code Assist OAuth) **is a violation**; a Google developer-forum thread reports **mass 403/ToS bans** for open-source CLI users on the paid tier. | `agy -p /usage --output-format json` — runs the vendor's own binary. | **Unconfirmed, treat as risk.** Keep CLI-only, never OAuth, never the Code Assist endpoints. Re-check before shipping. |

## Consequences for v1

- The free-API scraping lane stays **cut** — it is the part that is unambiguously risky.
- Meters that read **local files the CLI writes** (Grok, Codex) are fine.
- Any meter that touches **credentials or provider endpoints** is out. Claude's was the
  only one; it is now off by default (commit `8612ef5`).
- The installer/onboarding must state plainly: **we never see your provider logins.**

## Open, before anything ships

1. Get a written position (or a support answer) for **Grok** and **Gemini** scripted CLI
   use — the two gaps Beacon left open.
2. Re-check the Claude meter gate is off in any packaging build.
3. Keep provider names out of branding and the store listing.
