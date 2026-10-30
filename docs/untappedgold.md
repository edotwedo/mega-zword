# Untapped Gold: The Aggregator Engine & The Taxi Stand Architecture

**Author:** Phil Marler & MIKE-54 (Antigravity)  
**Date:** 2026-10-30  
**Context:** Paradigm shift for `mega-zword` routing, fault recovery, and fleet maintenance.

---

## 1. The Core Ideology: Aggregator over Container

The entire tech ecosystem spends billions trying to build the "perfect container"—Docker, hermetic runtimes, closed app stores, and complex agent frameworks (LangGraph, CrewAI). 

A **container** is defensive: it puts walls around state and assumes the value lives inside. But when LLMs and endpoints are volatile commodities shifting weekly (price changes, rate limits, Cloudflare TLS blocks, token expirations, sudden 401s), a container is just a prison for a commodity. Upstream breakage breaks the container.

An **aggregator (a market)** does the opposite:
- It owns the **demand** (user intent) and commoditizes all suppliers beneath it.
- It values **liquidity over isolation**: who has the fastest clearance, lowest cost, and an open rate limit right now?
- When a provider fails, it isn't a runtime crash—it's a supply-side signal to re-route.

---

## 2. The Implementation: The Taxi Stand Dispatcher

Currently, `mega-zword` operates on an ordered fallback ladder: a prompt looks up a static tuple (`easy`, `medium`, `hard` in `config.py`) and steps down sequentially until an API answers.

The **Taxi Stand** replaces hardcoded ladders with a dynamic priority dispatcher:

1. **The Curb (Real-Time Health & Tank Monitoring):**
   - Track three metrics per backend:
     - Availability / Liveness (healthy vs failing).
     - Tank level (remaining 5-hour / weekly / RPM headroom).
     - Unit cost (zero-token free tier vs prepaid flat CLI vs metered paid).
2. **Next Cab Up (`queue.pop`):**
   - Tasks enter as intents (required capability: reasoning depth, tool support, or simple text).
   - The dispatcher assigns the job to the first qualified cab waiting at the curb with a full tank and a clean record.
3. **Instant Re-route:**
   - If a model throws a 401, 429, or corrupt output, the passenger is immediately moved to the next waiting cab without blocking the user.

---

## 3. The Resolution Loop: Never Just Junk Trashed Results

A critical flaw in naive failover is dropping failures on the floor or letting broken models keep picking up fares. Failures are actionable diagnostic data.

### A. The Incident Box (Dead-Letter Queue)
- Every failed or malformed response is captured with its full prompt, HTTP status, response headers, and raw output into `.megazword/incidents/<id>.json`.
- The user is re-routed instantly, but the crime scene is preserved for analysis.

### B. The 3-Strike Lemon Law (Quarantine)
- **Strike 1 (Transient glitch or network timeout):** 5-minute cool-off.
- **Strike 3 (Persistent 401, 404, or corrupt syntax):** Immediate **Quarantine**.
- Quarantined backends are pulled off the road so they stop burning retries, slowing runs, or contaminating logs.

### C. Automated Resolution Routing
Incidents are categorized for triage rather than ignored:
1. **Human / Credential Fix:**
   - Token expired (e.g. `cmdc` 48-hour expiration) or payment required (HTTP 402).
   - Generates an actionable notification: *"cmdc auth expired. Run cmdc login to restore to fleet."*
2. **Provider Dead / Deprecated:**
   - Model removed upstream or keyless access closed (e.g. Pollinations moving behind paywall).
   - Auto-files an eviction ballot in the Hive room: *"Model X failed 5 consecutive runs with 404/410. Propose eviction from fleet."*
3. **Capability Mismatch:**
   - Model fails schema or leaks syntax (e.g. DeepSeek leaking DSML tool tags).
   - Downgrades the model's capability score to plain text/classification tasks only.

---

## Summary
Don't build a prison for LLMs. Build the dispatch clearinghouse that extracts the maximum work per dollar and token, keeps broken models off the road, and routes around failure automatically.
