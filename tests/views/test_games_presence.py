"""Tests for session presence routes."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.factories import GameFactory, GameSessionFactory
from website.models import SessionAttendance


class TestPresenceRoutes:
    @pytest.fixture
    def open_game(self, db_session, admin_user, regular_user, default_system):
        game = GameFactory(
            db_session,
            gm_id=admin_user.id,
            system_id=default_system.id,
            status="open",
            channel="123456789",
            role="987654321",
        )
        game.players.append(regular_user)
        db_session.commit()
        return game

    @pytest.fixture
    def future_session(self, db_session, open_game):
        future = datetime.now(timezone.utc) + timedelta(days=7)
        session = GameSessionFactory(
            db_session,
            game_id=open_game.id,
            start=future.replace(tzinfo=None),
            end=(future + timedelta(hours=3)).replace(tzinfo=None),
        )
        return session

    @pytest.fixture
    def past_session(self, db_session, open_game):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        session = GameSessionFactory(
            db_session,
            game_id=open_game.id,
            start=past.replace(tzinfo=None),
            end=(past + timedelta(hours=3)).replace(tzinfo=None),
        )
        return session

    def test_player_marks_absent(
        self,
        db_session,
        logged_in_user,
        mock_csrf,
        mock_discord_service,
        open_game,
        future_session,
    ):
        response = logged_in_user.post(
            f"/annonces/{open_game.slug}/sessions/{future_session.id}/presence/",
            data={"is_present": "0"},
        )
        assert response.status_code == 302
        record = (
            db_session.query(SessionAttendance).filter_by(session_id=future_session.id).first()
        )
        assert record is not None
        assert record.is_present is False

    def test_player_marks_present(
        self,
        db_session,
        logged_in_user,
        mock_csrf,
        mock_discord_service,
        open_game,
        future_session,
    ):
        response = logged_in_user.post(
            f"/annonces/{open_game.slug}/sessions/{future_session.id}/presence/",
            data={"is_present": "1"},
        )
        assert response.status_code == 302
        record = (
            db_session.query(SessionAttendance).filter_by(session_id=future_session.id).first()
        )
        assert record.is_present is True

    def test_player_cannot_set_attendance_on_past_session(
        self, db_session, logged_in_user, mock_csrf, mock_discord_service, open_game, past_session
    ):
        response = logged_in_user.post(
            f"/annonces/{open_game.slug}/sessions/{past_session.id}/presence/",
            data={"is_present": "0"},
            follow_redirects=True,
        )
        assert b"pass" in response.data or response.status_code in (302, 403)
        assert (
            db_session.query(SessionAttendance).filter_by(session_id=past_session.id).count() == 0
        )

    def test_unregistered_player_cannot_set_attendance(
        self,
        db_session,
        logged_in_admin,
        mock_csrf,
        mock_discord_service,
        open_game,
        future_session,
    ):
        # admin_user is GM, not in game.players
        logged_in_admin.post(
            f"/annonces/{open_game.slug}/sessions/{future_session.id}/presence/",
            data={"is_present": "0"},
            follow_redirects=True,
        )
        assert (
            db_session.query(SessionAttendance).filter_by(session_id=future_session.id).count()
            == 0
        )

    def test_gm_marks_attendance_for_player(
        self,
        db_session,
        logged_in_admin,
        mock_csrf,
        mock_discord_service,
        open_game,
        future_session,
        regular_user,
    ):
        response = logged_in_admin.post(
            f"/annonces/{open_game.slug}/sessions/{future_session.id}/presence/{regular_user.id}/",
            data={"is_present": "0"},
        )
        assert response.status_code == 302
        record = (
            db_session.query(SessionAttendance)
            .filter_by(session_id=future_session.id, user_id=regular_user.id)
            .first()
        )
        assert record is not None
        assert record.is_present is False

    def test_non_gm_cannot_set_attendance_for_player(
        self,
        db_session,
        logged_in_user,
        mock_csrf,
        mock_discord_service,
        open_game,
        future_session,
        admin_user,
    ):
        logged_in_user.post(
            f"/annonces/{open_game.slug}/sessions/{future_session.id}/presence/{admin_user.id}/",
            data={"is_present": "0"},
            follow_redirects=True,
        )
        assert (
            db_session.query(SessionAttendance).filter_by(session_id=future_session.id).count()
            == 0
        )
