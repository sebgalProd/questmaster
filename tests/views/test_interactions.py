"""Tests for the Discord interactions endpoint."""

import json
from unittest.mock import MagicMock, patch

import pytest
from nacl.signing import SigningKey

from tests.constants import TEST_ADMIN_USER_ID, TEST_REGULAR_USER_ID
from website.services.steam import STATUS_NOT_LINKED, STATUS_OK, CommonGamesResult, LibraryResult

URL = "/discord/interactions/"


def _run_inline(target, *args):
    target(*args)


@pytest.fixture
def signing_key(test_app, monkeypatch):
    key = SigningKey.generate()
    monkeypatch.setitem(test_app.config, "DISCORD_PUBLIC_KEY", key.verify_key.encode().hex())
    return key


def _post(client, key, payload, tamper=False):
    body = json.dumps(payload).encode()
    timestamp = "1700000000"
    signature = key.sign(timestamp.encode() + body).signature.hex()
    if tamper:
        body = body.replace(b"}", b" }", 1)
    return client.post(
        URL,
        data=body,
        content_type="application/json",
        headers={"X-Signature-Ed25519": signature, "X-Signature-Timestamp": timestamp},
    )


def _command(name, options=None, resolved=None, invoker=TEST_REGULAR_USER_ID, dm=False):
    payload = {
        "type": 2,
        "application_id": "app1",
        "token": "tok",
        "data": {"name": name, "options": options or [], "resolved": {"users": resolved or {}}},
    }
    user = {"id": invoker, "username": "invoker", "global_name": "Invoker"}
    if dm:
        payload["user"] = user
    else:
        payload["member"] = {"user": user, "nick": None}
    return payload


def _opt(i, user_id):
    return {"name": f"joueur{i}", "type": 6, "value": user_id}


def test_ping(client, db_session, signing_key):
    response = _post(client, signing_key, {"type": 1})
    assert response.status_code == 200
    assert response.get_json() == {"type": 1}


def test_bad_signature_is_rejected(client, db_session, signing_key):
    response = _post(client, signing_key, {"type": 1}, tamper=True)
    assert response.status_code == 401


def test_missing_public_key_returns_503(client, db_session, test_app, monkeypatch):
    monkeypatch.setitem(test_app.config, "DISCORD_PUBLIC_KEY", None)
    response = client.post(URL, data=b'{"type":1}', content_type="application/json")
    assert response.status_code == 503


def test_steam_status_is_deferred_ephemeral_then_edited(client, db_session, signing_key):
    service = MagicMock()
    service.get_library.return_value = LibraryResult(STATUS_OK, [{"appid": 1}] * 3)
    bot = MagicMock()
    with (
        patch("website.views.interactions.SteamService", return_value=service),
        patch("website.views.interactions.get_bot", return_value=bot),
        patch("website.views.interactions._start_background", side_effect=_run_inline),
    ):
        response = _post(client, signing_key, _command("steam-statut"))
    assert response.get_json() == {"type": 5, "data": {"flags": 64}}
    app_id, token, payload = bot.edit_interaction_response.call_args.args
    assert (app_id, token) == ("app1", "tok")
    assert "3 jeux" in payload["content"]


def test_common_games_defers_then_edits_response(client, db_session, signing_key):
    service = MagicMock()
    service.common_games.return_value = CommonGamesResult(
        ["Invoker", "Admin"], [], [{"appid": 7, "name": "Valheim", "playtime": 120}], 1, False
    )
    bot = MagicMock()
    options = [_opt(1, TEST_ADMIN_USER_ID)]
    resolved = {
        TEST_ADMIN_USER_ID: {"id": TEST_ADMIN_USER_ID, "username": "admin", "global_name": "Admin"}
    }
    with (
        patch("website.views.interactions.SteamService", return_value=service),
        patch("website.views.interactions.get_bot", return_value=bot),
        patch("website.views.interactions._start_background", side_effect=_run_inline),
    ):
        response = _post(client, signing_key, _command("jeux-en-commun", options, resolved))

    assert response.get_json() == {"type": 5}
    members = service.common_games.call_args.args[0]
    assert [name for name, _ in members] == ["Invoker", "Admin"]
    app_id, token, payload = bot.edit_interaction_response.call_args.args
    assert (app_id, token) == ("app1", "tok")
    assert "Valheim" in payload["embeds"][0]["description"]


def test_duplicates_and_self_mention_count_once(client, db_session, signing_key):
    options = [_opt(1, TEST_REGULAR_USER_ID), _opt(2, TEST_REGULAR_USER_ID)]
    with patch("website.views.interactions._start_background") as start:
        response = _post(client, signing_key, _command("jeux-en-commun", options))
    data = response.get_json()
    assert data["type"] == 4
    assert data["data"]["flags"] == 64
    assert "au moins un autre joueur" in data["data"]["content"]
    start.assert_not_called()


def test_unknown_member_is_not_linked(client, db_session, signing_key):
    service = MagicMock()
    service.common_games.return_value = CommonGamesResult(
        ["Invoker"], [("Robot", STATUS_NOT_LINKED)], [], 0, True
    )
    robot_id = "123456789012345678"
    resolved = {
        robot_id: {"id": robot_id, "username": "robot", "global_name": "Robot", "bot": True}
    }
    with (
        patch("website.views.interactions.SteamService", return_value=service),
        patch("website.views.interactions.get_bot", return_value=MagicMock()),
        patch("website.views.interactions._start_background", side_effect=_run_inline),
    ):
        _post(client, signing_key, _command("jeux-en-commun", [_opt(1, robot_id)], resolved))
    members = service.common_games.call_args.args[0]
    assert members[1] == ("Robot", None)


def test_command_from_direct_message(client, db_session, signing_key):
    service = MagicMock()
    service.get_library.return_value = LibraryResult(STATUS_NOT_LINKED)
    with (
        patch("website.views.interactions.SteamService", return_value=service),
        patch("website.views.interactions.get_bot", return_value=MagicMock()),
        patch("website.views.interactions._start_background", side_effect=_run_inline),
    ):
        response = _post(client, signing_key, _command("steam-statut", dm=True))
    assert response.status_code == 200
    user_arg = service.get_library.call_args.args[0]
    assert user_arg is not None and user_arg.id == TEST_REGULAR_USER_ID


def test_background_error_edits_response_with_error_message(client, db_session, signing_key):
    service = MagicMock()
    service.common_games.side_effect = RuntimeError("boom")
    bot = MagicMock()
    with (
        patch("website.views.interactions.SteamService", return_value=service),
        patch("website.views.interactions.get_bot", return_value=bot),
        patch("website.views.interactions._start_background", side_effect=_run_inline),
    ):
        _post(client, signing_key, _command("jeux-en-commun", [_opt(1, TEST_ADMIN_USER_ID)]))
    payload = bot.edit_interaction_response.call_args.args[2]
    assert payload["content"] == "Une erreur est survenue, réessaie plus tard."
    assert payload["allowed_mentions"] == {"parse": []}


def test_edit_is_retried_when_discord_has_not_registered_the_deferral(
    client, db_session, signing_key
):
    from website.exceptions import DiscordAPIError

    service = MagicMock()
    service.common_games.return_value = CommonGamesResult(["A", "B"], [], [], 0, False)
    bot = MagicMock()
    bot.edit_interaction_response.side_effect = [
        DiscordAPIError("Unknown Webhook", status_code=404),
        {},
    ]
    with (
        patch("website.views.interactions.SteamService", return_value=service),
        patch("website.views.interactions.get_bot", return_value=bot),
        patch("website.views.interactions._start_background", side_effect=_run_inline),
        patch("website.views.interactions.time.sleep") as sleep,
    ):
        _post(client, signing_key, _command("jeux-en-commun", [_opt(1, TEST_ADMIN_USER_ID)]))
    assert bot.edit_interaction_response.call_count == 2
    sleep.assert_called()


def test_member_names_never_ping(client, db_session, signing_key):
    service = MagicMock()
    service.common_games.return_value = CommonGamesResult(["@everyone", "B"], [], [], 0, False)
    bot = MagicMock()
    with (
        patch("website.views.interactions.SteamService", return_value=service),
        patch("website.views.interactions.get_bot", return_value=bot),
        patch("website.views.interactions._start_background", side_effect=_run_inline),
    ):
        _post(client, signing_key, _command("jeux-en-commun", [_opt(1, TEST_ADMIN_USER_ID)]))
    payload = bot.edit_interaction_response.call_args.args[2]
    assert payload["allowed_mentions"] == {"parse": []}


def test_background_thread_closes_db_session_even_on_error():
    from website.views import interactions

    def boom():
        raise RuntimeError("boom")

    with (
        patch.object(interactions.db.session, "remove") as remove,
        patch.object(interactions.threading, "Thread") as thread_cls,
    ):
        interactions._start_background(boom)
        runner = thread_cls.call_args.kwargs["target"]
        with pytest.raises(RuntimeError):
            runner()
    remove.assert_called_once()
    thread_cls.return_value.start.assert_called_once()
