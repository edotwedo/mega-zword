"""A stand-in for the claude / codex / grok / gemini CLIs, used by scripts/smoke.py.

Answers instantly, costs nothing. Put "REFUSE-<name>" in a prompt to make
that fake AI refuse, or "SLEEP-<name>" to make it hang (tests timeouts).
"""

import sys


def main() -> int:
    name, args = sys.argv[1], sys.argv[2:]
    if "--version" in args:
        print(f"fake-{name} 0.0")
        return 0
    if name == "gemini" and args != ["--approval-mode", "plan", "--output-format", "text"]:
        print("fake Gemini requires read-only flags and stdin input", file=sys.stderr)
        return 42
    if "--prompt-file" in args:
        with open(args[args.index("--prompt-file") + 1], encoding="utf-8") as f:
            prompt = f.read()
    else:
        prompt = sys.stdin.read()
    if f"AUTH-{name}" in prompt:  # simulate an expired login
        print("Error: Not logged in. Please run the login command.", file=sys.stderr)
        return 1
    if f"NET-{name}" in prompt:  # simulate no internet
        print("Error: getaddrinfo ENOTFOUND api.example.com", file=sys.stderr)
        return 1
    if f"LIMIT-{name}" in prompt:  # simulate an out-of-usage error (Codex wording)
        print("ERROR: You’ve hit your usage limit. Upgrade to Pro "
              "(https://chatgpt.com/explore/pro) or try again at 2:39 AM.", file=sys.stderr)
        return 1
    if f"SLEEP-{name}" in prompt:  # simulate a hung AI
        import time
        time.sleep(60)
    last = prompt.strip().splitlines()[-1] if prompt.strip() else ""
    answer = "I can't." if f"REFUSE-{name}" in prompt else f"[fake {name}] ok: {last[:60]}"
    if "-o" in args:  # codex writes its final message to a file
        with open(args[args.index("-o") + 1], "w", encoding="utf-8") as f:
            f.write(answer)
        print("codex progress noise")
    else:
        print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
