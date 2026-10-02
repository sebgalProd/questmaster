"""Tests for UserService.link_steam_from_connections."""

from types import SimpleNamespace

from website.services.user import UserService


def _conn(type_, id_):
    return SimpleNamespace(type=type_, id=id_)


def test_links_steam_connection(db_session, regular_user):
    changed = UserService().link_steam_from_connections(
        regular_user, [_conn("twitch", "t1"), _conn("steam", "76561198000000001")]
    )
    assert changed is True
    assert regular_user.steam_id == "76561198000000001"


def test_no_steam_connection_keeps_existing_value(db_session, regular_user):
    regular_user.steam_id = "76561198000000001"
    changed = UserService().link_steam_from_connections(regular_user, [_conn("twitch", "t1")])
    assert changed is False
    assert regular_user.steam_id == "76561198000000001"


def test_same_steam_id_is_not_a_change(db_session, regular_user):
    regular_user.steam_id = "76561198000000001"
    changed = UserService().link_steam_from_connections(
        regular_user, [_conn("steam", "76561198000000001")]
    )
    assert changed is False
