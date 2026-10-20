"""Settings edits preserve user TOML and fail without damaging it."""
import tomllib
from datetime import datetime, timezone

import pytest

from megazword import config

ORIGINAL = '''# mine
quality_check = false # flag note
unknown = { text = "# literal", n = 7 }
[route] # routes note
easy = [
  "grok", # first choice
  "claude", # backup
] # route note
medium = ["codex"]
[timeouts]
claude = 60 # seconds note
future = 13
[limits]
log_lines = 200 # log note
memory_lines = 300 # memory note
[out]
grok = 2026-10-17T00:00:00Z # out note
[unknown_table]
text = """[route]
easy = ["not a real key"]
# string content
"""
[[unknown_table.items]]
name = "keep"
'''

CASES = [
    (lambda p: config.set_route('easy', ['codex', 'grok'], p), ('route', 'easy'), ['codex', 'grok']),
    (lambda p: config.set_timeout('claude', 900, p), ('timeouts', 'claude'), 900),
    (lambda p: config.set_limit('log_lines', 50, p), ('limits', 'log_lines'), 50),
    (lambda p: config.set_limit('memory_lines', 60, p), ('limits', 'memory_lines'), 60),
    (lambda p: config.set_flag('quality_check', True, p), ('quality_check',), True),
    (lambda p: config.set_out(p, 'grok', datetime(2026, 11, 1, tzinfo=timezone.utc)),
     ('out', 'grok'), datetime(2026, 11, 1, tzinfo=timezone.utc)),
]


@pytest.mark.parametrize('writer,keys,value', CASES)
def test_writers_keep_comments_and_other_values(tmp_path, writer, keys, value):
    p = tmp_path / 'config.toml'
    p.write_bytes(ORIGINAL.replace('\n', '\r\n').encode())
    writer(p)
    raw = p.read_bytes()
    text = raw.decode()
    assert b'\n' not in raw.replace(b'\r\n', b'')
    for comment in ('# mine', '# flag note', '# routes note', '# first choice', '# backup',
                    '# route note', '# seconds note', '# log note', '# memory note', '# out note'):
        assert comment in text
    before, after = tomllib.loads(ORIGINAL), tomllib.loads(text)
    old, new = before, after
    for key in keys[:-1]:
        old, new = old[key], new[key]
    assert new.pop(keys[-1]) == value
    old.pop(keys[-1])
    assert before == after
    assert '[unknown_table]' + ORIGINAL.split('[unknown_table]', 1)[1] in text.replace('\r\n', '\n')


@pytest.mark.parametrize('writer,keys,value', CASES)
@pytest.mark.parametrize('exists', [True, False])
def test_reload_failure_restores_original(tmp_path, monkeypatch, writer, keys, value, exists):
    p = tmp_path / 'config.toml'
    old = ORIGINAL.encode()
    if exists:
        p.write_bytes(old)
    real_load = config.load
    def fail_reload(path=None):
        if path == p:
            raise ValueError('injected reload failure')
        return real_load(path)
    monkeypatch.setattr(config, 'load', fail_reload)
    with pytest.raises(ValueError, match='injected'):
        writer(p)
    assert p.read_bytes() == old if exists else not p.exists()
    assert not list(tmp_path.glob('.config-*.tmp'))


@pytest.mark.parametrize('writer,keys,value', CASES)
def test_atomic_replace_failure_leaves_original(tmp_path, monkeypatch, writer, keys, value):
    p = tmp_path / 'config.toml'
    p.write_text(ORIGINAL, encoding='utf-8')
    old = p.read_bytes()
    def fail_replace(src, dst):
        assert p.read_bytes() == old
        assert config.Path(src).parent == p.parent
        tomllib.loads(config.Path(src).read_text(encoding='utf-8'))
        raise OSError('injected replace failure')
    monkeypatch.setattr(config.os, 'replace', fail_replace)
    with pytest.raises(OSError, match='injected'):
        writer(p)
    assert p.read_bytes() == old
    assert not list(tmp_path.glob('.config-*.tmp'))


@pytest.mark.parametrize('writer', [
    lambda p: config.set_route('evil', ['claude'], p),
    lambda p: config.set_route([], ['claude'], p),
    lambda p: config.set_route('easy', 'claude', p),
    lambda p: config.set_route('easy', ['claude', 'claude'], p),
    lambda p: config.set_route('easy', ['unknown'], p),
    lambda p: config.set_route('easy', [{}], p),
    lambda p: config.set_timeout('unknown', 10, p),
    lambda p: config.set_timeout('claude', True, p),
    lambda p: config.set_timeout('claude', 0, p),
    lambda p: config.set_timeout('claude', 0.5, p),
    lambda p: config.set_timeout('claude', float('inf'), p),
    lambda p: config.set_limit('unknown', 10, p),
    lambda p: config.set_limit('log_lines', -1, p),
    lambda p: config.set_limit('memory_lines', True, p),
    lambda p: config.set_limit('memory_lines', '10', p),
    lambda p: config.set_flag('unknown', True, p),
    lambda p: config.set_flag('quality_check', 'false', p),
    lambda p: config.set_flag('quality_check', 1, p),
])
def test_bad_input_does_not_write(tmp_path, writer):
    p = tmp_path / 'config.toml'
    p.write_text(ORIGINAL, encoding='utf-8')
    old = p.read_bytes()
    with pytest.raises(ValueError):
        writer(p)
    assert p.read_bytes() == old


def test_create_add_clear_and_empty_route(tmp_path):
    p = tmp_path / 'config.toml'
    config.set_route('hard', [], p)
    config.set_timeout('claude', 45, p)
    config.set_timeout('codex', 90, p)
    config.set_limit('log_lines', 10, p)
    config.set_flag('quality_check', True, p)
    config.set_timeout('claude', None, p)
    config.set_timeout('grok', None, p)
    cfg = config.load(p)
    assert cfg.route['hard'] == []
    assert cfg.timeouts == {'codex': 90}
    assert cfg.log_lines == 10 and cfg.quality_check


def test_clear_timeout_keeps_inline_comment(tmp_path):
    p = tmp_path / 'config.toml'
    p.write_text(ORIGINAL, encoding='utf-8')
    config.set_timeout('claude', None, p)
    assert '# seconds note' in p.read_text(encoding='utf-8')
    assert 'claude' not in config.load(p).timeouts


@pytest.mark.parametrize('original', ['[route\n', 'route = {easy = ["grok"]}\n', 'route.easy = ["grok"]\n'])
def test_malformed_or_unsupported_target_layout_is_untouched(tmp_path, original):
    p = tmp_path / 'config.toml'
    p.write_text(original, encoding='utf-8')
    old = p.read_bytes()
    with pytest.raises(ValueError):
        config.set_route('easy', ['claude'], p)
    assert p.read_bytes() == old


def test_quoted_table_key_and_no_final_newline(tmp_path):
    p = tmp_path / 'config.toml'
    p.write_text('["route"] # hi\n"easy" = ["grok"]', encoding='utf-8')
    config.set_route('easy', ['claude'], p)
    assert p.read_text(encoding='utf-8') == '["route"] # hi\n"easy" = ["claude"]'
