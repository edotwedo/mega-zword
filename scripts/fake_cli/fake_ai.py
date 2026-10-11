"""A stand-in for the claude / codex / grok CLIs, used by scripts/smoke.py.

Answers instantly, costs nothing. Put "REFUSE-<name>" in a prompt to make
that fake AI refuse, which exercises escalation.
"""

import sys


def main() -> int:
    name, args = sys.argv[1], sys.argv[2:]
    if "--version" in args:
        print(f"fake-{name} 0.0")
        return 0
    if "--prompt-file" in args:
        with open(args[args.index("--prompt-file") + 1], encoding="utf-8") as f:
            prompt = f.read()
    else:
        prompt = sys.stdin.read()
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
