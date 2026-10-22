# Proposal: David vs Goliath - Mega Zword vs Hermes Agent

Harbor022 (Claude), 2026-10-22, at Phil's direct request. Status: **draft for Cinder-21 to put to
a Hive review and ballot.** Nothing here is built or decided. No schedule on purpose: Phil asked
for the plan, not the timeline.

Phil's goal: Hermes Agent (Nous Research) is now the enemy. Next to Mega Zword it should look like
a kindergartener wrote it. This plan gets there by **winning on the things a user can check
for themselves**, not by mocking theirs. Every claim we publish must be one a stranger can
reproduce, because a false claim is the one thing Goliath could use against us.

## 1. What they have (read from their repo, commit 4e58c721, 2026-10-21)

Source: a shallow clone of https://github.com/NousResearch/hermes-agent, read but never run.

| Area | Hermes Agent |
| --- | --- |
| License, backing | MIT. Nous Research raised a reported $90M at a $1.5B valuation (WSJ, via Dealroom, Oct 2026). Tens of thousands of GitHub stars. |
| Core | One self-improving agent. It writes its own skills from experience, searches its past chats and builds a profile of the user. |
| Models | Any API model: Nous Portal, OpenRouter, OpenAI, custom endpoints. Mostly **pay-per-token**. |
| Our idea, already shipped | Bundled skills "Delegate coding to Claude Code CLI" and "...Codex CLI", working with a subscription login. |
| Reach | Telegram, Discord, Slack, WhatsApp, Signal, email and CLI from one gateway process. Voice memo transcription. Android through Termux. |
| Multi-agent | "Hosted rooms" in the gateway, a bot-loop guard, and subagents with their own provider and limits. |
| Automation | Built-in cron with delivery to any platform. |
| Runs on | Local, Docker, SSH, Singularity, Modal, Daytona, Vercel Sandbox. Native Windows, macOS, Linux. |
| Skills | 211 bundled and optional `SKILL.md` files. |
| Tests | About 6,750 test files. |

**Where they are weak (each one checked in their repo or their own docs):**

1. **It acts safe while saying it isn't.** Their `SECURITY.md` admits the agent can do whatever
   the user's account can reach and that the only real boundary is a container or VM, yet the
   product is pitched as a friendly personal assistant. We don't attack them on safety (we are no
   safer); we attack the dishonesty. Mega Zword says it on the label (Pillar C).
2. **It does not check out on a stock Windows PC.** `git clone` fails with "Filename too long" on
   about 25 doc paths, and Git reports "checkout failed".
3. **The Windows install fights antivirus.** Their README has a whole section on Defender and
   Bitdefender quarantining the bundled `uv.exe`, telling users to whitelist the folder. The
   installer also pulls Python 3.14, Node.js, npm, ripgrep and FFmpeg.
4. **The code is sprawling.** 80 Python files sit loose at the repo root, 60 of them
   `hermes_state_*.py`. Two scratch files are committed at the root
   (`hermes_constants_scratch.py`, `hermes_constants_scratch_stuck.py`). The repo holds about
   10,000 Python files.
5. **It is one agent, not a team.** Subagents are copies of the same agent. Nothing has a second
   vendor check the first one's work.
6. **It does not watch your plans.** Its Claude skill mentions `/usage`, but nothing reads every
   plan's meter and routes work to whoever has room. Its economics assume you buy tokens.

## 2. What we have (true on main today)

| Area | Mega Zword + Hive |
| --- | --- |
| Economics | `megazword usage` reads the live meters of 5 paid plans (Claude, Codex, Grok, Gemini/agy, cmdc). `plan` ranks them, `spot` warns at the floor, a reserve is shown per plan. About 30 free sources (Groq, Cloudflare, Z.ai, Mistral, NVIDIA, OpenRouter, Tencent grants and more) with failover. A `credits` ledger. |
| Team | Five seats, each a different vendor, with one conductor. The cloud Hive room (Worker + D1), claims, ballots (`megazword vote`), seat status, retire and replace, and respawn (`resume`). |
| Control | `andon` (stop cord), `gate` (the suite blocks a red push), `rules check` (no unvoted rule change), the guard hook, secret scrubbing, keys in the Windows vault. |
| Automation | Night Shift, heartbeat, and the team job planner (`job`). |
| Tools | `review` (free AIs plus Greptile), `map` (repo symbol map), `scout` (finds new providers), `route-lab`, `sentinel`, `stats`, `advise`. |
| Surfaces | Desktop window and dashboard, phone web page, Discord mirror (one way), Hive MCP server, start screen. |

**Where we are weak (honest, because the plan has to fix these first):**

1. Built for one user. There is no installer a stranger can run, and no code signing.
2. The GUI does not yet cover everything the CLI does.
3. Reaching the Hive from a phone needs a key lookup, and the Discord mirror is one way.
4. Reliability holes found on 2026-10-21: an outbox jams behind one rejected post, a phantom
   claim, stale cache reads, and a listener that reported Ready while dead.
5. The provider terms for Grok and Gemini are still unresolved.
6. Memory is project notes plus logs. There is no searchable memory across seats yet.
7. We have no sandbox and we are not building one (Phil, 2026-10-22). Mega Zword is not a safe
   product and does not pretend to be. That is the positioning, not a gap (Pillar C).

## 3. The strategy: fight where Goliath cannot follow

A $1.5B company with 10,000 files cannot easily become small, honest, Windows-first and
multi-vendor. Those are our four ground rules.

### Pillar A - "The plans you already pay for" (the economics they cannot copy)
Hermes's business sells tokens through Nous Portal and OpenRouter. Ours makes the user's existing
subscriptions plus free grants do the work.

- A1. The usage board becomes the home screen: every plan, every window, reserve and reset time,
  plus what the free sources have left.
- A2. Routing on by default: each job goes to the plan with the most room that fits the work, and
  never below the floor.
- A3. A "money saved" meter: what each job would have cost at API prices against what it cost.
- A4. A public benchmark: one fixed task set, run through Hermes on OpenRouter and through
  Mega Zword on subscriptions. Publish the dollars and the scripts.

### Pillar B - "A team that checks itself" (the quality they do not have)
- B1. Every change gets a review from a second vendor (the P1 mechanism M3, built for real).
- B2. Ballots for decisions, a conductor for the queue, file locks instead of prose claims
  (P1 mechanisms M1, M2, M6, M7).
- B3. A public benchmark: plant bugs in a repo and count what one Hermes agent catches against
  what a cross-vendor review catches.

### Pillar C - "The rally car" (honest about what it is)
Phil, 2026-10-22: **we are not building security.** Mega Zword is the driver's seat of the rally
car of AI options: full speed, full access, a cage instead of airbags. Run it in a sandbox unless
you're insane. The developer is insane, which is why this project exists. Get in, loser, we're
going speeding.

Hermes dresses a full-access agent up as a gentle assistant. We say the truth on the label and
make it the brand.

- C1. The warning is the first screen of the installer and the first line of the README: what
  every seat can touch, in one sentence, and "run it in a sandbox."
- C2. A short guide to putting it in a cage (Windows Sandbox, a VM, or a spare user account). It is
  a guide, not a feature we build or maintain.
- C3. The brand voice everywhere: fast, loud, no hand-holding, nothing hidden.

### Pillar D - "It just works on Windows" (where they trip at the door)
- D1. One signed installer, no antivirus warnings, no Python, Node or FFmpeg to fetch.
- D2. First run finds the AI CLIs the user already has and is working in under 5 minutes.
- D3. A clean-machine install test in the gate, so the front door can never break unseen.
- D4. Repo hygiene a stranger can see: short paths, no scratch files, a size cap per module,
  a tidy root.

### Pillar E - "Take their strengths" (so they have nothing left to point at)
- E1. Phone: a two-way Telegram and Discord gateway into the Hive. Phil posts from his phone and
  seats answer there. One bookmark, no key lookup.
- E2. Memory: searchable memory shared across seats, built on the P2/A2 memory index, with
  MemPalace-style verbatim recall as a plug-in.
- E3. Scheduling through the one supervisor (P1 mechanism M5), never seats scheduling themselves.
- E4. **Make Goliath a worker.** Add Hermes as a Mega Zword seat on its own plan. "Mega Zword runs Hermes too" is the line that ends the comparison: the team includes them.

### Pillar F - "Never dies silently" (fix our own holes before we point at theirs)
- F1. Fix the 2026-10-21 failures: the outbox jam, the phantom claim, stale reads, the listener
  that lied about being Ready.
- F2. A monotonic heartbeat and watchdog, plus a daily synthetic message carried end to end
  (P1 mechanism M4).
- F3. A status page that shows observed liveness, never claimed liveness.

## 4. The comparison page (the "kindergartener" moment)

One page on megazword.com, every row backed by a script anyone can run:

| Check | How it is measured |
| --- | --- |
| Install on a fresh Windows 11 PC | Time and clicks to the first answer; antivirus warnings counted |
| Cost of the benchmark task set | API dollars spent, with the scripts published |
| Bugs caught in a planted-bug repo | Count, with the repo published |
| Says what it can touch, up front | Is the full-access warning on the first screen? (Ours is.) |
| Dies silently? | Kill a worker mid-task and see who reports it |
| Uses the subscriptions you already pay for | Yes or no, per plan |

No insults on the page. The numbers do the work, and every claim we make must survive Nous
Research trying to reproduce it.

## 5. Order of battle (sequence only, no dates)

1. **Fix our own house:** Pillar F, then P1 mechanisms M1 to M3. A team that jams cannot claim to
   be the careful one.
2. **The moat:** Pillar A (A1 to A3), with Pillar C's warning and brand voice from day one.
3. **The front door:** Pillar D, and resolve the provider terms for Grok and Gemini.
4. **Take their strengths:** Pillar E (E1 phone first, then E2 memory, then E4 Hermes as a seat).
5. **Prove it:** the benchmarks (A4, B3) and the comparison page.
6. **Launch:** public beta, code signing, the comparison page live.

## 6. Ballot items for the Hive (proposed as P3)

- **H1** Adopt the strategy: win on the economics of existing plans, cross-vendor teams, honesty
  and Windows polish, not on feature count.
- **H2** Adopt the order of battle in section 5: fix our own house first.
- **H3** Publish only reproducible comparisons; no claim goes out without its script.
- **H4** Build E4: Hermes as a Mega Zword seat.
- **H5** Build E1: a two-way phone gateway (Telegram or Discord) into the Hive.
- **H6** Adopt the rally car positioning (Pillar C): no security features, a run-it-in-a-sandbox
  warning on the first screen, and a cage guide.

Owners are the conductor's call. Fit suggestions only: Cinder-21 integrates; Briar-20 (Codex)
takes the heavy edits (F1, D, E1); Nock-21 (Grok) takes breadth and benchmarks (A4, B3, the
comparison page); Forge-22 (Gemini) gives second opinions on E2 and the brand voice; Harbor022
(Claude) reviews the high-risk changes (F, E1) and keeps this plan honest.
