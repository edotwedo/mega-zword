"""A stand-in for the claude / codex / grok / gemini CLIs, used by scripts/smoke.py.

Answers instantly, costs nothing. Put "REFUSE-<name>" in a prompt to make
that fake AI refuse, or "SLEEP-<name>" to make it hang (tests timeouts).
"""

import sys
for stream in (sys.stdin, sys.stdout, sys.stderr):
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")
import json
import os
from pathlib import Path
import uuid


def main() -> int:
    name, args = sys.argv[1], sys.argv[2:]
    if args[:1] == ["app-server"]:  # no fake Codex app server: Mega Zword falls back to logs
        return 1
    if "--version" in args:
        print(f"fake-{name} 0.0")
        return 0
    if name == "gemini" and args != ["--approval-mode", "yolo", "--output-format", "text"]:
        print("fake Gemini requires full-access flags and stdin input", file=sys.stderr)
        return 42
    if name == "agy":  # Antigravity CLI: the prompt is the value of -p
        if args[:4] == ["-p", "/usage", "--output-format", "json"]:
            print('{"status":"SUCCESS","command":{"name":"usage","data":{"groups":[{"name":'
                  '"Gemini Models","buckets":[{"id":"g","window":"weekly",'
                  '"remaining_fraction":0.9,"reset_time":"2030-01-01T00:00:00Z"}]}]}}}')
            return 0
        if args[:1] != ["--dangerously-skip-permissions"] or args[-2:-1] != ["-p"]:
            print("fake agy requires full access and the prompt as the -p value", file=sys.stderr)
            return 42
        name, prompt = "gemini", args[-1]
    elif "--prompt-file" in args:
        with open(args[args.index("--prompt-file") + 1], encoding="utf-8") as f:
            prompt = f.read()
    else:
        prompt = sys.stdin.read()
    session = ""
    structured = "--json" in args or ("--output-format" in args and
                 args[args.index("--output-format") + 1] == "json")
    session_mode = structured or "--session-id" in args or "--resume" in args or "resume" in args
    if session_mode:
        flag = "--resume" if "--resume" in args else "resume" if "resume" in args else None
        session = args[args.index(flag) + 1] if flag else (
            args[args.index("--session-id") + 1] if "--session-id" in args else str(uuid.uuid4()))
        directory = Path(os.environ["MEGAZWORD_HOME"]) / "fake-sessions"
        directory.mkdir(parents=True, exist_ok=True)
        record = directory / (str(uuid.UUID(session)) + ".json")
        if flag and not record.exists():
            print("Session not found", file=sys.stderr)
            return 1
        saved = json.loads(record.read_text()) if record.exists() else {"prompts": []}
        saved["prompts"].append(prompt)
        record.write_text(json.dumps(saved), encoding="utf-8")
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
        print(json.dumps({"type": "thread.started", "thread_id": session})
              if structured else "codex progress noise")
    elif name == "claude" and structured:
        print(json.dumps({"result": answer, "session_id": session, "is_error": False}))
    else:
        print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
