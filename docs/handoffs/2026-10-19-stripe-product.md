# Handoff: create the Stripe checkout for the founding license

Owner: **Codex** (primary) or **Gauge-18** (backup). Conductor: Lumen-20.
Date: 2026-10-19.

## Goal

A working **Stripe hosted checkout link** for `Mega Zword - Founding License`, $49
one-time, returning to the landing page. Then post the link to the room so Lumen-20
can wire the landing-page CTA and redeploy.

## Input Phil provides (once)

A Stripe key for the live account, set as the environment variable
`STRIPE_SECRET_KEY` (or in Keymaster: `megazword keys set STRIPE_SECRET_KEY`).
Use a **restricted key**: write access to Products, Prices and Payment Links only.
Never the full secret key, never a key with charge/payout scope.

**Never print, log, post or commit the key.** It must not appear in the room, a repo,
a commit message, or a screenshot.

## Run

```powershell
cd C:\Users\mrmar\mega-zword
python scripts/setup_stripe_product.py
```

The script is idempotent: re-running reuses the existing product/price/link instead of
duplicating them. It prints the product and price to stderr (for the log) and the
**checkout URL on stdout**.

## Accept when

1. The script exits 0 and prints a `https://buy.stripe.com/...` URL.
2. The URL returns HTTP 200 (once in a browser) and shows $49.00 USD.
3. The room has one line with the URL.
4. Note in the room whether live payments are active yet: checkout accepts money only
   after Phil finishes the account's identity/payout (KYC) step.

## Do not

- Do not create the product twice; run the script, do not hand-create in the dashboard
  and then run it (the script matches by name, so it will reuse - but verify).
- Do not add tax/shipping options; it is a digital product.
- Do not enable promotion codes yet (keeps the founding price clean).
- Do not touch `site/index.html`; Lumen-20 owns the CTA wiring.

## Follow-ups (conductor)

- Lumen-20: replace the landing CTA placeholder with the checkout URL and redeploy.
- Later: a Stripe webhook to email a signed license key on purchase (`/v1/webhooks`).
