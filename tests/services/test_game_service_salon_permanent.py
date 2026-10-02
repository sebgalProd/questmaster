"""Tests for permanent games and salons in GameService."""

from datetime import datetime
from unittest.mock import patch

import pytest

from config.constants import GAME_LENGTH_PERMANENT, SALON_PARTY_SIZE
from website.exceptions import ValidationError
from website.services.channel import ChannelService


def _form_data(**overrides):
    data = {
        "name": "Annonce",
        "type": "oneshot",
        "length": "1 session",
        "system": None,
        "description": "Description",
        "restriction": "all",
        "party_size": 4,
        "xp": "all",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "session_length": 3.5,
        "characters": "self",
    }
    data.update(overrides)
    return data


@pytest.fixture(autouse=True)
def _mock_form_parsers():
    with (
        patch("website.utils.form_parsers.get_classification", return_value={}),
        patch("website.utils.form_parsers.get_ambience", return_value=[]),
        patch("website.utils.form_parsers.parse_restriction_tags", return_value=None),
    ):
        yield


class TestPermanentGame:
    def test_create_permanent_game_has_no_date_nor_duration(
        self, db_session, admin_user, default_system, game_service
    ):
        data = _form_data(system=default_system.id, permanent="on")
        # Date fields are disabled in the form, so they are not submitted
        for key in ("date", "length", "session_length"):
            data.pop(key)

        game = game_service.create(data, admin_user.id)

        assert game.permanent is True
        assert game.date is None
        assert game.session_length is None
        assert game.length == GAME_LENGTH_PERMANENT
        assert game.system_id == default_system.id

    def test_publish_permanent_game_creates_no_session(
        self, db_session, admin_user, default_system, oneshot_channel, game_service
    ):
        data = _form_data(system=default_system.id, permanent="on")
        game = game_service.create(data, admin_user.id)

        game = game_service.publish(game.slug)

        assert game.status == "open"
        assert game.sessions == []

    def test_game_without_system_is_rejected(self, db_session, admin_user, game_service):
        with pytest.raises(ValidationError):
            game_service.create(_form_data(system=None), admin_user.id)

    def test_update_game_to_permanent(self, db_session, admin_user, default_system, game_service):
        game = game_service.create(_form_data(system=default_system.id), admin_user.id)
        assert game.permanent is False

        game = game_service.update(game.slug, _form_data(system=default_system.id, permanent="on"))

        assert game.permanent is True
        assert game.date is None


class TestSalon:
    def test_create_salon(self, db_session, admin_user, game_service):
        data = {
            "name": "bitcoin",
            "type": "salon",
            "description": "Le salon où on parle de bitcoin.",
            "restriction": "all",
        }

        salon = game_service.create(data, admin_user.id)

        assert salon.type == "salon"
        assert salon.is_salon is True
        assert salon.permanent is True
        assert salon.date is None
        assert salon.system_id is None
        assert salon.party_size == SALON_PARTY_SIZE
        assert salon.slug == f"bitcoin-par-{admin_user.username}"

    def test_publish_salon(
        self, db_session, admin_user, oneshot_channel, mock_discord, game_service
    ):
        salon = game_service.create(
            {
                "name": "la chouette d'or",
                "type": "salon",
                "description": "On cherche la chouette.",
                "restriction": "all",
            },
            admin_user.id,
        )

        salon = game_service.publish(salon.slug)

        assert salon.status == "open"
        assert salon.sessions == []
        role_name = mock_discord.create_role.call_args.kwargs["name"]
        assert role_name.startswith("Membre_")


class TestCategoryFallback:
    def test_salon_falls_back_to_oneshot_category(self, db_session, oneshot_channel):
        category = ChannelService().get_category("salon")
        assert category.type == "oneshot"
