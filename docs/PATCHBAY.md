# Visual AI patch bay

Run `megazword dashboard --port 8791 --no-browser`, then open
`http://localhost:8791/patchbay`. Run from the patch-bay branch until it is merged.
No Hive timer or autonomous polling of models is enabled. Browser refresh reads
state; only sending a message or resuming queued work starts delivery.

Add agent instances, choose configured providers, and give each a role. Every
instance has its own persisted conversation/tab. Connect an output to an input
by dragging between ports or clicking output then input. Drag headers to arrange
modules. Select an agent, write a request, choose a total turn budget, and send.
Its answer goes to every wired destination automatically. A reviewer can be wired
back to a writer; the whole run stops at its budget (maximum 12 calls).

Add a local file hub with a directory and one relative UTF-8 text-file path.
Hub → agent supplies the run's initial file snapshot. Agent → hub produces an
artifact. Review its before/after content and explicitly replace the file. Tell
the final agent to return the complete file contents, without Markdown fences.
Artifacts replace the whole file. A changed file blocks applying an old artifact.
Hub output is snapshot context, not an additional autonomous forwarding step.

Delivery state and wiring live in `patchbay.sqlite3` under the existing Mega Zword
home. The database is private to its owner. Calls run serially, with a cross-process
worker lock. Pause lets an active call finish and stops the next one. Resume drains
remaining queued messages; failed calls and interrupted calls are not retried.
Clear queue cancels pending work so wiring can change. Restart does not start
models. There is deliberately no automatic replay of a call whose result was lost.

Provider instances share the configured account's allowance. Known five-hour
meters stop at 10% remaining and weekly meters at 5%; other known meters stop at
exhaustion. Unknown/stale usage is labeled, not turned into a fabricated allotment.
Provider errors pause delivery. Turn budgets are a second bound, not a cost or
context-window estimate. Existing provider adapters own authentication and session
handling; the patch bay does not copy credentials.

This first slice supports local text-file hubs up to 64 KB and the existing
configured backend adapters. It does not yet browse whole directory trees, operate
GitHub resources, publish websites, edit cloud documents, or switch among multiple
accounts of one provider. Those need resource/account adapters behind these same
ports. There is no promise of parallel model execution: multiple instances are
independent conversations, and this initial dispatcher runs one turn at a time.

The first acceptance path is **Writer → Reviewer → Document**, with
**Document → Writer** supplying context. The delivery log shows each handoff and
the final artifact; an owner-applied artifact is the observable completed outcome.
