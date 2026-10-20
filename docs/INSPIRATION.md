# Inspiration: software from other fields (Beacon-17, 2026-10-19)

Phil asked for ideas from anywhere, even unrelated areas. Each entry: what the other system does,
then the idea for the Hive / Mega Zword (Beacon-17's ideas, not decisions). Vendor numbers are their
own claims unless noted.

## Getting bots to answer and show up

1. **Ham radio directed nets.** Net control opens, asks for emergency traffic first, takes a roll
   call, logs each check-in, then calls for late or missed check-ins; stations leaving early say
   "in and out". Idea: a Broadcast opens a roll sheet in the room (answered / not yet), a 2-minute
   "late check-ins" line, an `in-and-out` status for a seat signing off, and a priority tag that
   jumps the queue.
2. **PagerDuty escalation.** An alert climbs a ladder (primary, secondary, manager) every 5-15 min
   until someone acknowledges; an ack timeout restarts it if the issue stays open. Idea: if no seat
   answers Phil within N minutes, ping the next seat, then Phil's phone ("nobody picked up"). Fixes
   the "why isn't anyone answering" problem directly.
3. **Zello (push-to-talk).** Phone walkie-talkie: channels, a dispatch queue that shows your place,
   replayable messages, broadcasts. Idea: hold-to-talk on the phone page, transcribed into a room
   post; a queue view showing which seat has Phil's request.

## Moving work between bots

4. **Air traffic flight strips.** Every flight is a strip on a board; handing a plane to the next
   controller moves the strip; a strip pushed out of line ("cocked") flags a problem; corrections are
   crossed out, never erased. Idea: a job board where each job is a strip that moves seat to seat,
   a "flagged" state anyone can set, and history that's struck through instead of deleted.
5. **I-PASS hospital handoffs.** Structured shift-change handoff: severity, summary, action list,
   "if X then Y" contingencies, and the receiver restates it (synthesis). A 2014 NEJM study of nine
   hospitals found medical errors fell 23% and preventable adverse events 30%, with no extra time.
   Idea: handoffs get those five fields, and the receiving bot posts a one-line read-back before it
   starts, which catches misunderstandings before tokens are spent.
6. **Kitchen display systems.** Tickets route by station (grill, cold, bar); expo holds the order
   until every part is ready; one tap to bump (done) or recall. Idea: the team engine's combine step
   works like expo (nothing ships until every piece passes), plus bump/recall buttons on the phone page.
7. **Toyota andon cord + kanban.** Anyone can pull the cord to stop the line on a problem; kanban
   caps work in progress, and work is pulled when there is room, never pushed. Idea: an `andon`
   command (Phil or any seat) that pauses a job for everyone; a WIP limit of 1-2 claims per seat.

## Spending usage wisely

8. **Tesla Powerwall time-based control.** Charges when power is cheap and discharges at peak,
   from the rate plan, with a backup-reserve slider. Idea: each AI's usage as a battery: spend
   before a reset (already "use it or lose it"), plus a reserve slider Phil sets per AI (the night
   rule's 20% floor, made visible and adjustable).
9. **Cloud spot instances (AWS + Karpenter).** A 2-minute warning before the machine is taken away;
   the node drains, and work falls back to regular capacity. Idea: when a seat nears its limit it
   gets a warning, writes its checkpoint note, and the job moves to the next AI automatically.
10. **Temporal durable workflows.** Every step's result is saved to a log; after a crash the workflow
    replays from the log without redoing finished steps. Idea: cache each model step's result, so a
    retried job never pays again for steps that already succeeded (most of the 459K-token waste was
    re-sending finished work).
11. **Erlang supervisors.** Crashed workers restart, but only up to N times in a window; past that,
    the supervisor gives up and escalates to the level above. Idea: "stop thrashing jobs" as code:
    3 failures in 10 minutes, the job stops and posts to Phil instead of retrying to the step cap.
12. **LiteLLM gateway.** Per-key budgets, cooldown after allowed failures, fallbacks, usage-based
    routing. Idea: copy `allowed_fails` + `cooldown_time` per free source, and a per-job budget cap.
13. **Langfuse / Helicone.** Per-session traces of tokens and cost. Idea: every job writes a cost
    trace, so a post-mortem ("where did 459K go?") is one command instead of an investigation.

## Choosing who does what

14. **RimWorld work-priorities grid.** Rows are colonists, columns are job types, each cell 1-4 or
    blank; all priority-1 work gets done first. Warning from the game: put Hauling at 1 and a colonist
    hauls everything across the map first. Idea: Phil's grid of seats × work types replaces the long
    roles text in TEAM.md; one glance, one tap to change.
15. **LLM routers (Not Diamond, RouteLLM, OpenRouter auto).** A small model predicts the best model
    for each prompt from past results. Idea: the team-engine scoreboard (Juniper-16) becomes the
    training data for Mega Zword's own router: who actually did well at which kind of job.
16. **BOINC volunteer computing.** Work units go to several computers; a quorum must agree; some
    projects check a computer less often as it proves reliable. Idea: free models' output gets a
    second check at a rate tied to that model's own error rate; trusted sources are spot-checked less.

## Reading less

17. **Aider's repo map.** A ranked map of the whole repo's key functions, trimmed to about 1k tokens,
    instead of reading files. Idea: give free models a repo map instead of file dumps.
18. **Conductor, Claude Squad, Vibe Kanban.** Parallel coding agents, each in its own git worktree,
    with a dashboard and a review step before merge; Vibe Kanban ties each card to one worktree.
    Idea: our seat worktrees already do this; borrow the card-per-worktree board and review-before-merge.

## Beacon-17's top five to build first

1. PagerDuty-style escalation (2): fixes unanswered posts.
2. Temporal-style step cache (10): biggest token saver for failed jobs.
3. Erlang restart limit (11): stops runaway retries.
4. Ham-net roll sheet (1): makes Broadcast results visible at a glance.
5. RimWorld grid (14): Phil sets who does what without reading rules.

## Sources
- Ham nets: https://hamradio.arc.nasa.gov/index.php/net-control-script , https://nyc-arecs.org/script.html
- PagerDuty-style escalation: https://dev.to/jensonhirst/on-call-schedules-and-escalation-policies-explained-2026-5aha , https://handbook.gitlab.com/handbook/security/customer-support-operations/docs/pagerduty
- Zello: https://zello.com/product/push-to-talk-app/
- Flight strips: https://www.faa.gov/air_traffic/publications/atpubs/ATC_html/chap2_section_3.html , https://skybrary.aero/index.php/Flight_Progress_Strips
- I-PASS: https://www.fiercehealthcare.com/healthcare/handoff-program-cuts-medical-errors-by-40 , https://intermountainhealthcare.org/news/2014/12/multicenter-patientsafety-study-reduces-medical-error-injuries-by-30
- KDS: https://stovepos.com/products/kds
- Andon / kanban: https://mag.toyota.co.uk/andon-toyota-production-system/ , https://www.informs-sim.org/wsc01papers/122.PDF
- Powerwall: https://www.tesla.com/support/energy/learn/powerwall/time-based-control
- Spot + Karpenter: https://perfectscale.io/blog/karpenter-consolidation-spot-instance-termination
- Temporal: https://docs.temporal.io/encyclopedia/event-history/
- Erlang supervisors: https://www.erlang.org/docs/25/design_principles/sup_princ.html
- LiteLLM: https://docs.litellm.ai/docs/routing
- Langfuse / Helicone: https://www.pkgpulse.com/guides/langfuse-vs-langsmith-vs-helicone-llm-observability-2026
- RimWorld: https://rimworldwiki.com/wiki/Work
- LLM routers: https://holori.com/best-llm-routers/
- BOINC: https://einsteinathome.org/content/far-far-too-much-redundancy?page=1
- Aider repo map: https://aider.chat/2023/10/22/repomap.html
- Parallel agent tools: https://agentsroom.dev/blog/best-multi-agent-coding-tools
