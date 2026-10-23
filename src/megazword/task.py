"""Shared task leases (M2/P3): explicit heartbeats, no scheduler or model calls."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .filelock import locked, write_atomic

LEASE = timedelta(minutes=30)
HOT_FILES = {"src/megazword/cli.py", "docs/status.md", "docs/hive-roster.md"}


class TaskError(ValueError):
    pass


def _git(repo, *args):
    env = dict(os.environ)
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR",
                 "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        env.pop(name, None)
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          encoding="utf-8", errors="replace", timeout=10, env=env)
    if proc.returncode:
        raise TaskError("git operation failed: " + " ".join(args[:2]))
    return proc.stdout.rstrip("\r\n")


def _root(repo):
    return Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()


def _now(now):
    value = now or datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _owner(seat):
    value = (seat or os.environ.get("MEGAZWORD_SEAT") or "").strip()
    if not value:
        raise TaskError("set MEGAZWORD_SEAT or pass --seat")
    return value


def _files(root, files):
    result = set()
    for raw in files:
        path = (root / str(raw).replace("\\", "/")).resolve()
        if not path.is_relative_to(root) or path == root or path.is_dir():
            raise TaskError("task files must name files inside this worktree")
        relative = path.relative_to(root).as_posix()
        if relative.casefold() == ".git" or relative.casefold().startswith(".git/"):
            raise TaskError("Git metadata cannot be task files")
        result.add(relative.casefold() if os.name == "nt" else relative)
    return sorted(result)


@contextmanager
def _registry(root):
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    path = common / "megazword-tasks.json"
    with locked(path, timeout=2) as acquired:
        if not acquired:
            raise TaskError("task registry busy; no operation performed")
        try:
            state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"version": 1, "tasks": {}}
            if state.get("version") != 1 or not isinstance(state.get("tasks"), dict):
                raise ValueError("bad task registry")
        except (ValueError, TypeError, AttributeError) as exc:
            raise TaskError("task registry invalid; refusing to ignore locks") from exc
        before = json.dumps(state, sort_keys=True)
        yield state["tasks"]
        if json.dumps(state, sort_keys=True) != before:
            write_atomic(path, json.dumps(state, indent=2) + "\n")


def _active(task, now):
    try:
        if task["state"] != "open":
            return False
        expires = datetime.fromisoformat(task["expires_at"])
        return now < _now(expires)
    except (KeyError, TypeError, ValueError) as exc:
        raise TaskError("task lease invalid; refusing to ignore locks") from exc


def _conflicts(tasks, files, now, own=None):
    wanted = {f for f in files if f.casefold() not in HOT_FILES}
    return [(t["id"], t["seat"], sorted(wanted & set(t["files"])))
            for t in tasks.values() if t["id"] != own and _active(t, now)
            and wanted & set(t["files"])]


def new(repo, title, files, *, seat=None, now=None):
    root, now, owner = _root(repo), _now(now), _owner(seat)
    if not title.strip():
        raise TaskError("task needs a title")
    paths = _files(root, files)
    if not paths:
        raise TaskError("task needs at least one file")
    with _registry(root) as tasks:
        conflicts = _conflicts(tasks, paths, now)
        if conflicts:
            raise TaskError(f"files held by {conflicts[0][1]} task {conflicts[0][0]}: {', '.join(conflicts[0][2])}")
        task_id = uuid.uuid4().hex[:12]
        branch = "task/" + task_id
        _git(root, "branch", branch, "HEAD")  # Allocate without switching anyone's worktree.
        task = {"id": task_id, "title": title.strip(), "seat": owner, "branch": branch,
                "files": [f for f in paths if f.casefold() not in HOT_FILES],
                "state": "open", "tick": 0, "heartbeat_at": now.isoformat(),
                "expires_at": (now + LEASE).isoformat()}
        tasks[task_id] = task
    return task


def update(repo, task_id, *, seat=None, now=None, release=False, files=()):
    root, now, owner = _root(repo), _now(now), _owner(seat)
    paths = _files(root, files)
    with _registry(root) as tasks:
        if task_id not in tasks:
            raise TaskError("unknown task")
        task = tasks[task_id]
        if task["seat"].casefold() != owner.casefold():
            raise TaskError("only the owning seat can renew or release this task")
        if release:
            task["state"] = "released"  # Relinquishing locks does not declare work done (M3).
        else:
            if not _active(task, now):
                raise TaskError("task lease expired or released; create a new task")
            if now < datetime.fromisoformat(task["heartbeat_at"]):
                raise TaskError("heartbeat time moved backwards")
            conflicts = _conflicts(tasks, paths, now, own=task_id)
            if conflicts:
                raise TaskError(f"additional files held by task {conflicts[0][0]}")
            task["files"] = sorted(set(task["files"]) | {p for p in paths if p.casefold() not in HOT_FILES})
            task.update(tick=task["tick"] + 1, heartbeat_at=now.isoformat(), expires_at=(now + LEASE).isoformat())
    return task


def check_push(lines, *, repo=".", now=None):
    """Return conflicts for Git pre-push's refs, including new branch pushes."""
    root, now = _root(repo), _now(now)
    conflicts = []
    with _registry(root) as tasks:
        if not any(_active(t, now) for t in tasks.values()):
            return []
        for line in lines.splitlines():
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 4:
                raise TaskError("invalid pre-push ref input")
            local_ref, local_sha, _remote_ref, remote_sha = parts
            if local_ref == "(delete)" or set(local_sha) == {"0"}:
                continue
            if set(remote_sha) != {"0"}:
                base = remote_sha
            else:
                base = _git(root, "merge-base", "origin/main", local_sha)
            changed = _git(root, "diff", "--no-renames", "--name-only", "-z", base, local_sha)
            paths = [p.casefold() if os.name == "nt" else p for p in changed.split("\0") if p]
            owner = (os.environ.get("MEGAZWORD_SEAT") or "").casefold()
            own = next((t["id"] for t in tasks.values()
                        if local_ref == "refs/heads/" + t["branch"] and t["seat"].casefold() == owner), None)
            conflicts.extend(_conflicts(tasks, paths, now, own=own))
    return conflicts


def pre_push():
    try:
        conflicts = check_push(sys.stdin.read())
        for task_id, seat, files in conflicts:
            print(f"task gate: push blocked - {seat} task {task_id} holds {', '.join(files)}")
        return 1 if conflicts else 0
    except (TaskError, OSError, subprocess.SubprocessError) as exc:
        print(f"task gate: push blocked - {exc}")
        return 1


def command(args):
    try:
        if args.action == "new":
            result = new(Path.cwd(), args.title, args.files, seat=args.seat)
        else:
            result = update(Path.cwd(), args.id, seat=args.seat, release=args.action == "release",
                            files=getattr(args, "files", ()))
        print(json.dumps(result))
        return 0
    except (TaskError, OSError, subprocess.SubprocessError) as exc:
        print(f"task: {exc}")
        return 1


def add_parser(sub):
    parser = sub.add_parser("task", help="allocate task branches and shared expiring file leases")
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("new", help="allocate a task and branch, without switching worktrees")
    create.add_argument("--title", required=True)
    create.add_argument("--files", nargs="+", required=True)
    for action in ("beat", "release"):
        child = actions.add_parser(action, help="renew/add files" if action == "beat" else "relinquish locks, not declare done")
        child.add_argument("id")
        if action == "beat":
            child.add_argument("--files", nargs="*", default=[])
        child.add_argument("--seat")
    create.add_argument("--seat")
