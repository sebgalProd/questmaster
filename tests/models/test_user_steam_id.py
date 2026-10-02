"""Tests for the User.steam_id column and SteamAPIError."""

from website.exceptions import QuestMasterError, SteamAPIError
from website.models import User


def test_user_steam_id_defaults_to_none(db_session):
    user = User(id="999000000000000111", name="Steamless")
    db_session.add(user)
    db_session.flush()
    assert user.steam_id is None


def test_user_steam_id_is_persisted(db_session):
    user = User(id="999000000000000112", name="Steamer")
    user.steam_id = "76561198000000001"
    db_session.add(user)
    db_session.flush()
    assert db_session.get(User, "999000000000000112").steam_id == "76561198000000001"


def test_steam_api_error_is_questmaster_error():
    err = SteamAPIError("boom", status_code=503)
    assert isinstance(err, QuestMasterError)
    assert err.status_code == 503
    assert "503" in str(err)
