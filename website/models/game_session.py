"""GameSession model for scheduled play sessions."""

from sqlalchemy import Enum

from config.constants import SESSION_LOCATION_TYPES
from website.extensions import db
from website.models.base import SerializableMixin


class GameSession(db.Model, SerializableMixin):
    """A scheduled play session belonging to a Game.

    Attributes:
        id: Primary key.
        game_id: Foreign key to the parent game.
        start: Session start datetime.
        end: Session end datetime.
        location_type: Type of location (online or inperson), nullable.
        location_label: Optional free-text label for the location (e.g. "Discord", "Salle B12").
        location_url: Optional URL (Google Maps or invite link).
    """

    __tablename__ = "game_session"

    _exclude_fields = []
    _relationship_fields = []

    id = db.Column(db.BigInteger, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"))
    start = db.Column(db.DateTime, nullable=False)
    end = db.Column(db.DateTime, nullable=False)
    location_type = db.Column(
        "location_type",
        Enum(*SESSION_LOCATION_TYPES, name="session_location_enum"),
        nullable=True,
    )
    location_label = db.Column(db.String(), nullable=True)
    location_url = db.Column(db.String(), nullable=True)

    @classmethod
    def from_dict(cls, data):
        """Create a GameSession instance from a dictionary.

        Args:
            data: Dictionary with session field values.

        Returns:
            A new GameSession instance.
        """
        return cls(
            id=data.get("id"),
            game_id=data.get("game_id"),
            start=data.get("start"),
            end=data.get("end"),
            location_type=data.get("location_type"),
            location_label=data.get("location_label"),
            location_url=data.get("location_url"),
        )

    def update_from_dict(self, data):
        """Update this instance from a dictionary.

        Args:
            data: Dictionary with fields to update.

        Returns:
            This GameSession instance.
        """
        super().update_from_dict(data)
        return self
