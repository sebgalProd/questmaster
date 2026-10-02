"""Login callback links Steam and never fails because of it."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.constants import TEST_REGULAR_USER_ID


def _fake_discord(connections=None, error=None):
    fake = MagicMock()
    fake.authorized = True
    fake.fetch_user.return_value = SimpleNamespace(id=TEST_REGULAR_USER_ID)
    if error:
        fake.fetch_connections.side_effect = error
    else:
        fake.fetch_connections.return_value = connections or []
    return fake


def test_login_requests_connections_scope(client):
    with patch("website.views.auth.discord") as fake:
        fake.create_session.return_value = "redirecting"
        client.get("/login/")
        fake.create_session.assert_called_once_with(scope=["identify", "connections"])


def test_callback_links_steam(client, db_session, mock_discord_lookups, regular_user):
    fake = _fake_discord([SimpleNamespace(type="steam", id="76561198000000042")])
    with patch("website.views.auth.discord", fake):
        response = client.get("/callback/")
    assert response.status_code in (302, 303)
    assert regular_user.steam_id == "76561198000000042"


def test_callback_succeeds_when_connections_fail(
    client, db_session, mock_discord_lookups, regular_user
):
    fake = _fake_discord(error=RuntimeError("Discord down"))
    with patch("website.views.auth.discord", fake):
        response = client.get("/callback/")
    assert response.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert sess["user_id"] == TEST_REGULAR_USER_ID


def test_callback_rolls_back_when_steam_link_fails(
    client, db_session, mock_discord_lookups, regular_user
):
    fake = _fake_discord([SimpleNamespace(type="steam", id="76561198000000042")])
    with (
        patch("website.views.auth.discord", fake),
        patch(
            "website.services.user.UserService.link_steam_from_connections",
            side_effect=RuntimeError("db error"),
        ),
        patch("website.views.auth.db.session.rollback") as rollback,
    ):
        response = client.get("/callback/")
    assert response.status_code in (302, 303)
    rollback.assert_called_once()
