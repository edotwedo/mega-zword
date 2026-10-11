"""End-to-end smoke test: the real `megazword` against fake AI CLIs.

Runs every main feature (backends, init, run, escalation, retry, -m, memory,
usage, chat, dashboard API) in a throwaway home folder with fake claude /
codex / grok programs first on PATH. No paid calls, no network, and nothing
touches your real ~/.megazword or CLI logins.

    python scripts/smoke.py          (or scripts/smoke.ps1)

Exits 0 if every check passes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FAKES = REPO / "scripts" / "fake_cli"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))


def make_env(tmp: Path) -> dict:
    env = dict(os.environ)
    home = tmp / "home"
    home.mkdir()
    env.update({
        "PATH": str(FAKES) + os.pathsep + env.get("PATH", ""),
        "MZ_SMOKE_PYTHON": sys.executable,
        "MEGAZWORD_HOME": str(tmp / "mz"),
        # Refused instantly: the rater falls back to its rule, no local model.
        "MEGAZWORD_OLLAMA_URL": "http://127.0.0.1:9",
        # No CLI logins or logs here, so usage meters can't reach the network.
        "USERPROFILE": str(home), "HOME": str(home),
        "PYTHONPATH": str(REPO / "src"),
        "PYTHONIOENCODING": "utf-8",
    })
    return env


def mz(env: dict, cwd: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "megazword.cli", *args], input=stdin,
                          capture_output=True, text=True, encoding="utf-8", env=env,
                          cwd=cwd, timeout=120)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(url: str, body: dict | None = None, token: str = "") -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "X-MZ-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def dashboard_checks(env: dict, cwd: Path) -> None:
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "megazword.cli", "dashboard",
                             "--port", str(port), "--no-browser", "-p", "smoke"],
                            env=env, cwd=cwd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        page = ""
        for _ in range(50):
            try:
                _, page = http(base + "/")
                break
            except OSError:
                time.sleep(0.2)
        m = re.search(r'const TOKEN = "([^"]+)"', page)
        check("dashboard serves the page with a token", bool(m))
        if not m:
            return
        token = m.group(1)
        code, body = http(base + "/api/state")
        state = json.loads(body) if code == 200 else {}
        check("dashboard /api/state", code == 200 and state.get("project") == "smoke", body[:200])
        code, _ = http(base + "/api/run", {"prompt": "hi"}, token="wrong")
        check("dashboard rejects a bad token", code == 403)
        code, body = http(base + "/api/run", {"prompt": "dashboard hello"}, token=token)
        job = json.loads(body).get("job") if code == 200 else None
        view = {}
        for _ in range(100):
            if not job:
                break
            _, body = http(f"{base}/api/job/{job}")
            view = json.loads(body)
            if view.get("done"):
                break
            time.sleep(0.2)
        check("dashboard run job finishes with an answer",
              view.get("code") == 0 and "ok: dashboard hello" in view.get("out", ""),
              str(view)[:300])
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="megazword-smoke-"))
    work = tmp / "project"
    work.mkdir()
    env = make_env(tmp)
    try:
        r = mz(env, work, "backends")
        check("backends finds all three fakes",
              r.returncode == 0 and r.stdout.count("installed") == 3, r.stdout + r.stderr)

        r = mz(env, work, "init")
        check("init writes a config", r.returncode == 0 and (tmp / "mz" / "config.toml").exists(),
              r.stderr)

        r = mz(env, work, "run", "hello there")
        check("run auto-picks and answers", r.returncode == 0 and "ok: hello there" in r.stdout,
              r.stdout + r.stderr)
        first = re.search(r"\[fake (\w+)\]", r.stdout)

        r = mz(env, work, "run", "REFUSE-grok REFUSE-codex please answer")
        check("refusals escalate to the next AI",
              r.returncode == 0 and "[fake claude]" in r.stdout and "rejected" in r.stderr,
              r.stdout + r.stderr)

        mz(env, work, "run", "pick me", "-m", "grok")
        r = mz(env, work, "retry")
        check("retry moves to a different AI",
              r.returncode == 0 and "[fake grok]" not in r.stdout and "ok:" in r.stdout,
              r.stdout + r.stderr)

        r = mz(env, work, "run", "forced", "-m", "codex")
        check("-m forces an AI (codex reads its -o file)",
              r.returncode == 0 and "[fake codex] ok: forced" in r.stdout, r.stdout + r.stderr)

        mz(env, work, "decide", "Smoke tests stay free")
        mz(env, work, "note", "a note")
        r = mz(env, work, "history")
        check("decide / note / history", "Smoke tests stay free" in r.stdout
              and "a note" in r.stdout and "done" in r.stdout, r.stdout + r.stderr)

        r = mz(env, work, "run", "with memory", "--context", "-m", "claude")
        check("--context sends project memory", "ok:" in r.stdout and r.returncode == 0,
              r.stdout + r.stderr)

        mz(env, work, "out", "grok", "--until", "1d")
        r = mz(env, work, "run", "while grok is out")
        check("out: marked-out AI is skipped",
              r.returncode == 0 and "[fake grok]" not in r.stdout and "ok:" in r.stdout,
              r.stdout + r.stderr)
        mz(env, work, "out", "grok", "--clear")
        r = mz(env, work, "out")
        check("out --clear brings it back", "no AI is marked out" in r.stdout, r.stdout + r.stderr)

        r = mz(env, work, "usage")
        check("usage runs without real meters", r.returncode == 0 and "Mega Zword runs" in r.stdout,
              r.stdout + r.stderr)

        r = mz(env, work, "chat", stdin="first message\nsecond message\n/usage\n/quit\n")
        check("chat answers and quits cleanly",
              r.returncode == 0 and r.stdout.count("ok:") >= 2 and "Traceback" not in r.stderr,
              r.stdout[-400:] + r.stderr[-400:])

        dashboard_checks(env, work)

        check("first auto run went to a fake AI", bool(first))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
