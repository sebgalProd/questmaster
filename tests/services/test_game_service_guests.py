"""Tests for weekly guests and co-organizers in GameService."""

import pytest

from tests.factories import GameFactory
from website.exceptions import ValidationError


@pytest.fixture
def weekly_game(db_session, admin_user, default_system):
    """A silently opened game: closed, no public announcement."""
    return GameFactory(
        db_session,
        gm_id=admin_user.id,
        system_id=default_system.id,
        status="closed",
        role="weekly_role",
        party_size=6,
    )


class TestGuests:
    def test_register_as_guest_marks_player_as_guest(
        self, db_session, weekly_game, regular_user, game_service
    ):
        game_service.register_player(weekly_game.slug, regular_user.id, force=True, guest=True)

        assert regular_user in weekly_game.players
        assert regular_user in weekly_game.guests

    def test_regular_registration_is_not_a_guest(
        self, db_session, weekly_game, regular_user, game_service
    ):
        game_service.register_player(weekly_game.slug, regular_user.id, force=True)

        assert regular_user in weekly_game.players
        assert regular_user not in weekly_game.guests

    def test_clear_guests_keeps_permanent_members(
        self, db_session, weekly_game, regular_user, gm_user, game_service, mock_discord
    ):
        game_service.register_player(weekly_game.slug, gm_user.id, force=True)
        game_service.register_player(weekly_game.slug, regular_user.id, force=True, guest=True)

        removed = game_service.clear_guests(weekly_game.slug, user_id=gm_user.id)

        assert removed == 1
        assert weekly_game.players == [gm_user]
        assert weekly_game.guests == []
        mock_discord.remove_role_from_user.assert_called_once_with(regular_user.id, "weekly_role")

    def test_removing_a_guest_does_not_reopen_the_game(
        self, db_session, weekly_game, regular_user, game_service
    ):
        game_service.register_player(weekly_game.slug, regular_user.id, force=True, guest=True)

        game_service.unregister_player(weekly_game.slug, regular_user.id)

        assert weekly_game.status == "closed"
        assert weekly_game.guests == []

    def test_clear_guests_without_guests_removes_nobody(
        self, db_session, weekly_game, gm_user, game_service
    ):
        game_service.register_player(weekly_game.slug, gm_user.id, force=True)

        assert game_service.clear_guests(weekly_game.slug) == 0
        assert weekly_game.players == [gm_user]


class TestOrganizers:
    def test_add_and_remove_organizer(self, db_session, weekly_game, gm_user, game_service):
        game_service.add_organizer(weekly_game.slug, gm_user.id)
        assert weekly_game.organizers == [gm_user]

        game_service.remove_organizer(weekly_game.slug, gm_user.id)
        assert weekly_game.organizers == []

    def test_adding_the_gm_as_organizer_is_refused(
        self, db_session, weekly_game, admin_user, game_service
    ):
        with pytest.raises(ValidationError):
            game_service.add_organizer(weekly_game.slug, admin_user.id)

    def test_adding_an_organizer_twice_is_refused(
        self, db_session, weekly_game, gm_user, game_service
    ):
        game_service.add_organizer(weekly_game.slug, gm_user.id)
        with pytest.raises(ValidationError):
            game_service.add_organizer(weekly_game.slug, gm_user.id)

    def test_can_manage_players(
        self, db_session, weekly_game, admin_user, gm_user, regular_user, game_service
    ):
        game_service.add_organizer(weekly_game.slug, gm_user.id)

        assert game_service.can_manage_players(weekly_game, admin_user.id)
        assert game_service.can_manage_players(weekly_game, gm_user.id)
        assert not game_service.can_manage_players(weekly_game, regular_user.id)
        assert game_service.can_manage_players(weekly_game, regular_user.id, is_admin=True)
        assert not game_service.can_manage_players(weekly_game, None)
