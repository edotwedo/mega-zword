import os

from megazword import cli, config


def test_fills_missing_known_keys_only():
    env = {"GROQ_API_KEY": ""}
    store = {"GROQ_API_KEY": "fake-groq", "MISTRAL_API_KEY": "fake-mistral",
             "CEREBRAS_API_KEY": "fake-cerebras",
             "SOME_OTHER_KEY": "nope"}
    copied = config.load_user_env(read=store.get, env=env)
    assert sorted(copied) == ["CEREBRAS_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY"]
    assert env == {"GROQ_API_KEY": "fake-groq", "MISTRAL_API_KEY": "fake-mistral",
                   "CEREBRAS_API_KEY": "fake-cerebras"}


def test_does_not_overwrite_set_vars():
    env = {"GROQ_API_KEY": "from-shell"}
    copied = config.load_user_env(read=lambda name: "from-registry", env=env)
    assert env["GROQ_API_KEY"] == "from-shell"
    assert "GROQ_API_KEY" not in copied


def test_uses_os_environ_by_default(monkeypatch):
    for name in config.USER_ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    config.load_user_env(read={"NVIDIA_API_KEY": "fake-nvidia"}.get)
    assert os.environ["NVIDIA_API_KEY"] == "fake-nvidia"
    assert "GROQ_API_KEY" not in os.environ


def test_noop_off_windows(monkeypatch):
    monkeypatch.setattr(config.os, "name", "posix")
    assert config.load_user_env(env={}) == []


def test_cli_main_loads_user_env_only_for_real_runs(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "load_user_env", lambda: calls.append(1))
    monkeypatch.setattr(cli, "build_parser", lambda: (_ for _ in ()).throw(SystemExit(0)))
    for argv in (None, ["doctor"]):
        try:
            cli.main(argv)
        except SystemExit:
            pass
    assert calls == [1]


def test_values_never_printed(capsys):
    config.load_user_env(read=lambda name: "secret-value", env={})
    out = capsys.readouterr()
    assert "secret-value" not in out.out + out.err
