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
    assert text_result(call_tool("hive_read", {})) == "(no messages yet)"


def test_handle_hive_say_and_read(isolated_home):
    result = call_tool("hive_say", {
        "room": "test-room", "author": "Reed-12", "text": "  hello hive  ",
    })
    assert text_result(result) == "[reed-12] hello hive"
    messages = room.read_messages("test-room", home=isolated_home)
    assert [(m.author, m.text) for m in messages] == [("reed-12", "hello hive")]
    assert room.room_path("test-room").parent == isolated_home / "rooms"
    assert text_result(call_tool("hive_read", {"room": "test-room"})) == "[reed-12] hello hive"
    assert text_result(call_tool("hive_read", {})) == "(no messages yet)"


@pytest.mark.parametrize("n, expected", [
    (1, "[quill-12] second"),
    (2, "[reed-12] first\n[quill-12] second"),
    (0, "(no messages yet)"),
])
def test_handle_hive_read_recent(n, expected):
    room.append_message("hive", "reed-12", "first")
    room.append_message("hive", "quill-12", "second")
    assert text_result(call_tool("hive_read", {"n": n})) == expected


def test_handle_hive_say_defaults_to_seat(monkeypatch, isolated_home):
    monkeypatch.setenv("MEGAZWORD_SEAT", "reed-12")
    assert text_result(call_tool("hive_say", {"text": "ready"})) == "[reed-12] ready"
    assert room.read_messages("hive", home=isolated_home)[0].author == "reed-12"


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
    assert text_result(result) == "[quill-12] new instruction"


def test_handle_hive_wait_timeout(monkeypatch):
    room.append_message("hive", "reed-12", "already seen")

    def unexpected_sleep(pause):
        pytest.fail("zero timeout must not sleep")

    monkeypatch.setattr(floor, "sleep", unexpected_sleep)
    assert text_result(call_tool("hive_wait", {"timeout": 0})) == "(no new hive message)"


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
