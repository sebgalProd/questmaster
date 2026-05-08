"""SessionAttendance model for per-session player presence tracking."""

from website.extensions import db
from website.models.base import SerializableMixin


class SessionAttendance(db.Model, SerializableMixin):
    """Tracks whether a player will attend a specific game session.

    Attributes:
        id: Primary key.
        session_id: Foreign key to the parent GameSession.
        user_id: Foreign key to the User.
        is_present: True = present, False = absent. Missing row = no response.
    """

    __tablename__ = "session_attendance"

    _exclude_fields = []
    _relationship_fields = []

    id = db.Column(db.BigInteger, primary_key=True)
    session_id = db.Column(
        db.BigInteger,
        db.ForeignKey("game_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.String(),
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_present = db.Column(db.Boolean, nullable=False)

    session = db.relationship("GameSession", backref="attendances")

    __table_args__ = (
        db.UniqueConstraint("session_id", "user_id", name="uix_session_user_attendance"),
    )
