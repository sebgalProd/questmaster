"""Tests for UserService.resolve_member (find a member by pseudo or Discord ID)."""

from unittest.mock import Mock

import pytest

from tests.constants import TEST_GM_USER_ID, TEST_REGULAR_USER_ID
from website.exceptions import ValidationError
from website.services.user import UserService

NEW_ID = "123456789012345678"


def _member(user_id, username, global_name=None, nick=None):
    return {
        "user": {"id": user_id, "username": username, "global_name": global_name},
        "nick": nick,
    }


@pytest.fixture
def discord():
    return Mock(search_members=Mock(return_value=[]))


def test_discord_id_is_used_as_is(db_session, discord):
    user = UserService().resolve_member(TEST_REGULAR_USER_ID, discord)
    assert user.id == TEST_REGULAR_USER_ID
    discord.search_members.assert_not_called()


def test_known_member_found_by_name_ignoring_case_and_at_sign(db_session, discord):
    assert UserService().resolve_member("@jadow", discord).id == TEST_GM_USER_ID
    assert UserService().resolve_member("  GREW ", discord).id == TEST_REGULAR_USER_ID
    discord.search_members.assert_not_called()


def test_unknown_member_found_on_discord_is_created(db_session, discord):
    discord.search_members.return_value = [_member(NEW_ID, "zelda", "Zelda", "Zel")]

    user = UserService().resolve_member("zel", discord)

    # The display name is refreshed from the Discord profile on load, not checked here
    assert user.id == NEW_ID
    assert user.username == "zelda"


def test_exact_match_wins_over_other_results(db_session, discord):
    discord.search_members.return_value = [
        _member("223456789012345678", "zeldafan"),
        _member(NEW_ID, "zelda"),
    ]
    assert UserService().resolve_member("zelda", discord).id == NEW_ID


def test_ambiguous_search_lists_candidates(db_session, discord):
    discord.search_members.return_value = [
        _member("223456789012345678", "zeldafan"),
        _member(NEW_ID, "zeldax"),
    ]
    with pytest.raises(ValidationError) as exc:
        UserService().resolve_member("zeld", discord)
    assert "zeldafan" in str(exc.value)
    assert "zeldax" in str(exc.value)


def test_nobody_found(db_session, discord):
    with pytest.raises(ValidationError) as exc:
        UserService().resolve_member("personne", discord)
    assert "personne" in str(exc.value)


def test_empty_query_is_refused(db_session, discord):
    with pytest.raises(ValidationError):
        UserService().resolve_member("  @ ", discord)
