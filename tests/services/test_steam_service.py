"""Tests for SteamService."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from website.exceptions import SteamAPIError
from website.services.steam import (
    LIBRARY_CACHE_TIMEOUT,
    STATUS_NOT_LINKED,
    STATUS_OK,
    STATUS_PRIVATE,
    STATUS_UNAVAILABLE,
    SteamService,
)


class FakeCache:
    def __init__(self):
        self.store = {}
        self.timeouts = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, timeout=None):
        self.store[key] = value
        self.timeouts[key] = timeout


def _user(steam_id):
    return SimpleNamespace(steam_id=steam_id)


def _game(appid, name, minutes):
    return {"appid": appid, "name": name, "playtime_forever": minutes}


@pytest.fixture
def cache():
    return FakeCache()


def test_not_linked_user(cache):
    client = MagicMock()
    service = SteamService(client=client, cache=cache)
    assert service.get_library(_user(None)).status == STATUS_NOT_LINKED
    assert service.get_library(None).status == STATUS_NOT_LINKED
    client.get_owned_games.assert_not_called()


def test_library_is_cached(cache):
    client = MagicMock()
    client.get_owned_games.return_value = [_game(1, "A", 10)]
    service = SteamService(client=client, cache=cache)
    first = service.get_library(_user("s1"))
    second = service.get_library(_user("s1"))
    assert first.status == second.status == STATUS_OK
    assert second.games == [_game(1, "A", 10)]
    client.get_owned_games.assert_called_once_with("s1")
    assert cache.timeouts["steam:library:s1"] == LIBRARY_CACHE_TIMEOUT


def test_private_library_is_cached(cache):
    client = MagicMock()
    client.get_owned_games.return_value = None
    service = SteamService(client=client, cache=cache)
    assert service.get_library(_user("s1")).status == STATUS_PRIVATE
    assert service.get_library(_user("s1")).status == STATUS_PRIVATE
    client.get_owned_games.assert_called_once()


def test_unavailable_is_never_cached(cache):
    client = MagicMock()
    client.get_owned_games.side_effect = SteamAPIError("down", status_code=503)
    service = SteamService(client=client, cache=cache)
    assert service.get_library(_user("s1")).status == STATUS_UNAVAILABLE
    assert service.get_library(_user("s1")).status == STATUS_UNAVAILABLE
    assert client.get_owned_games.call_count == 2
    assert "steam:library:s1" not in cache.store


def test_common_games_intersection_sorted_by_group_playtime(cache):
    libraries = {
        "a": [_game(1, "Zeta", 10), _game(2, "Alpha", 500), _game(3, "Only A", 9999)],
        "b": [_game(1, "Zeta", 600), _game(2, "Alpha", 5)],
    }
    client = MagicMock()
    client.get_owned_games.side_effect = lambda sid: libraries[sid]
    service = SteamService(client=client, cache=cache)

    result = service.common_games([("Alice", _user("a")), ("Bob", _user("b"))])

    assert result.included == ["Alice", "Bob"]
    assert result.excluded == []
    assert result.too_few is False
    assert result.total == 2
    assert result.games == [
        {"appid": 1, "name": "Zeta", "playtime": 610},
        {"appid": 2, "name": "Alpha", "playtime": 505},
    ]


def test_ties_are_sorted_by_name(cache):
    libraries = {
        "a": [_game(1, "Beta", 0), _game(2, "Alpha", 0)],
        "b": [_game(1, "Beta", 0), _game(2, "Alpha", 0)],
    }
    client = MagicMock()
    client.get_owned_games.side_effect = lambda sid: libraries[sid]
    result = SteamService(client=client, cache=cache).common_games(
        [("A", _user("a")), ("B", _user("b"))]
    )
    assert [g["name"] for g in result.games] == ["Alpha", "Beta"]


def test_excluded_members_and_too_few(cache):
    client = MagicMock()
    client.get_owned_games.side_effect = lambda sid: None if sid == "priv" else [_game(1, "A", 1)]
    service = SteamService(client=client, cache=cache)

    result = service.common_games(
        [("Alice", _user("a")), ("Bob", None), ("Carole", _user("priv"))]
    )

    assert result.included == ["Alice"]
    assert result.excluded == [("Bob", STATUS_NOT_LINKED), ("Carole", STATUS_PRIVATE)]
    assert result.too_few is True
    assert result.games == []
    assert result.total == 0


def test_no_common_game(cache):
    libraries = {"a": [_game(1, "A", 1)], "b": [_game(2, "B", 1)]}
    client = MagicMock()
    client.get_owned_games.side_effect = lambda sid: libraries[sid]
    result = SteamService(client=client, cache=cache).common_games(
        [("A", _user("a")), ("B", _user("b"))]
    )
    assert result.too_few is False
    assert result.games == []
    assert result.total == 0
