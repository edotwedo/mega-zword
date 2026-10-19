"""Create the Mega Zword founding-license product, price and hosted checkout link.

Idempotent: safe to re-run. It looks for the product/price/payment link by name and
reuses what exists instead of creating duplicates.

Run (once Phil has set STRIPE_SECRET_KEY in the environment or Keymaster):

    python scripts/setup_stripe_product.py
    python scripts/setup_stripe_product.py --name "Mega Zword Pro" --amount 9900

It prints the checkout URL and nothing else. It never prints the secret key.

The key must be a Stripe key for the account Phil chose. Prefer a **restricted key**
with write access to Products, Prices and Payment Links only - not the full secret key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.stripe.com/v1"
DEFAULT_NAME = "Mega Zword - Founding License"
DEFAULT_AMOUNT = 4900  # $49.00 in cents
SUCCESS_URL = "https://megazword.pages.dev/?thanks=1"


def _key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        sys.exit("STRIPE_SECRET_KEY is not set (environment or Keymaster). Aborting.")
    return key


def _call(key: str, method: str, path: str, data: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data, doseq=True).encode() if data else None
    request = urllib.request.Request(API + path, data=body, method=method)
    request.add_header("Authorization", "Bearer " + key)
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    if data:  # same request = same result, even if this script is re-run mid-flight
        request.add_header("Idempotency-Key", "mz-" + path.strip("/").replace("/", "-") + "-"
                           + str(sorted(data.items()))[:120])
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        sys.exit(f"Stripe {method} {path} failed: HTTP {exc.code}: {detail[:400]}")


def _find(key: str, path: str, field: str, wanted: str) -> dict | None:
    page = _call(key, "GET", path + "?limit=100")
    for row in page.get("data", []):
        if str(row.get(field, "")).strip().lower() == wanted.strip().lower():
            return row
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default=DEFAULT_NAME, help="product + link name")
    parser.add_argument("--amount", type=int, default=DEFAULT_AMOUNT, help="price in cents")
    parser.add_argument("--success-url", default=SUCCESS_URL, help="where checkout returns")
    args = parser.parse_args(argv)
    key = _key()

    product = _find(key, "/products", "name", args.name)
    if product is None:
        product = _call(key, "POST", "/products", {
            "name": args.name,
            "description": "One-time lifetime license for Mega Zword (Apache-2.0 core).",
        })
    print(f"product: {product['id']}", file=sys.stderr)

    prices = _call(key, "GET", f"/prices?limit=100&product={product['id']}")
    price = next((p for p in prices.get("data", [])
                  if p.get("unit_amount") == args.amount and p.get("type") == "one_time"), None)
    if price is None:
        price = _call(key, "POST", "/prices", {
            "product": product["id"],
            "unit_amount": args.amount,
            "currency": "usd",
        })
    print(f"price: {price['id']} ({args.amount / 100:.2f} USD)", file=sys.stderr)

    links = _call(key, "GET", f"/payment_links?limit=100&active=true")
    link = next((row for row in links.get("data", [])
                 if row.get("metadata", {}).get("megazword") == args.name), None)
    if link is None:
        link = _call(key, "POST", "/payment_links", {
            "line_items[0][price]": price["id"],
            "line_items[0][quantity]": 1,
            "after_completion[type]": "redirect",
            "after_completion[redirect][url]": args.success_url,
            "metadata[megazword]": args.name,
        })
    print(link["url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
