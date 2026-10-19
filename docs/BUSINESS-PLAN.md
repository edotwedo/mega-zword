# Mega Zword: fastest path to revenue + users

Phil's constraint (2026-10-19): needs money **now** (debt), needs popularity, and wants
costs to stay flat as income rises so the work can eventually be given away. Every
choice below is judged by one question: **does it produce cash in 30 days without
adding recurring cost?**

## Positioning

Sell **the bench, not a model**:

> "Mission control for your AI subscriptions: route every job to the cheapest capable
> model, coordinate agents without collisions, and prove the result with tests."

Buyer: the person already paying for 2-4 AI subscriptions who is tired of tab-copying,
quota surprises, and not knowing which model did the work. Not "people curious about AI."

## License (decision)

- **Guts (`src/`, CLI, agent loop): Apache-2.0.**
- **Polish stays proprietary:** installer/packaging, auto-update, tray app, onboarding,
  support bot, hosted room, brand/trademark, team features.
- Why not AGPL: its network clause makes the paid hosted/packaged product a legal
  question, and it deters the contributors who create popularity. Why not BSL now:
  source-available scares the open-source crowd that drives adoption; revisit BSL only
  if a competitor starts hosting the guts.
- Evidence: TypingMind and Msty both sell closed apps in an open ecosystem; Dokploy
  keeps a permissive core with SSO/audit/RBAC behind a commercial layer.

## Pricing (evidence-based)

| Offer | Price | Why |
| --- | --- | --- |
| **Founding lifetime license** (first 50) | **$49** | TypingMind Standard is $39; captures early cash + testimonials |
| Pro lifetime (after founding) | **$99** | TypingMind Premium is $99 |
| Support + updates subscription (optional) | **$15/mo** | Covers ongoing support cost; matches Phil's original idea |
| Lifetime premium (later, once proven) | **$149-349** | Msty charges $149/yr and $349 lifetime |
| **Done-for-you setup** (60-90 min) | **$150-300** | Market rate for AI setup sessions is $150-1,200 |

One-time is the hook (the market expects it); the subscription is for people who want
updates + a human/bot on call. Keep the $15/mo strictly optional.

## Fastest cash ladder (in order)

1. **Done-for-you setup, this week.** Use Mega Zword as the demo and the delivery
   tool. One flat package: install, detect CLIs, import keys, wire the hive room,
   leave them with a working bench + a 1-page cheat sheet. 3 clients x $250 = $750.
   Channel: local network, X/LinkedIn, r/selfhosted "I'll set this up" threads,
   Upwork/Fiverr as a fallback.
2. **Founding lifetime licenses.** Landing page + Gumroad/Lemon Squeezy. 50 x $49 =
   $2,450. Requires: signed installer, 5-minute onboarding, one demo video.
3. **Support tier.** $15/mo after the first 20 licenses; no promises beyond "we answer
   within a business day and can dial in with your consent."
4. **Consulting/automation** using the tool as portfolio proof (highest $/hour, least
   scalable; use to bridge until licenses land).

Month-1 target: **$1,000-2,000 cash**, zero new recurring infra cost.

## Popularity engine (cost: time, not money)

- **GitHub, Apache-2.0, great README** with a 60-second GIF and an honest limitations
  section. Open issues labeled `good first issue`.
- **Show HN** once the installer works. Title sells the outcome, not the tech:
  "I run four AI subscriptions from one CLI and never hit a quota surprise."
- **Reddit:** r/LocalLLaMA, r/ClaudeAI, r/ChatGPTPro, r/selfhosted — participate first,
  post only where self-promo is allowed, answer questions in the comments.
- **Build in public:** short posts with real numbers (tokens saved, jobs finished).
- **Product Hunt** at the same time as the founding-license launch.
- **Docs-led growth:** every error message links to a fix page; `megazword doctor`
  is the onboarding.
- **Demos over claims:** 30-60s screen recordings of a real job finishing, reviewed
  by a different model family, and landing on main.

## What makes it feel "premier" (and therefore payable)

1. Signed installer + auto-update + tray app (no Python setup for end users).
2. Onboarding in under 5 minutes (detect CLIs, import keys, first routed run).
3. A cost ledger you can trust: per job/model/project, one command.
4. Durable jobs + escalation: nothing silently dies; someone is always on call.
5. The Hive as a real surface: who is on what, blockers, handoffs, one-click dispatch
   from the phone.
6. Cross-family review before merge (trust).
7. Exportable reports for clients ("here's what the AI did and what it cost").

## Support bot (the differentiator, scoped safely)

- **v1 (this month):** local diagnostic agent, run with explicit consent, that produces
  a **sanitized** report (doctor output, versions, recent errors, no keys/paths if the
  user opts out). The user pastes it or sends it with one click. No remote shell.
- **v2:** guided remote session with an audit log and a kill switch.
- **v3:** hosted agent with scoped permissions, retention policy, and liability terms.
- Never ship silent remote access. Consent + audit is the product promise.

## 30 / 60 / 90

**Days 1-30 — cash + proof**
- Ship a signed, one-click installer and the 5-minute onboarding.
- Record 3 demo videos (bench, cost ledger, Hive phone dispatch).
- Launch founding lifetime at $49 (Gumroad/Lemon Squeezy) + Show HN + Product Hunt.
- Book 2-3 paid setup sessions.
- Success: first $1,000, 20+ licenses, 50+ GitHub stars.

**Days 31-60 — trust + recurring**
- Cost ledger, durable jobs, escalation (the night roadmap items).
- Add the $15/mo support tier.
- Publish 2 case studies with real numbers.
- Success: $300/mo recurring, 100+ stars, first organic testimonials.

**Days 61-90 — premium**
- Team features (shared budgets, seats, audit log) at a higher tier.
- Repo map + review gate as headline features.
- Success: $1,000/mo combined, one team customer.

## Risks and mitigations

- **Support eats the margin.** Cap support to business hours, automate diagnostics,
  and price the subscription to cover one hour/quarter.
- **Open core gets cloned.** Trademark + polish + support are the moat, not the code.
- **One-time revenue dries up.** Founding price is time-boxed; the subscription covers
  continued updates. Revisit a paid major-version upgrade later.
- **Burnout.** The conductor loop does the repetitive work; Phil decides, doesn't operate.
- **Debt pressure leads to bad deals.** No custom contracts below $150; no free 1:1
  support before 20 licenses.

## Two-instance split (so this and the code both move)

- **Lumen-20 (me):** engineering + conductor. Owns the night roadmap
  (`docs/INSPIRATION-ROADMAP.md`), code, tests, deploys.
- **Second `cmdc` instance:** business lane. Reads this plan + `docs/INSPIRATION.md`,
  does competitor/price research, writes `docs/BUSINESS-MODEL.md` and landing-page
  copy. No code files. Claims in the room as its own designation.

## Sources

- [TypingMind pricing](https://www.typingmind.com/buy) · [TypingMind review/pricing](https://toolchase.com/tool/typingmind/)
- [Msty pricing](https://msty.ai/pricing/) · [Msty review/lifetime](https://aitrendtool.com/tools/msty)
- [Open-core model](https://en.wikipedia.org/wiki/Open-core_model) · [Dokploy license split](https://bex.co/blog/2026/07/28/dokploy-license-split-open-core)
- [AI setup service cost](https://seofyai.com/ai-setup-service-cost/) · [AI automation agency pricing](https://taskip.net/ai-automation-agency-pricing/)
- [Getting first users for dev tools](https://www.disvia.ai/blog/get-first-users-for-developer-tool) · [Devtool promotion playbook](https://dupple.com/learn/how-to-promote-your-devtool)
