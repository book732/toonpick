"""Verify QA-channel isolation, safe errors, pagination, and MCP transport."""

import asyncio
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("discord_qa", _ROOT / "scripts/discord_qa.py")
_QA = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_QA)


def _response(_value):
    _result = io.BytesIO(json.dumps(_value).encode())
    _result.status = 200
    return _result


def _test_channel_boundary():
    with patch.object(_QA, "_request", return_value={"id": _QA._CHANNEL_ID, "guild_id": "other"}):
        with unittest.TestCase().assertRaisesRegex(RuntimeError, "지정된 QA 서버"):
            _QA._read_qa()
    with patch.object(_QA, "_request", return_value={
        "id": "1566066429298479174", "guild_id": _QA._GUILD_ID,
        "parent_id": "other", "type": 11,
    }) as _request:
        with unittest.TestCase().assertRaisesRegex(RuntimeError, "#qa 채널에 속한"):
            _QA._read_qa(_thread_id="1566066429298479174")
        assert _request.call_count == 1


def _test_pagination_and_attachments():
    _messages = [{"id": str(_id), "content": "QA", "author": {"username": "tester"},
                  "reactions": [{"emoji": {"name": "✅"}, "me": True}],
                  "attachments": [{"filename": "qa.png", "url": "https://cdn.discordapp.com/qa.png"}]}
                 for _id in (1566066429298479175, 1566066429298479174)]
    with patch.object(_QA, "_channel", return_value={"id": _QA._CHANNEL_ID}), \
            patch.object(_QA, "_request", return_value=_messages) as _request:
        _result = _QA._read_qa(2, "1566066429298479176")
        assert _result["next_before"] == "1566066429298479174"
        assert _result["messages"][0]["id"] == "1566066429298479174"
        assert _result["messages"][0]["attachments"][0]["filename"] == "qa.png"
        assert _result["messages"][0]["completed"]
        assert _result["messages"][0]["url"].endswith("/1566066429298479174")
        _request.assert_called_once_with("/channels/" + _QA._CHANNEL_ID + "/messages",
                                        {"limit": 2, "before": "1566066429298479176"})


def _test_validation_before_io():
    for _arguments in ({"_limit": 0}, {"_limit": 101}, {"_before": "../other"},
                       {"_thread_id": "../other"}):
        with patch.object(_QA, "_request") as _request:
            with unittest.TestCase().assertRaises(ValueError):
                _QA._read_qa(**_arguments)
            _request.assert_not_called()


def _test_secret_loading():
    with tempfile.TemporaryDirectory() as _directory:
        _path = Path(_directory) / ".env.discord.local"
        _path.write_text("DISCORD_BOT_TOKEN=local-test-token\n", encoding="utf-8")
        with patch.object(_QA, "_TOKEN_FILE", _path), patch.dict(_QA.os.environ, {"DISCORD_BOT_TOKEN": ""}):
            assert _QA._token() == "local-test-token"
            _path.write_text("DISCORD_BOT_TOKEN=\n", encoding="utf-8")
            with unittest.TestCase().assertRaisesRegex(RuntimeError, "DISCORD_BOT_TOKEN"):
                _QA._token()


def _test_only_get_and_safe_errors():
    with patch.object(_QA, "_token", return_value="never-log-this"), \
            patch.object(_QA, "urlopen", return_value=_response([])) as _open:
        assert _QA._request("/channels/" + _QA._CHANNEL_ID + "/messages") == []
        _request = _open.call_args.args[0]
        assert _request.get_method() == "GET"
        assert _request.full_url.startswith("https://discord.com/api/v10/")
        assert _request.get_header("Authorization") == "Bot never-log-this"
    for _status in (401, 403, 404):
        _error = HTTPError("https://discord.com", _status, "never-log-this", {}, io.BytesIO())
        with patch.object(_QA, "_token", return_value="never-log-this"), \
                patch.object(_QA, "urlopen", side_effect=_error):
            with unittest.TestCase().assertRaises(RuntimeError) as _raised:
                _QA._request("/users/@me")
            assert "never-log-this" not in str(_raised.exception)


def _test_rate_limit_bounds():
    _error = HTTPError("https://discord.com", 429, "rate limited", {}, _response({"retry_after": 0}))
    with patch.object(_QA, "_token", return_value="test-token"), \
            patch.object(_QA, "urlopen", side_effect=[_error, _response([])]), \
            patch.object(_QA.time, "sleep") as _sleep:
        assert _QA._request("/users/@me") == []
        _sleep.assert_called_once_with(0)
    _error = HTTPError("https://discord.com", 429, "rate limited", {}, _response({"retry_after": 120}))
    with patch.object(_QA, "_token", return_value="test-token"), \
            patch.object(_QA, "urlopen", side_effect=_error), patch.object(_QA.time, "sleep") as _sleep:
        with unittest.TestCase().assertRaisesRegex(RuntimeError, "조회 제한"):
            _QA._request("/users/@me")
        _sleep.assert_not_called()


def _test_no_false_connection():
    with patch.object(_QA, "_request", return_value={"bot": True, "id": "other-bot"}):
        with unittest.TestCase().assertRaisesRegex(RuntimeError, "ToonPick QA"):
            _QA._check_connection()
    _responses = [{"bot": True, "id": _QA._APPLICATION_ID, "username": "QA"}, {"flags": 0}]
    with patch.object(_QA, "_request", side_effect=_responses):
        with unittest.TestCase().assertRaisesRegex(RuntimeError, "Message Content Intent"):
            _QA._check_connection()
    _responses[1] = {"flags": 1 << 19}
    with patch.object(_QA, "_request", side_effect=_responses), \
            patch.object(_QA, "_channel", return_value={"name": "qa"}), \
            patch.object(_QA, "_read_qa", return_value={"messages": []}):
        with unittest.TestCase().assertRaisesRegex(RuntimeError, "메시지 기록 보기"):
            _QA._check_connection()


async def _mcp_transport():
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    _parameters = StdioServerParameters(command=sys.executable,
                                       args=[str(_ROOT / "scripts/discord_qa.py")])
    async with Client(_parameters, read_timeout_seconds=10) as _client:
        _tools = await _client.list_tools()
        _by_name = {_tool.name: _tool for _tool in _tools.tools}
        assert set(_by_name) == {"read_qa", "check_connection", "mark_qa_complete"}
        assert all(_by_name[_name].annotations.read_only_hint for _name in ('read_qa', 'check_connection'))
        assert not _by_name['mark_qa_complete'].annotations.read_only_hint
        _result = await _client.call_tool("read_qa", {"limit": 0})
        assert _result.is_error
        assert "1~100" in _result.content[0].text


def _test_mcp_transport():
    async def _bounded():
        await asyncio.wait_for(_mcp_transport(), timeout=20)
    asyncio.run(_bounded())


def _test_completion_scope_and_idempotency():
    _id = '1566066429298479174'
    _message = {'id': _id, 'channel_id': _QA._CHANNEL_ID,
                'reactions': [{'emoji': {'name': '✅'}, 'me': True}]}
    with patch.object(_QA, '_channel'), patch.object(_QA, '_request', return_value=_message) as _request:
        assert _QA._mark_qa_complete(_id)['completed']
        assert _request.call_count == 1
    with patch.object(_QA, '_channel'), patch.object(_QA, '_request', return_value={'id': _id, 'channel_id': 'other'}):
        with unittest.TestCase().assertRaisesRegex(RuntimeError, '#qa 채널'):
            _QA._mark_qa_complete(_id)
    with patch.object(_QA, '_request') as _request:
        with unittest.TestCase().assertRaises(ValueError):
            _QA._mark_qa_complete('../other')
        _request.assert_not_called()
    with patch.object(_QA, '_channel'), patch.object(_QA, '_request', side_effect=[
        {**_message, 'reactions': []}, {}, _message,
    ]) as _request:
        assert _QA._mark_qa_complete(_id)['completed']
        _request.assert_any_call('/channels/' + _QA._CHANNEL_ID + '/messages/' + _id +
                                '/reactions/%E2%9C%85/@me', _method='PUT')


def _test_empty_reaction_response():
    _empty = io.BytesIO()
    _empty.status = 204
    with patch.object(_QA, '_token', return_value='test-token'), patch.object(_QA, 'urlopen', return_value=_empty):
        assert _QA._request('/test', _method='PUT') == {}


def load_tests(_loader, _tests, _pattern):
    return unittest.TestSuite(unittest.FunctionTestCase(_function)
                              for _name, _function in globals().items() if _name.startswith("_test_"))


if __name__ == "__main__":
    unittest.main()
