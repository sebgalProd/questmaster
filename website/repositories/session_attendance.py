"""SessionAttendance repository for attendance data access."""

from website.models import GameSession, SessionAttendance
from website.repositories.base import BaseRepository


class SessionAttendanceRepository(BaseRepository[SessionAttendance]):
    """Repository for SessionAttendance entities."""

    model_class = SessionAttendance

    def find_by_session(self, session_id: int) -> list[SessionAttendance]:
        """Return all attendance records for a session.

        Args:
            session_id: GameSession primary key.

        Returns:
            List of SessionAttendance instances.
        """
        return (
            self.session.query(SessionAttendance)
            .filter_by(session_id=session_id)
            .all()
        )

    def find_by_session_and_user(
        self, session_id: int, user_id: str
    ) -> SessionAttendance | None:
        """Return the attendance record for a specific player and session.

        Args:
            session_id: GameSession primary key.
            user_id: User primary key.

        Returns:
            SessionAttendance instance or None.
        """
        return (
            self.session.query(SessionAttendance)
            .filter_by(session_id=session_id, user_id=user_id)
            .first()
        )

    def upsert(
        self, session_id: int, user_id: str, is_present: bool
    ) -> SessionAttendance:
        """Create or update an attendance record.

        Args:
            session_id: GameSession primary key.
            user_id: User primary key.
            is_present: True = present, False = absent.

        Returns:
            Created or updated SessionAttendance instance.
        """
        existing = self.find_by_session_and_user(session_id, user_id)
        if existing:
            existing.is_present = is_present
            self.session.flush()
            return existing
        record = SessionAttendance(
            session_id=session_id, user_id=user_id, is_present=is_present
        )
        self.session.add(record)
        self.session.flush()
        return record

    def delete_by_game_and_user(self, game_id: int, user_id: str) -> None:
        """Delete all attendance records for a user across all sessions of a game.

        Called when a player unregisters from a game.

        Args:
            game_id: Game primary key.
            user_id: User primary key.
        """
        session_ids = self.session.query(GameSession.id).filter_by(game_id=game_id)
        self.session.query(SessionAttendance).filter(
            SessionAttendance.session_id.in_(session_ids),
            SessionAttendance.user_id == user_id,
        ).delete(synchronize_session=False)
        self.session.flush()
