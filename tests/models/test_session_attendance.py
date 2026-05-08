"""Tests for SessionAttendance model."""

import pytest
from sqlalchemy.exc import IntegrityError

from tests.factories import GameFactory, GameSessionFactory
from website.models import SessionAttendance


class TestSessionAttendanceModel:
    def test_create(self, db_session, admin_user, default_system):
        game = GameFactory(db_session, gm_id=admin_user.id, system_id=default_system.id)
        session = GameSessionFactory(db_session, game_id=game.id)
        record = SessionAttendance(
            session_id=session.id, user_id=admin_user.id, is_present=True
        )
        db_session.add(record)
        db_session.flush()
        assert record.id is not None
        assert record.is_present is True

    def test_unique_constraint(self, db_session, admin_user, default_system):
        game = GameFactory(db_session, gm_id=admin_user.id, system_id=default_system.id)
        session = GameSessionFactory(db_session, game_id=game.id)
        db_session.add(
            SessionAttendance(session_id=session.id, user_id=admin_user.id, is_present=True)
        )
        db_session.flush()
        db_session.add(
            SessionAttendance(session_id=session.id, user_id=admin_user.id, is_present=False)
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
