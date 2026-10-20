# Mega Zword landing page copy

Draft copy for the founding-lifetime launch. Plain text so it can be pasted into any
builder. Sells the **bench**, not a model. Everything marked `[VERIFY]` is a claim that
must be true (or removed) before publishing — see the checklist at the end.

## Meta

- **Title:** Mega Zword — mission control for your AI subscriptions
- **Meta description:** One command line, every AI you pay for. Route each job to the
  cheapest model that can do it, keep the agents from colliding, and prove the result
  with tests.
- **OG headline:** Stop paying for four AI subscriptions and driving them by hand.

## Hero

**H1:** Your AI subscriptions, finally working as one bench.

**Sub:** Mega Zword routes every job to the cheapest model that can do it — Claude Code,
Codex, Grok, Gemini, local models — tracks what each one costs, and keeps them from
stepping on each other. One command line. Your keys, your machine, your existing plans.

**Primary CTA:** Get the founding license — $49 (first 50)
**Secondary CTA:** Watch a 60-second demo
**Under CTA:** One-time. Lifetime updates. 14-day money-back.

## Problem

You are paying for three AI subscriptions. You are still the router.

- The quota you did not use on one plan while another plan throttled you.
- The same prompt pasted into three tabs, three times.
- The four-hour agent run that died at step 40 with nothing to show.
- No answer to "which model did this, and what did it cost?" when a client asks.

The stack grew one subscription at a time. Nobody planned it. Mega Zword is the layer
that makes the stack behave.

## How it works

1. **Point it at the CLIs you already own.** Mega Zword detects your installed tools and
   reads their existing logins. No new accounts, no API keys resold to you, no per-seat
   fee.
2. **Describe the job.** Mega Zword rates difficulty, checks live plan usage, and picks
   the cheapest capable model. If one refuses or fails, it moves to the next.
3. **Get the result and the receipt.** The work lands with a cost line — model, steps,
   tokens — and the option to have a different model family review it before you trust
   it. `[VERIFY: cost ledger and review gate ship before launch]`

## Features

- **Free-first routing.** Configured free APIs and local models get first attempt at
  every difficulty; paid plans are fallbacks. `[VERIFY: matches Beta 3.0 behavior]`
- **Live usage meters.** See plan quota before you start, not after you are throttled.
- **The Hive floor.** Give each AI a seat. They read the room, you dispatch from the
  dashboard or your phone, and a wake message brings the right seat back.
- **Nothing dies quietly.** `[VERIFY: durable jobs + escalation land in the night roadmap]`
- **A cost ledger you can trust.** `[VERIFY]` Per job, per model, per project, one command.
- **Cross-family review.** `[VERIFY]` A different model reviews the change before it
  merges.
- **Runs where you do.** Windows today, CI on Windows and Linux. Open-source core. Your
  prompts never leave your machine except to the providers you already use.

## Proof

`[VERIFY — replace with real material]`

- "I run four AI subscriptions from one CLI and never hit a quota surprise." — *demo
  video, 60s*
- Before/after: **3 clients, $750 delivered in week one** using Mega Zword as the tool.
- Numbers from our own bench: **X% less spend per finished job**, **Y jobs run
  unattended**.

Honest limitations, stated up front (this earns more trust than hiding it):

- You need at least one installed AI CLI and a paid plan (or a free API key) to get value.
- Grok is left out of edit mode on Windows today.
- The dashboard is local by default; remote access needs Tailscale.
- It is a bench, not magic: routing saves money, it does not make a bad prompt good.

## Pricing

**Founding lifetime license — $49** *(first 50 only)*
Everything in the core bench, forever, plus updates. Price goes to $99 after the
founding batch.

**Pro lifetime — $99** *(after founding)*
Adds `[VERIFY: premium features once defined]`.

**Support + updates — $15/mo** *(optional)*
We answer within a business day, and can dial in with your consent. Cancel anytime.

**Done-for-you setup — from $250**
A 60-90 minute session: install, detect your CLIs, import keys, wire the Hive, and hand
you a one-page cheat sheet and a working bench.

*Not included: the AI plans and API usage you already pay for.*

## FAQ

**Do I need an API key?** No. If you already run Claude Code, Codex, Grok or the
Antigravity CLI, Mega Zword uses those logins. Free API keys (OpenRouter, Groq) are
optional extras.

**Does this replace my subscriptions?** No — it makes them work together. Keep the plans
you use; we route and coordinate them.

**Is it open source?** The core is. `[VERIFY: finalize license before publishing —
README currently says proprietary.]` The polished installer, on-boarding and hosted
features are what the license pays for.

**What runs on your servers?** Nothing by default. Routing, logs and project memory stay
on your machine. The optional cloud room is a free Cloudflare Worker you can self-deploy.

**What if it does not work for me?** 14-day money-back, no questions.

## Final CTA

**You already bought the AIs. Now make them a team.**
Get the founding license — $49, first 50. → *[Buy on Lemon Squeezy]*

## Footer

Docs · Changelog · GitHub · Contact · License · "Built and coordinated by Mega Zword's
own agent bench" (put a real number here: jobs run, dollars saved).

## Before you publish — verification checklist

1. **License.** `README.md` and `LICENSE` still say proprietary. The Apache-2.0 guts /
   proprietary polish split is a decision, not a done deal. Copy must not claim open
   source until it is.
2. **Every `[VERIFY]` above** — cost ledger, durable jobs, escalation, cross-family review
   — must actually ship, or move to a clearly-labeled "on the roadmap" section.
3. **Testimonials and numbers** must be real. No invented quotes, no placeholder metrics on
   a live page.
4. **Refund + support promises** must match what Phil can actually staff (business hours,
   one hour per quarter).
5. **Storefront** account (Gumroad or Lemon Squeezy) and payout details exist before the
   CTA goes live.
