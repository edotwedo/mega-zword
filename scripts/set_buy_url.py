"""Wire the Stripe payment link into the landing page and redeploy it.

Usage:
    python scripts/set_buy_url.py https://buy.stripe.com/xxxxxxxx
    python scripts/set_buy_url.py https://buy.stripe.com/xxxxxxxx --no-deploy

Sets the single `var BUY = "...";` line in site/index.html - every [data-buy]
button points at it - then deploys the Pages site. Safe to re-run with a new URL.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "site" / "index.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="the https://buy.stripe.com/... payment link")
    parser.add_argument("--no-deploy", action="store_true", help="edit only, do not deploy")
    args = parser.parse_args(argv)
    if not args.url.startswith("https://buy.stripe.com/"):
        sys.exit("expected a https://buy.stripe.com/... URL")
    text = SITE.read_text(encoding="utf-8")
    new, count = re.subn(r'var BUY = "[^"]*";', f'var BUY = "{args.url}";', text)
    if count != 1:
        sys.exit(f"expected exactly one BUY line, found {count}")
    SITE.write_text(new, encoding="utf-8")
    print(f"BUY set to {args.url}")
    if not args.no_deploy:
        subprocess.run(["npx", "--yes", "wrangler@4", "pages", "deploy", "site",
                        "--project-name=megazword", "--branch=main"],
                       cwd=str(ROOT), shell=True, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
