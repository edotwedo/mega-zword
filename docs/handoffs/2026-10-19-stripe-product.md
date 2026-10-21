# Handoff: create the Stripe checkout for the founding license

Owner: **Codex** (primary) or **Gauge-18** (backup). Conductor: Lumen-20.
Date: 2026-10-19.

> **BLOCKED 2026-10-20 — do not re-run this as if it were unblocked.** Phil's Stripe
> account has a passkey registered as its only two-step method, and the credential is on
> no device he has: the dashboard offers only "phone" or "USB security key", the phone QR
> answers **"No keys were found"**, Chrome in his profile is not signed into any Google
> account, and no FIDO key has ever been seen on this PC. Every action that needs step-up
> is therefore locked. Only **Stripe support can remove that second factor** (email
> identity check). Until they do, there is no key, so this script cannot run.
>
> Consequence for the plan: the payment rail is not the product. The landing page takes any
> checkout URL through the single `var BUY` constant in `site/index.html`, and the script's
> only job was a product named "Mega Zword - Founding License" at $49.00 with a hosted
> checkout — the same thing a Gumroad or Lemon Squeezy product does from a form, with no
> API key and no step-up. Route around the lock; do not wait on it.
>
> **Status 2026-10-20: the support ticket has been SENT by Phil.** So this is waiting on
> Stripe, not on him. Do not ask him to raise it again, and do not treat the missing key as
> his outstanding action. Interim rail: Gumroad (a product form, no API key, no step-up);
> note Lemon Squeezy is Stripe-owned, so its onboarding runs into the same account wall.

## Goal

A working **Stripe hosted checkout link** for `Mega Zword - Founding License`, $49
one-time, returning to the landing page. Then post the link to the room so Lumen-20
can wire the landing-page CTA and redeploy.

## Input Phil provides (once)

A Stripe key for the live account, set as the environment variable
`STRIPE_SECRET_KEY` in the shell that runs the script.

**Environment variable only.** `megazword keys` takes `show` and `move`, not `set`, and
Stripe is not one of its known providers, so there is no Keymaster path today. (This
handoff previously said `megazword keys set STRIPE_SECRET_KEY`; that command does not
exist, and running it just errors.) The key is read from `os.environ` at line 34.

Use a **restricted key**: write access to Products, Prices and Payment Links only.
Never the full secret key, never a key with charge/payout scope. In the current Stripe
UI these live under API keys -> the **Access policies** tab; "restricted" no longer
appears as a label, and "Create a secret key" makes the broad key instead.

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
