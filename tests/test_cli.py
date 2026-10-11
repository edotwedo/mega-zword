"""Tests use fake backends so they never spend paid usage."""

from dataclasses import dataclass

from megazword.backends import Backend, CLIBackend
from megazword.cli import main


@dataclass
class FakeBackend(Backend):
    reply: str = "hello"
    fail: bool = False

    def _run(self, prompt: str) -> str:
        if self.fail:
            raise RuntimeError("boom")
        return f"{self.reply}: {prompt}"


def fakes(**kw):
    return {"fake": FakeBackend("fake", **kw)}


def test_run_prints_answer(capsys):
    assert main(["run", "hi there", "-m", "fake"], fakes()) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "hello: hi there"
    assert "using fake" in out.err


def test_unknown_model(capsys):
    assert main(["run", "hi", "-m", "nope"], fakes()) == 2
    assert "Choose from: fake" in capsys.readouterr().err


def test_failure_is_reported_not_raised(capsys):
    assert main(["run", "hi", "-m", "fake"], fakes(fail=True)) == 1
    assert "boom" in capsys.readouterr().err


def test_backends_lists_availability(capsys):
    missing = CLIBackend("ghost", exe="definitely-not-a-real-cli-xyz")
    assert main(["backends"], {"ghost": missing}) == 0
    out = capsys.readouterr().out
    assert "ghost" in out and "not found" in out


def test_prompt_placeholder_goes_in_args():
    b = CLIBackend("x", exe="python", args=["-c", "{prompt}"])
    cmd, stdin = b._command("print(1)")
    assert cmd[-1] == "print(1)" and stdin is None


def test_prompt_goes_to_stdin_without_placeholder():
    b = CLIBackend("x", exe="python", args=["-"])
    cmd, stdin = b._command("print(1)")
    assert stdin == "print(1)" and "print(1)" not in cmd
