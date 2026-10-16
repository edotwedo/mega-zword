# Credit scout (ROADMAP item 4)

**Status:** open. Written by Juniper-16 (Claude Code), 2026-10-16. Meant to be worked one
step per heartbeat beat by free models; any seat may take a step too (claim with
`ROADMAP #4` on the Active line).

## Goal
Find more free AI capacity automatically. Mega Zword already lists OpenRouter's free,
tool-capable models (`src/megazword/openrouter_catalog.py`, `megazword free models`).
OpenRouter is itself an aggregator: the companies it routes to, and the ones in public
price lists, are where direct free tiers and signup grants hide.

## Rules for every step
- Parsing functions are pure (take a dict, return a list) and are tested with small JSON
  fixtures written inside the test. Tests never touch the network.
- Network fetches are thin wrappers with a 15 s timeout, like `openrouter_catalog.fetch_catalog`.
- No API keys are needed for any source below. Never add keys, logins or secrets.
- New code goes in `src/megazword/scout.py` and `tests/test_scout.py`. Don't edit
  routing.py, ledger.py, review.py, heartbeat.py or night.py.

## Steps (do the first one not yet done; tick it here with date and commit)
1. [x] (2026-10-16, written by free model nvidia via heartbeat on night/2026-10-16-2; test mocks fixed by Juniper-16) `providers_from_endpoints(payload) -> list[str]`: parse OpenRouter's
   `GET https://openrouter.ai/api/v1/models/{author}/{slug}/endpoints` response
   (`{"data": {"endpoints": [{"provider_name": ..., "pricing": {...}}, ...]}}`) into sorted,
   unique provider names; plus `fetch_endpoints(model_id)`. Tests: normal payload,
   duplicates, missing fields, empty list.
2. [ ] `zero_price_litellm(payload) -> list[dict]`: parse LiteLLM's public price file
   (`https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json`,
   a dict of model -> {"litellm_provider", "input_cost_per_token", "output_cost_per_token", ...})
   and return `{"provider", "model"}` for entries whose input and output costs are both 0.
   Skip the `sample_spec` key and entries without costs. Tests with a 4-entry fixture.
3. [ ] `leads(sources) -> list[dict]`: merge provider names from steps 1 and 2 into one
   list of `{"provider", "seen_in", "already_have"}`. `already_have` is true when the
   provider matches a Mega Zword backend family (names in `free_apis.FREE_KEYS`, e.g.
   groq, cerebras, mistral, nvidia, cloudflare, tencent, zai). Save to
   `~/.megazword/scout/leads.json` (use `config.HOME`); keep a `first_seen` date per provider.
4. [ ] `megazword scout` command: fetch both sources (endpoints for at most 25 free
   OpenRouter models from `openrouter_catalog.free_tool_models`), update leads.json and
   print NEW providers first, then known ones. One help line, under "See" in COMMAND_GROUPS.
   Tests use monkeypatched fetchers.
5. [ ] docs/GUIDE.md: a short "Finding more free AI" section: what `megazword scout`
   shows, and that every lead must be checked by a person (terms, real free amount,
   whether it can bill) before a key is added. Then `megazword credits set NAME --can-bill no`
   only after that check.

## Research half (needs web search, so for Juniper-16 / Grok, not free coders)
Regional providers to check against two sources each, results in
docs/FREE-MODEL-ROSTER.md: Alibaba Model Studio (international; Free Quota Only per
model), SiliconFlow, ModelScope API-Inference, Volcano Engine Ark, Baidu Qianfan, Zhipu
BigModel, MiniMax, StepFun, SEA-LION, Scaleway, OVH AI Endpoints, Nebius, Sarvam,
Upstage, Chutes, GitHub Models.

## Done when
`megazword scout` lists providers from both sources with new ones first, tests pass with
fakes, GUIDE has the section, and ROADMAP item 4 is ticked.

## Heartbeat log
- 2026-10-16: step 1 done (scout.providers_from_endpoints, fetch_endpoints, 4 tests). openrouter, groq and zai hit the 60-step cap first; nvidia finished with one broken mock. Next: step 2, zero_price_litellm.
