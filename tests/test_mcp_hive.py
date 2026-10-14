"""MCP hive requests against an isolated local room; no AI backends."""

import json
from io import BytesIO

import pytest

from megazword import config, floor, mcp_hive, room


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(room.config, "HOME", tmp_path)
    monkeypatch.setattr(floor.config, "HOME", tmp_path)
    monkeypatch.delenv("MEGAZWORD_SEAT", raising=False)
    return tmp_path


def call_tool(name, arguments, request_id=7):
    response = mcp_hive.handle({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == request_id
    assert "error" not in response
    return response["result"]


def text_result(result):
    assert result["isError"] is False
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    return result["content"][0]["text"]


def test_handle_initialize():
    response = mcp_hive.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    })
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "error" not in response
    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["capabilities"]["tools"] == {}
    assert result["serverInfo"]["name"] == "megazword-hive"
    assert result["serverInfo"]["version"]


@pytest.mark.parametrize("asked", ["2099-01-01", None, 42])
def test_handle_initialize_unknown_version_answers_ours(asked):
    from megazword import __version__
    params = {} if asked is None else {"protocolVersion": asked}
    response = mcp_hive.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": params})
    assert response["result"]["protocolVersion"] == mcp_hive.PROTOCOL_VERSION
    assert response["result"]["serverInfo"]["version"] == __version__


def test_hive_say_description_phil_mentions_only():
    tools = {t["name"]: t for t in mcp_hive.TOOLS}
    desc = tools["hive_say"]["description"]
    assert "bot @names do not" in desc
    assert "Phil's @name" in desc


def test_handle_tools_list():
    response = mcp_hive.handle({
        "jsonrpc": "2.0", "id": 2, "method": "tools/list",
    })
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 2
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    assert {"hive_read", "hive_say", "hive_wait"} <= tools.keys()
    for name in ("hive_read", "hive_say", "hive_wait"):
        assert tools[name]["inputSchema"]["type"] == "object"
    assert "text" in tools["hive_say"]["inputSchema"]["required"]


def test_handle_hive_read_empty():
    assert text_result(call_tool("hive_read", {})) == "(no messages yet)\n(after=0)"


def test_handle_hive_say_and_read(isolated_home):
    result = call_tool("hive_say", {
        "room": "test-room", "author": "Reed-12", "text": "  hello hive  ",
    })
    assert text_result(result) == "[reed-12] hello hive"
    messages = room.read_messages("test-room", home=isolated_home)
    assert [(m.author, m.text) for m in messages] == [("reed-12", "hello hive")]
    assert room.room_path("test-room").parent == isolated_home / "rooms"
    assert text_result(call_tool("hive_read", {"room": "test-room"})) == \
        "[reed-12] hello hive\n(after=1)"
    assert text_result(call_tool("hive_read", {})) == "(no messages yet)\n(after=0)"


@pytest.mark.parametrize("n, expected", [
    (1, "[quill-12] second\n(after=2)"),
    (2, "[reed-12] first\n[quill-12] second\n(after=2)"),
    (0, "(after=2)"),  # cursor only, like `floor peek -n 0`
    (-3, "(after=2)"),
])
def test_handle_hive_read_recent(n, expected):
    room.append_message("hive", "reed-12", "first")
    room.append_message("hive", "quill-12", "second")
    assert text_result(call_tool("hive_read", {"n": n})) == expected


def test_handle_hive_say_defaults_to_seat(monkeypatch, isolated_home):
    monkeypatch.setenv("MEGAZWORD_SEAT", "reed-12")
    assert text_result(call_tool("hive_say", {"text": "ready"})) == "[reed-12] ready"
    assert room.read_messages("hive", home=isolated_home)[0].author == "reed-12"
    assert "reed-12" in floor.format_heard(home=isolated_home)


@pytest.mark.parametrize("author", ["phil", "Phil", None])
def test_handle_hive_say_bot_seat_cannot_post_as_phil(monkeypatch, isolated_home, author):
    monkeypatch.setenv("MEGAZWORD_SEAT", "claude")
    args = {"text": "ship it"}
    if author:
        args["author"] = author
    result = call_tool("hive_say", args)
    if author is None:  # falls back to the seat, which is fine
        assert text_result(result) == "[claude] ship it"
        return
    assert result["isError"] is True
    assert "cannot post as phil" in result["content"][0]["text"]
    assert room.read_messages("hive", home=isolated_home) == []


@pytest.mark.parametrize("seat", [None, "phil", "PHIL"])
def test_handle_hive_say_phil_allowed_without_bot_seat(monkeypatch, isolated_home, seat):
    if seat:
        monkeypatch.setenv("MEGAZWORD_SEAT", seat)
    result = call_tool("hive_say", {"author": "phil", "text": "go"})
    assert text_result(result) == "[phil] go"


def test_room_say_bot_seat_cannot_post_as_phil(monkeypatch, isolated_home):
    monkeypatch.setenv("MEGAZWORD_SEAT", "grok")
    with pytest.raises(PermissionError):
        room.say("hive", "pretend", home=isolated_home, write=lambda s: None)
    assert room.read_messages("hive", home=isolated_home) == []
    room.say("hive", "as myself", author="grok", home=isolated_home, write=lambda s: None)
    assert room.read_messages("hive", home=isolated_home)[0].author == "grok"


def test_handle_hive_wait_new_message(monkeypatch):
    room.append_message("test-room", "reed-12", "already seen")
    # Deliver a local message at the polling boundary without threads or sleeping.
    clock = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(floor, "monotonic", lambda: next(clock))
    monkeypatch.setattr(floor, "sleep", lambda pause: room.append_message(
        "test-room", "quill-12", "new instruction",
    ))
    result = call_tool("hive_wait", {"room": "test-room", "timeout": 1})
    assert text_result(result) == "[quill-12] new instruction\n(after=2)"


def test_handle_hive_wait_timeout(monkeypatch):
    room.append_message("hive", "reed-12", "already seen")

    def unexpected_sleep(pause):
        pytest.fail("zero timeout must not sleep")

    monkeypatch.setattr(floor, "sleep", unexpected_sleep)
    assert text_result(call_tool("hive_wait", {"timeout": 0})) == \
        "(no new hive message)\n(after=1)"


def test_handle_hive_wait_after_catches_message_posted_since_read(monkeypatch):
    room.append_message("hive", "reed-12", "seen")
    assert text_result(call_tool("hive_read", {})).endswith("\n(after=1)")
    room.append_message("hive", "quill-12", "landed between read and wait")
    monkeypatch.setattr(floor, "sleep", lambda pause: pytest.fail("must not block"))
    result = text_result(call_tool("hive_wait", {"after": 1, "timeout": 0}))
    assert result == "[quill-12] landed between read and wait\n(after=2)"
    # Chaining the returned cursor waits for anything newer.
    assert text_result(call_tool("hive_wait", {"after": 2, "timeout": 0})) == \
        "(no new hive message)\n(after=2)"


def test_handle_hive_wait_negative_after_is_clamped(monkeypatch):
    room.append_message("hive", "reed-12", "one")
    monkeypatch.setattr(floor, "sleep", lambda pause: pytest.fail("must not block"))
    assert text_result(call_tool("hive_wait", {"after": -5, "timeout": 0})) == \
        "[reed-12] one\n(after=1)"


@pytest.mark.parametrize("timeout, expected", [
    (1e9, 300.0),
    (float("inf"), 300.0),
    (300, 300.0),
    (45, 45.0),
    (-5, 0.0),
])
def test_handle_hive_wait_timeout_is_capped(monkeypatch, timeout, expected):
    seen = []
    monkeypatch.setattr(floor, "wait_for",
                        lambda room_name, after, timeout: seen.append(timeout) or [])
    text_result(call_tool("hive_wait", {"timeout": timeout}))
    assert seen == [expected]


def test_handle_hive_wait_nan_timeout_is_error(monkeypatch):
    monkeypatch.setattr(floor, "wait_for", lambda *a, **k: pytest.fail("must not wait"))
    result = call_tool("hive_wait", {"timeout": float("nan")})
    assert result["isError"] is True


def test_hive_wait_schema_has_after():
    tools = {t["name"]: t for t in mcp_hive.TOOLS}
    assert tools["hive_wait"]["inputSchema"]["properties"]["after"]["type"] == "integer"


@pytest.mark.parametrize("text", ["", "   "])
def test_handle_hive_say_empty_is_error(text, isolated_home):
    result = call_tool("hive_say", {"text": text})
    assert result["isError"] is True
    assert result["content"][0]["type"] == "text"
    assert "text is required" in result["content"][0]["text"]
    assert room.read_messages("hive", home=isolated_home) == []
    assert not room.room_path("hive").exists()


def test_serve_newline_initialize_roundtrip():
    request = {
        "jsonrpc": "2.0",
        "id": "init-1",
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    }
    stdin = BytesIO((json.dumps(request) + "\n").encode("utf-8"))
    stdout = BytesIO()
    assert mcp_hive.serve(stdin=stdin, stdout=stdout) == 0
    raw = stdout.getvalue()
    assert raw.endswith(b"\n")
    assert len(raw.splitlines()) == 1
    response = json.loads(raw.decode("utf-8"))
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "init-1"
    assert "error" not in response
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert response["result"]["capabilities"]["tools"] == {}
    assert response["result"]["serverInfo"]["name"] == "megazword-hive"


def frame(message):
    body = message if isinstance(message, bytes) else json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def framed_replies(raw):
    stream = BytesIO(raw)
    replies = []
    while (got := mcp_hive.read_message(stream)) is not None:
        message, framed = got
        assert framed is True
        replies.append(message)
    return replies


def serve_bytes(data):
    stdout = BytesIO()
    assert mcp_hive.serve(stdin=BytesIO(data), stdout=stdout) == 0
    return stdout.getvalue()


PING = {"jsonrpc": "2.0", "id": 9, "method": "ping"}


def test_serve_batch_bad_item_gets_error_and_server_keeps_going():
    batch = [
        {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": ["positional"]},
        "not an object",
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
    ]
    replies = framed_replies(serve_bytes(frame(batch) + frame(PING)))
    assert len(replies) == 2
    by_id = {r["id"]: r for r in replies[0]}
    assert len(replies[0]) == 4
    assert by_id[1]["result"] == {}
    assert by_id[2]["error"]["code"] == -32602
    assert by_id[None]["error"]["code"] == -32600
    assert by_id[3]["result"]["tools"]
    assert replies[1] == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_serve_batch_item_that_crashes_handler_gets_internal_error(monkeypatch):
    def boom(request):
        if request.get("id") == 1:
            raise RuntimeError("kaboom")
        return {"jsonrpc": "2.0", "id": request["id"], "result": {}}

    monkeypatch.setattr(mcp_hive, "handle", boom)
    batch = [{"jsonrpc": "2.0", "id": 1, "method": "ping"},
             {"jsonrpc": "2.0", "id": 2, "method": "ping"}]
    [replies] = framed_replies(serve_bytes(frame(batch)))
    assert replies[0]["id"] == 1
    assert replies[0]["error"] == {"code": -32603, "message": "kaboom"}
    assert replies[1] == {"jsonrpc": "2.0", "id": 2, "result": {}}


def test_serve_empty_batch_is_invalid_request():
    [reply] = framed_replies(serve_bytes(frame([])))
    assert reply["error"]["code"] == -32600


def test_serve_newline_batch():
    raw = serve_bytes((json.dumps([PING, {"jsonrpc": "2.0", "id": 10, "method": "nope"}])
                       + "\n").encode("utf-8"))
    replies = json.loads(raw.decode("utf-8"))
    assert replies[0]["result"] == {}
    assert replies[1]["error"]["code"] == -32601


def test_serve_framed_roundtrip():
    [reply] = framed_replies(serve_bytes(frame(PING)))
    assert reply == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_serve_negative_content_length_is_protocol_error():
    # read(-5) would swallow the rest of stdin (and block on a real pipe), losing the ping.
    replies = framed_replies(serve_bytes(b"Content-Length: -5\r\n\r\n" + frame(PING)))
    assert replies[0]["error"]["code"] == -32700
    assert replies[1] == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_serve_oversized_content_length_is_skipped(monkeypatch):
    monkeypatch.setattr(mcp_hive, "MAX_BODY_BYTES", 200)
    big = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "pad": "x" * 400})
    replies = [r for r in framed_replies(serve_bytes(frame(big.encode("utf-8")) + frame(PING)))
               if r is not None]
    assert replies[0]["error"]["code"] == -32700
    assert replies[1] == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_cli_mcp_keeps_stray_prints_off_stdout(monkeypatch):
    import io
    import sys
    from types import SimpleNamespace

    from megazword import cli

    rpc = BytesIO()
    fake_out = SimpleNamespace(buffer=rpc)
    fake_err = io.StringIO()
    seen = {}

    def fake_serve(stdin, stdout):
        print("oops, a stray print")
        seen["stdout"] = stdout
        return 0

    monkeypatch.setattr(mcp_hive, "serve", fake_serve)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=BytesIO()))
    monkeypatch.setattr(sys, "stdout", fake_out)
    monkeypatch.setattr(sys, "stderr", fake_err)
    assert cli.main(["mcp"]) == 0
    assert seen["stdout"] is rpc
    assert rpc.getvalue() == b""
    assert "stray print" in fake_err.getvalue()
    assert sys.stdout is fake_out


@pytest.mark.parametrize("header", [b"Content-Length: nope", b"X-Other: 1"])
def test_serve_bad_content_length_header_is_protocol_error(header):
    [reply] = framed_replies(serve_bytes(header + b"\r\n\r\n"))
    assert reply["error"]["code"] == -32700
