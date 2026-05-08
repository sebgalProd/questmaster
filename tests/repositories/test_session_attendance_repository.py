"""Tests for SessionAttendanceRepository."""

from tests.factories import GameFactory, GameSessionFactory
from website.models import SessionAttendance
from website.repositories.session_attendance import SessionAttendanceRepository


class TestSessionAttendanceRepository:
    def test_upsert_creates(self, db_session, admin_user, default_system):
        game = GameFactory(db_session, gm_id=admin_user.id, system_id=default_system.id)
        session = GameSessionFactory(db_session, game_id=game.id)
        repo = SessionAttendanceRepository()
        record = repo.upsert(session.id, admin_user.id, True)
        assert record.id is not None
        assert record.is_present is True

    def test_upsert_updates(self, db_session, admin_user, default_system):
        game = GameFactory(db_session, gm_id=admin_user.id, system_id=default_system.id)
        session = GameSessionFactory(db_session, game_id=game.id)
        repo = SessionAttendanceRepository()
        repo.upsert(session.id, admin_user.id, True)
        updated = repo.upsert(session.id, admin_user.id, False)
        assert updated.is_present is False
        assert db_session.query(SessionAttendance).filter_by(session_id=session.id).count() == 1

    def test_find_by_session(self, db_session, admin_user, default_system):
        game = GameFactory(db_session, gm_id=admin_user.id, system_id=default_system.id)
        session = GameSessionFactory(db_session, game_id=game.id)
        repo = SessionAttendanceRepository()
        repo.upsert(session.id, admin_user.id, True)
        results = repo.find_by_session(session.id)
        assert len(results) == 1
        assert results[0].user_id == admin_user.id

    def test_find_by_session_and_user(self, db_session, admin_user, default_system):
        game = GameFactory(db_session, gm_id=admin_user.id, system_id=default_system.id)
        session = GameSessionFactory(db_session, game_id=game.id)
        repo = SessionAttendanceRepository()
        repo.upsert(session.id, admin_user.id, False)
        record = repo.find_by_session_and_user(session.id, admin_user.id)
        assert record is not None
        assert record.is_present is False

    def test_find_by_session_and_user_missing(self, db_session, admin_user, default_system):
        game = GameFactory(db_session, gm_id=admin_user.id, system_id=default_system.id)
        session = GameSessionFactory(db_session, game_id=game.id)
        repo = SessionAttendanceRepository()
        assert repo.find_by_session_and_user(session.id, admin_user.id) is None

    def test_delete_by_game_and_user(self, db_session, admin_user, default_system):
        game = GameFactory(db_session, gm_id=admin_user.id, system_id=default_system.id)
        s1 = GameSessionFactory(db_session, game_id=game.id)
        s2 = GameSessionFactory(
            db_session, game_id=game.id,
            start=s1.start.replace(day=s1.start.day + 1),
            end=s1.end.replace(day=s1.end.day + 1),
        )
        repo = SessionAttendanceRepository()
        repo.upsert(s1.id, admin_user.id, True)
        repo.upsert(s2.id, admin_user.id, False)
        repo.delete_by_game_and_user(game.id, admin_user.id)
        db_session.flush()
        assert db_session.query(SessionAttendance).filter_by(user_id=admin_user.id).count() == 0
