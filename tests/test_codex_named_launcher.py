import concurrent.futures
import importlib.util
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("hive_launcher", Path(__file__).resolve().parents[1] / "scripts/codex_named_launcher.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_launch_invariants():
    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "names.sqlite"
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            names = list(pool.map(lambda i: m.designation(str(i), database=db), range(24)))
        assert len(set(names)) == 24
        assert m.designation("0", database=db) == names[0]
        assert m.designation("existing", existing="Alder-16", database=db) == "Alder-16"
        with patch.dict(os.environ, {"MEGAZWORD_SEAT": "wrong-parent", "MEGAZWORD_SESSION": "wrong-id", "CODEX_THREAD_ID": "wrong-id"}):
            env = m.resume_environment(["resume", "existing"], database=db)
            assert env["MEGAZWORD_SEAT"] == "Alder-16"
            assert env["MEGAZWORD_SESSION"] == "existing"
            assert "CODEX_THREAD_ID" not in env
        assert m.invocation(["--model", "chosen", "a task"])[0] == "new"
        assert m.invocation(["-c", 'some_key="value"', "--search"])[0] == "new"
        for command in ("exec", "app-server", "features", "mcp", "queue"):
            assert m.invocation([command, "anything"])[0] == "pass"
        assert m.invocation(["resume", "existing"])[0] == "resume"
        assert m.invocation(["--help"])[0] == "pass"
        calls = []
        with patch.object(m, "native_binary", return_value="native.exe"), patch.object(m, "prepare", return_value=("new-id", "Briar-17")), patch.object(m.subprocess, "call", side_effect=lambda args, **kw: calls.append((args, kw)) or 0):
            assert m.main(["--model", "chosen", "text with spaces & quotes"]) == 0
        assert calls[0][0] == ["native.exe", "resume", "new-id", "--model", "chosen", "text with spaces & quotes"]
        assert calls[0][1]["env"]["MEGAZWORD_SEAT"] == "Briar-17"
        assert calls[0][1]["env"]["MEGAZWORD_SESSION"] == "new-id"
        with patch.object(m, "native_binary", return_value="native.exe"), patch.object(m, "prepare", side_effect=AssertionError("must not rename resumed session")), patch.object(m, "resume_environment", return_value={}), patch.object(m.subprocess, "call", return_value=0):
            assert m.main(["resume", "existing"]) == 0
    print("PASS: 24 concurrent unique names, stable resume identity, native command pass-through, argument/env preservation")


if __name__ == "__main__":
    test_launch_invariants()
