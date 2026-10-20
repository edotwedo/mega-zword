# Mega Zword business model

Evidence-backed companion to `docs/BUSINESS-PLAN.md` (Lumen-20, branch `seat/lumen-20`;
**not on main yet**). Owner this shift: Quill-21. All prices checked **2026-10-19**, each
linked in Sources. The plan holds the positioning, the license decision and the cash
ladder; this file adds the competitor table, the unit economics and the go-to-market
sequence, and marks what still needs Phil's call.

## 1. Who buys, and the pain we charge for

- The buyer is the developer already paying for **2-4 AI subscriptions**. Paying
  developers average ~3.5 subscriptions; 70% run 2-4 tools at once
  ([AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/15/ai-agent-subscription-fatigue-developer-tool-spending-crisis)).
- Baseline stack is ~$70/mo: Copilot Pro $10, Cursor Pro $20, Claude Pro $20, ChatGPT
  Plus $20 — before any overage. Heavy users hit Claude Max $100-200/mo and report
  $500-2,000/mo in sprint consumption. Token-based tooling has been measured at
  $500-1,500/dev/mo of unpredictable OpEx ([AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/15/ai-agent-subscription-fatigue-developer-tool-spending-crisis),
  [futureproofing.dev](https://www.futureproofing.dev/resources/ai-native-team/claude-code-vs-cursor-pricing-2026)).
- The pain is not price, it is **waste and uncertainty**: quota that goes unused on one
  plan while another throttles, retyping the same prompt into three tabs, and no record
  of which model did which work or what it cost.
- Our wedge: nobody sells *coordination of the subscriptions you already own*. The
  market sells either a BYO-key chat shell or a single-vendor agent.

## 2. Competitive landscape (checked 2026-10-19)

| Product | Model | Price | What it is | Gap we exploit |
| --- | --- | --- | --- | --- |
| **TypingMind** | One-time | $39 / $79 / $99; bulk $395 for 10 seats; Teams custom | Browser chat shell for BYO API keys; 20,641+ customers | Chat only; you still pay per token and still drive the CLIs by hand |
| **Msty Studio** | Free + one-time/sub | Free; Aurum $149/yr; Lifetime $349; Teams ~$300/user/yr | No-terminal local+cloud desktop chat | Chat, not orchestration; no task routing, no cost ledger |
| **LibreChat** | Open source (MIT) | Free; you pay hosting + tokens | Self-hosted multi-model chat | Same — a chat surface, no bench |
| **Open WebUI** | Open source | Free; Enterprise is "contact us" (SSO/RBAC/audit, branding) | Self-hosted chat platform | Enterprise add-ons are the paid layer, not orchestration |
| **Cursor / Claude Code / Codex** | Subscription | Cursor Pro $20 (Pro+ $60, Ultra $200); Claude Pro $20, Max 5x $100, 20x $200; real spend $150-250/dev/mo | Single-vendor coding agents | Single vendor by design; no cross-family routing or review |
| **Aider / Cline / OpenHands / OpenCode / Goose / Plandex** | Open source | Free + your tokens | Terminal/IDE coding agents (Aider Apache-2.0 ~39k★; Cline ~60k★; OpenHands ~68k★; OpenCode 100k+★) | One agent, one model config, no shared floor or usage pacing |
| **AI agencies** | Service | $5k-50k projects, $2k-15k/mo retainers | Done-for-you automation | Not a productized setup; our $150-300 session undercuts the door |

Read across it: the paid layer in this market is **polish and hosting**, not routing.
That supports the plan's open-core split (Apache-2.0 guts, proprietary polish).

## 3. Positioning (keep the plan's line)

> **Mission control for your AI subscriptions** — route every job to the cheapest capable
> model, coordinate agents without collisions, prove the result with tests.

Four things no single competitor above does together:

1. **Drives the CLIs you already pay for** (Claude Code, Codex, Grok, agy) instead of
   reselling tokens or adding a seat.
2. **Difficulty routing with usage pacing** — skip plans at ≥95%, reserve fast-burn
   plans for hard jobs, fall through on failure.
3. **A shared floor** — seats, wake, escalation, handoff; the phone can dispatch.
4. **Evidence** — a per-job cost ledger and cross-family review before merge.

## 4. Pricing architecture

Plan's numbers hold against the evidence, with two refinements:

| Offer | Price | Benchmark it sits on | Verdict |
| --- | --- | --- | --- |
| Founding lifetime (first 50) | **$49** | TypingMind $39/$79/$99 | Good — under Premium, above Standard |
| Pro lifetime (after founding) | **$99** → later **$149** | TypingMind Premium $99; Msty Lifetime $349 | Raise to $149 once 20+ testimonials exist; $349 is the ceiling |
| Support + updates (optional) | **$15/mo** | — | Keep strictly optional; see §5 |
| Done-for-you setup | **$150-300** | Agencies $5k-50k; sessions $150-1,200 | Right wedge; upsell to $500+ only after 3 delivered |
| Team (later) | $300+/seat/yr | Msty Teams ~$300/user/yr; TypingMind Teams custom | Mirror Msty |

Two decisions to make explicit: **one-time is the hook, not the business** (TypingMind
itself funds lifetime sales with a Team subscription), and **refunds** should match the
category's 14-day money-back norm.

## 5. Unit economics

Payment (recommend **Lemon Squeezy** over Gumroad — merchant-of-record VAT handling and
5% + $0.50 vs Gumroad's flat 10%):

| Sale | Gross | Fee | Net | Margin |
| --- | --- | --- | --- | --- |
| Founding license $49 | $49 | $2.95 | $46.05 | 94% |
| Pro lifetime $99 | $99 | $5.45 | $93.55 | 94% |
| Bulk 10-seat $395 | $395 | $20.25 | $374.75 | 95% |
| Support $15/mo | $15 | $1.25 | $13.75 | 92% |

- **Infra COGS ≈ $0.** The hosted room runs on Cloudflare Workers/D1 free tiers
  (100k req/day) — this is the proof of the "costs stay flat as income rises" promise,
  and it should survive the first few hundred users before any paid tier.
- **Support is the only real COGS.** $13.75/mo buys roughly one hour per quarter at a
  ~$55/h loaded rate. Cap support to business hours, template the top 5 answers, and let
  `megazword doctor` plus the sanitized diagnostic report (plan §"Support bot") absorb
  the rest.
- **Setup delivery** nets ~$237 of a $250 session before your time; budget ≤2 h.

## 6. Go-to-market sequence

Order matters — do not open the lifetime sale before the gate is ready.

1. **This week — paid setup sessions** (cash, no product risk). Use Mega Zword as the
   demo and the delivery tool. Channel: local network, X/LinkedIn, r/selfhosted "I'll set
   this up" threads, Upwork/Fiverr as fallback. Goal: 3 sessions, 3 testimonials.
2. **Gate, then launch founding lifetime.** Required before launch: signed installer,
   sub-5-minute onboarding (detect CLIs → import keys → first routed run), 3 demo videos,
   honest limitations section. Sell on Lemon Squeezy; run Show HN + Product Hunt the same
   week.
3. **Support tier** after the first 20 licenses.
4. **Team/audit tier** after the roadmap's cost ledger, durable jobs and escalation land
   (they are the trust features the premium tier is priced on).

Channels, by cost: GitHub + README (free, compounding), Show HN (one shot — participate
first, the feed is crowded in 2026), Reddit (r/LocalLLaMA, r/ClaudeAI, r/ChatGPTPro,
r/selfhosted — answer first, post where self-promo is allowed), build-in-public numbers on
X/LinkedIn, Product Hunt, docs-led growth (every error links to a fix), demos over claims.

## 7. Funnel targets (assumptions, to be replaced by real numbers)

| Stage | Assumption | Month 1 target | Month 3 target |
| --- | --- | --- | --- |
| Traffic | Show HN front page ≈ 8k visits; later organic | 5-10k | 20k |
| Email/waitlist | 2-4% of traffic | 200 | 700 |
| License conversion | 1-2% of traffic | 20-40 | 60-120 |
| Setup sales | direct outreach + threads | 3 | 6 |
| Support subs | 10% of license holders after 20 | 0 | 10-15 |
| **Cash** | — | **$1,000-2,000** | **$3,000-5,000/mo run-rate** |

These are the plan's targets, decomposed. They are unproven; treat the middle of each
range as the planning number and re-baseline after the first launch week.

## 8. Risks and open questions

Risks already covered by the plan: support eating margin, open core being cloned,
one-time revenue drying up, debt pressure causing bad deals, burnout. Add one:

- **The value prop needs multi-subscription ownership.** A single-subscription user sees
  little benefit. Target the paying 3.5-subscription developer explicitly in copy and in
  the Reddit/Show HN framing, or conversions will look worse than the model predicts.

Open questions for Phil (blocking or near-blocking):

1. **License switch**: the plan decides Apache-2.0 guts / proprietary polish, but
   `README.md` and `LICENSE` still say proprietary. When does that land? Copy must match.
2. **Storefront**: Gumroad or Lemon Squeezy account, and who owns it?
3. **Setup services**: sell under Phil's name/calendar, or as an anonymous productized
   offer? Availability window (evenings only)?
4. **Founding price**: $49 or $39 to match TypingMind Standard exactly?
5. **Refund policy**: adopt 14-day money-back to match the category?

## Sources

- [TypingMind pricing](https://www.typingmind.com/buy) · [TypingMind review/pricing](https://toolchase.com/tool/typingmind/) · [ToolRadar: TypingMind pricing](https://toolradar.com/tools/typingmind/pricing)
- [Msty pricing/review](https://aitrendtool.com/tools/msty) · [Msty tiers detail](https://kunavo.com/guides/msty-api-cost)
- [LibreChat pricing/cost](https://kunavo.com/guides/librechat-api-cost) · [Open WebUI enterprise license](https://vdf.ai/blog/open-webui-enterprise-license/) · [Open WebUI pricing guide](https://markaicode.com/pricing/open-webui-pricing/)
- [AI agent subscription fatigue: the $840/yr problem](https://agentmarketcap.ai/blog/2026/04/15/ai-agent-subscription-fatigue-developer-tool-spending-crisis) · [AI coding agent costs 2026](https://www.agensi.io/learn/ai-coding-agent-costs-compared-2026) · [Claude Code vs Cursor pricing 2026](https://www.futureproofing.dev/resources/ai-native-team/claude-code-vs-cursor-pricing-2026)
- [Terminal coding agents compared](https://amux.io/blog/best-terminal-ai-coding-agents-2026/) · [Coding CLI tools compared](https://www.tembo.io/blog/coding-cli-tools-comparison)
- [Gumroad vs Lemon Squeezy fees 2026](https://www.usefeekit.com/blog/gumroad-vs-lemon-squeezy-fees-2026) · [Gumroad vs Lemon Squeezy](https://www.pocketsflow.com/blog/gumroad-vs-lemon-squeezy)
- [AI agency pricing 2026](https://digitalagencynetwork.com/ai-agency-pricing/) · [AI automation agency cost](https://thecrunch.io/ai-automation-agency-cost/)
- [How to promote a devtool](https://dupple.com/learn/how-to-promote-your-devtool)
