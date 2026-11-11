"""Tests for interaction-related Discord client methods."""

from unittest.mock import MagicMock

from website.client.discord import Discord
from website.utils.discord_commands import DISCORD_COMMANDS


def _client():
    client = Discord.__new__(Discord)  # skip __init__, which calls the live API
    client.guild_id = "guild1"
    client._request = MagicMock(return_value={})
    return client


def test_edit_interaction_response():
    client = _client()
    client.edit_interaction_response("app1", "tok", {"content": "hi"})
    client._request.assert_called_once_with(
        "PATCH", "/webhooks/app1/tok/messages/@original", json={"content": "hi"}
    )


def test_register_guild_commands():
    client = _client()
    client.register_guild_commands("app1", DISCORD_COMMANDS)
    client._request.assert_called_once_with(
        "PUT", "/applications/app1/guilds/guild1/commands", json=DISCORD_COMMANDS
    )


def test_command_definitions():
    by_name = {c["name"]: c for c in DISCORD_COMMANDS}
    assert set(by_name) == {"steam-statut", "jeux-en-commun"}
    options = by_name["jeux-en-commun"]["options"]
    assert [o["name"] for o in options] == [f"joueur{i}" for i in range(1, 10)]
    assert all(o["type"] == 6 for o in options)
    assert options[0]["required"] is True
    assert not any(o.get("required") for o in options[1:])


def test_discord_requests_have_a_timeout():
    from unittest.mock import patch

    client = Discord.__new__(Discord)
    client.headers = {}
    ok = MagicMock(status_code=200, ok=True, content=b"{}")
    ok.json.return_value = {}
    with patch("website.client.discord.requests.request", return_value=ok) as req:
        client._request("GET", "/users/@me")
    assert req.call_args.kwargs.get("timeout")


def test_search_members():
    client = _client()
    client._request.return_value = [{"user": {"id": "1"}}]
    assert client.search_members("zel", limit=5) == [{"user": {"id": "1"}}]
    client._request.assert_called_once_with(
        "GET", "/guilds/guild1/members/search", params={"query": "zel", "limit": 5}
    )
