"""Tests for the low-level Steam client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from website.client.steam import Steam
from website.exceptions import SteamAPIError


def _response(status=200, payload=None):
    r = MagicMock()
    r.status_code = status
    r.ok = 200 <= status < 300
    r.json.return_value = payload if payload is not None else {}
    return r


@pytest.fixture
def steam():
    return Steam("secret-key", retry_wait=0)


def test_returns_games(steam):
    payload = {
        "response": {
            "game_count": 2,
            "games": [
                {"appid": 10, "name": "Counter-Strike", "playtime_forever": 120},
                {"appid": 20, "name": "Valheim", "playtime_forever": 0},
            ],
        }
    }
    with patch("website.client.steam.requests.get", return_value=_response(200, payload)) as get:
        games = steam.get_owned_games("76561198000000001")
    assert games == [
        {"appid": 10, "name": "Counter-Strike", "playtime_forever": 120},
        {"appid": 20, "name": "Valheim", "playtime_forever": 0},
    ]
    params = get.call_args.kwargs["params"]
    assert params["steamid"] == "76561198000000001"
    assert params["include_appinfo"] == 1
    assert params["include_played_free_games"] == 1


def test_private_profile_returns_none(steam):
    with patch("website.client.steam.requests.get", return_value=_response(200, {"response": {}})):
        assert steam.get_owned_games("1") is None


def test_public_empty_library_returns_empty_list(steam):
    payload = {"response": {"game_count": 0, "games": []}}
    with patch("website.client.steam.requests.get", return_value=_response(200, payload)):
        assert steam.get_owned_games("1") == []


def test_game_without_name_gets_fallback(steam):
    payload = {"response": {"games": [{"appid": 42, "playtime_forever": 5}]}}
    with patch("website.client.steam.requests.get", return_value=_response(200, payload)):
        assert steam.get_owned_games("1") == [
            {"appid": 42, "name": "App 42", "playtime_forever": 5}
        ]


def test_retries_transient_error_then_succeeds(steam):
    ok = _response(200, {"response": {"games": []}})
    with patch("website.client.steam.requests.get", side_effect=[_response(503), ok]) as get:
        assert steam.get_owned_games("1") == []
    assert get.call_count == 2


def test_network_error_is_retried(steam):
    ok = _response(200, {"response": {"games": []}})
    with patch(
        "website.client.steam.requests.get",
        side_effect=[requests.ConnectionError("down"), ok],
    ):
        assert steam.get_owned_games("1") == []


def test_gives_up_after_three_transient_errors(steam):
    with patch("website.client.steam.requests.get", return_value=_response(503)) as get:
        with pytest.raises(SteamAPIError):
            steam.get_owned_games("1")
    assert get.call_count == 3


def test_permanent_error_is_not_retried(steam):
    with patch("website.client.steam.requests.get", return_value=_response(403)) as get:
        with pytest.raises(SteamAPIError) as exc:
            steam.get_owned_games("1")
    assert get.call_count == 1
    assert "secret-key" not in str(exc.value)
