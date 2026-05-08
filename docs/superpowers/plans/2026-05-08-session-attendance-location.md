# Session Attendance & Location — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-session location (online/inperson) and per-session player attendance (present/absent) to QuestMaster.

**Architecture:** Two independent additions to `GameSession`: three new nullable columns for location, and a new `session_attendance` join table. Attendance is managed via a new `SessionAttendanceRepository` and new methods on `GameSessionService`. Discord notification fires only when a player marks themselves absent.

**Tech Stack:** Flask 3.1, SQLAlchemy/Alembic, PostgreSQL, Bootstrap 5, Jinja2, pytest

---

## File Map

**Create:**
- `website/models/session_attendance.py` — `SessionAttendance` ORM model
- `website/repositories/session_attendance.py` — `SessionAttendanceRepository`
- `website/templates/game_details/session_attendance.j2` — attendance section partial (player buttons + GM list)
- `tests/models/test_session_attendance.py`
- `tests/repositories/test_session_attendance_repository.py`
- `tests/views/test_games_presence.py`

**Modify:**
- `config/constants.py` — add `SESSION_LOCATION_*` constants
- `website/models/game_session.py` — add 3 location columns
- `website/models/__init__.py` — export `SessionAttendance`
- `website/repositories/__init__.py` — export `SessionAttendanceRepository`
- `website/services/game_session.py` — add `discord_service` injection, `set_attendance`, `get_attendance_summary`, location params on `create`/`update`
- `website/services/game.py` — delete attendance records in `unregister_player`
- `website/utils/game_embeds.py` — add `build_attendance_alert_embed`, register in `send_game_embed`
- `website/views/games.py` — update `session_service` instantiation, add 2 presence routes, pass location in `add_game_session`/`edit_game_session`, pass `attendance_summaries` in `get_game_details`
- `website/templates/game_details/add_session.j2` — add location fields
- `website/templates/game_details/edit_session.j2` — add location fields
- `website/templates/game_details.j2` — add location badge and include attendance partial per session

---

## Task 1: Constants + Location Columns + Model

**Files:**
- Modify: `config/constants.py`
- Modify: `website/models/game_session.py`

- [ ] **Step 1: Add location constants to `config/constants.py`**

Find the end of the constants file (after the existing enums) and add:

```python
# Session Location
SESSION_LOCATION_ONLINE = "online"
SESSION_LOCATION_INPERSON = "inperson"
SESSION_LOCATION_TYPES = (SESSION_LOCATION_ONLINE, SESSION_LOCATION_INPERSON)
```

- [ ] **Step 2: Add location columns to `GameSession` model**

In `website/models/game_session.py`, add the `Enum` import and three new columns:

```python
"""GameSession model for scheduled play sessions."""

from sqlalchemy import Enum

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
        location_label: Free text label, required when location_type is set.
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
        Enum("online", "inperson", name="session_location_enum"),
        nullable=True,
    )
    location_label = db.Column(db.String(), nullable=True)
    location_url = db.Column(db.String(), nullable=True)

    @classmethod
    def from_dict(cls, data):
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
        super().update_from_dict(data)
        return self
```

- [ ] **Step 3: Generate and apply the migration**

```bash
source .venv/bin/activate && set -a && source .env && set +a
flask db revision --autogenerate -m "add location fields to game_session"
flask db upgrade
```

Verify the generated migration file in `migrations/versions/` contains `add_column` calls for `location_type`, `location_label`, `location_url` and a `CREATE TYPE session_location_enum`. If autogenerate misses the enum, edit the migration manually:

```python
def upgrade():
    op.execute("CREATE TYPE session_location_enum AS ENUM ('online', 'inperson')")
    op.add_column('game_session', sa.Column('location_type',
        sa.Enum('online', 'inperson', name='session_location_enum'), nullable=True))
    op.add_column('game_session', sa.Column('location_label', sa.String(), nullable=True))
    op.add_column('game_session', sa.Column('location_url', sa.String(), nullable=True))

def downgrade():
    op.drop_column('game_session', 'location_url')
    op.drop_column('game_session', 'location_label')
    op.drop_column('game_session', 'location_type')
    op.execute("DROP TYPE session_location_enum")
```

- [ ] **Step 4: Run existing tests to confirm no regression**

```bash
python -m pytest tests/ -m "not integration" -q
```

Expected: same pass count as before (≥593 passed).

- [ ] **Step 5: Commit**

```bash
git add config/constants.py website/models/game_session.py migrations/
git commit -m "feat(session): add location columns to game_session"
```

---

## Task 2: Location Validation in GameSessionService

**Files:**
- Modify: `website/services/game_session.py`
- Test: `tests/services/test_game_session_service.py`

- [ ] **Step 1: Write failing tests for location validation**

Add to `tests/services/test_game_session_service.py` inside `TestGameSessionService`:

```python
def test_create_with_valid_location(self, db_session, sample_game):
    service = GameSessionService()
    start = datetime(2025, 12, 1, 20, 0)
    end = datetime(2025, 12, 1, 23, 0)
    session = service.create(
        sample_game, start, end,
        location_type="online", location_label="Discord"
    )
    assert session.location_type == "online"
    assert session.location_label == "Discord"
    assert session.location_url is None

def test_create_location_type_without_label_raises(self, db_session, sample_game):
    service = GameSessionService()
    start = datetime(2025, 12, 2, 20, 0)
    end = datetime(2025, 12, 2, 23, 0)
    with pytest.raises(ValidationError):
        service.create(sample_game, start, end, location_type="online", location_label="")

def test_update_location(self, db_session, sample_game):
    service = GameSessionService()
    session = service.create(
        sample_game, datetime(2025, 12, 3, 20, 0), datetime(2025, 12, 3, 23, 0)
    )
    updated = service.update(
        session,
        datetime(2025, 12, 3, 20, 0),
        datetime(2025, 12, 3, 23, 0),
        location_type="inperson",
        location_label="Salle B12",
        location_url="https://maps.google.com/test",
    )
    assert updated.location_type == "inperson"
    assert updated.location_label == "Salle B12"
    assert updated.location_url == "https://maps.google.com/test"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/services/test_game_session_service.py::TestGameSessionService::test_create_with_valid_location tests/services/test_game_session_service.py::TestGameSessionService::test_create_location_type_without_label_raises -v
```

Expected: FAIL — `create()` does not accept location kwargs yet.

- [ ] **Step 3: Update `GameSessionService.create` and `update`**

In `website/services/game_session.py`, update both methods:

```python
def create(
    self,
    game: Game,
    start: datetime,
    end: datetime,
    location_type: str | None = None,
    location_label: str | None = None,
    location_url: str | None = None,
) -> GameSession:
    """Create a new game session.

    Args:
        game: Game instance to add the session to.
        start: Session start datetime.
        end: Session end datetime.
        location_type: 'online' or 'inperson', or None.
        location_label: Required when location_type is set.
        location_url: Optional URL.

    Returns:
        Created GameSession instance.

    Raises:
        ValidationError: If start >= end or location_type set without label.
        SessionConflictError: If the session overlaps with an existing one.
    """
    if start >= end:
        raise ValidationError("Session start must be before end time.")

    if location_type and not location_label:
        raise ValidationError(
            "Le lieu doit avoir un nom.", field="location_label"
        )

    if self._has_conflict(game, start, end):
        raise SessionConflictError(
            "Session overlaps with an existing session.", game_id=game.id
        )

    session = GameSession(
        start=start,
        end=end,
        location_type=location_type,
        location_label=location_label,
        location_url=location_url,
    )
    self.repo.add(session)
    game.sessions.append(session)
    db.session.commit()
    logger.info(f"Session added for game {game.id} from {start} to {end}")
    return session


def update(
    self,
    session: GameSession,
    new_start: datetime,
    new_end: datetime,
    location_type: str | None = None,
    location_label: str | None = None,
    location_url: str | None = None,
) -> GameSession:
    """Update a session's start/end times and optional location.

    Args:
        session: Existing GameSession instance.
        new_start: New start datetime.
        new_end: New end datetime.
        location_type: 'online' or 'inperson', or None to clear.
        location_label: Required when location_type is set.
        location_url: Optional URL.

    Returns:
        Updated GameSession instance.

    Raises:
        ValidationError: If new_start >= new_end or location_type set without label.
        SessionConflictError: If new times overlap another session.
    """
    if new_start >= new_end:
        raise ValidationError("Session start must be before end time.")

    if location_type and not location_label:
        raise ValidationError(
            "Le lieu doit avoir un nom.", field="location_label"
        )

    game = session.game
    if self._has_conflict(game, new_start, new_end, exclude_session_id=session.id):
        raise SessionConflictError(
            "Session overlaps with an existing session.", game_id=game.id
        )

    session.start = new_start
    session.end = new_end
    session.location_type = location_type
    session.location_label = location_label
    session.location_url = location_url
    db.session.commit()
    logger.info(f"Session {session.id} updated to {new_start} - {new_end}")
    return session
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/services/test_game_session_service.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add website/services/game_session.py tests/services/test_game_session_service.py
git commit -m "feat(session): add location validation to GameSessionService"
```

---

## Task 3: SessionAttendance Model + Migration

**Files:**
- Create: `website/models/session_attendance.py`
- Modify: `website/models/__init__.py`
- Test: `tests/models/test_session_attendance.py`

- [ ] **Step 1: Write failing model test**

Create `tests/models/test_session_attendance.py`:

```python
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
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/models/test_session_attendance.py -v
```

Expected: FAIL — `SessionAttendance` not defined.

- [ ] **Step 3: Create `website/models/session_attendance.py`**

```python
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
```

- [ ] **Step 4: Register in `website/models/__init__.py`**

```python
"""SQLAlchemy model definitions for QuestMaster."""

from .channel import Channel
from .game import Game
from .game_event import GameEvent
from .game_session import GameSession
from .session_attendance import SessionAttendance
from .special_event import SpecialEvent
from .system import System
from .trophy import Trophy, UserTrophy
from .user import User
from .vtt import Vtt

__all__ = [
    "Channel",
    "Game",
    "GameEvent",
    "GameSession",
    "SessionAttendance",
    "SpecialEvent",
    "System",
    "Trophy",
    "UserTrophy",
    "User",
    "Vtt",
]
```

- [ ] **Step 5: Generate and apply migration**

```bash
flask db revision --autogenerate -m "add session_attendance table"
flask db upgrade
```

Verify the migration creates `session_attendance` with both FK cascades and the unique constraint. If autogenerate misses cascade, edit manually:

```python
def upgrade():
    op.create_table(
        'session_attendance',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('session_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('is_present', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['game_session.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'user_id', name='uix_session_user_attendance'),
    )

def downgrade():
    op.drop_table('session_attendance')
```

- [ ] **Step 6: Run model tests**

```bash
python -m pytest tests/models/test_session_attendance.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add website/models/session_attendance.py website/models/__init__.py migrations/ tests/models/test_session_attendance.py
git commit -m "feat(session): add SessionAttendance model and migration"
```

---

## Task 4: SessionAttendanceRepository

**Files:**
- Create: `website/repositories/session_attendance.py`
- Modify: `website/repositories/__init__.py`
- Test: `tests/repositories/test_session_attendance_repository.py`

- [ ] **Step 1: Write failing tests**

Create `tests/repositories/test_session_attendance_repository.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/repositories/test_session_attendance_repository.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create `website/repositories/session_attendance.py`**

```python
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
        session_ids = (
            self.session.query(GameSession.id).filter_by(game_id=game_id).subquery()
        )
        self.session.query(SessionAttendance).filter(
            SessionAttendance.session_id.in_(session_ids),
            SessionAttendance.user_id == user_id,
        ).delete(synchronize_session=False)
        self.session.flush()
```

- [ ] **Step 4: Register in `website/repositories/__init__.py`**

```python
"""Repository layer for data access operations."""

from website.repositories.base import BaseRepository
from website.repositories.channel import ChannelRepository
from website.repositories.game import GameRepository
from website.repositories.game_event import GameEventRepository
from website.repositories.game_session import GameSessionRepository
from website.repositories.session_attendance import SessionAttendanceRepository
from website.repositories.special_event import SpecialEventRepository
from website.repositories.system import SystemRepository
from website.repositories.trophy import TrophyRepository
from website.repositories.user import UserRepository
from website.repositories.vtt import VttRepository

__all__ = [
    "BaseRepository",
    "SystemRepository",
    "VttRepository",
    "ChannelRepository",
    "GameEventRepository",
    "UserRepository",
    "GameSessionRepository",
    "SessionAttendanceRepository",
    "SpecialEventRepository",
    "TrophyRepository",
    "GameRepository",
]
```

- [ ] **Step 5: Run repository tests**

```bash
python -m pytest tests/repositories/test_session_attendance_repository.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add website/repositories/session_attendance.py website/repositories/__init__.py tests/repositories/test_session_attendance_repository.py
git commit -m "feat(session): add SessionAttendanceRepository"
```

---

## Task 5: Attendance Methods on GameSessionService

**Files:**
- Modify: `website/services/game_session.py`
- Test: `tests/services/test_game_session_service.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/services/test_game_session_service.py`:

```python
class TestSessionAttendanceService:
    @pytest.fixture
    def session_svc(self, mock_discord):
        from website.services.game_session import GameSessionService
        return GameSessionService(discord_service=mock_discord)

    def test_set_attendance_absent_triggers_discord(
        self, db_session, sample_game, session_svc, mock_discord, admin_user
    ):
        from datetime import timedelta
        session = session_svc.create(
            sample_game,
            sample_game.date,
            sample_game.date + timedelta(hours=3),
        )
        sample_game.players.append(admin_user)
        db_session.commit()
        session_svc.set_attendance(session, admin_user.id, False, by_gm=False)
        mock_discord.send_game_embed.assert_called_once()
        call_kwargs = mock_discord.send_game_embed.call_args[1]
        assert call_kwargs["embed_type"] == "attendance-alert"

    def test_set_attendance_present_no_discord(
        self, db_session, sample_game, session_svc, mock_discord, admin_user
    ):
        from datetime import timedelta
        session = session_svc.create(
            sample_game,
            sample_game.date,
            sample_game.date + timedelta(hours=3),
        )
        sample_game.players.append(admin_user)
        db_session.commit()
        session_svc.set_attendance(session, admin_user.id, True, by_gm=False)
        mock_discord.send_game_embed.assert_not_called()

    def test_set_attendance_by_gm_no_discord(
        self, db_session, sample_game, session_svc, mock_discord, admin_user
    ):
        from datetime import timedelta
        session = session_svc.create(
            sample_game,
            sample_game.date,
            sample_game.date + timedelta(hours=3),
        )
        sample_game.players.append(admin_user)
        db_session.commit()
        session_svc.set_attendance(session, admin_user.id, False, by_gm=True)
        mock_discord.send_game_embed.assert_not_called()

    def test_set_attendance_toggle_resets_to_no_response(
        self, db_session, sample_game, session_svc, mock_discord, admin_user
    ):
        from datetime import timedelta
        from website.repositories.session_attendance import SessionAttendanceRepository
        session = session_svc.create(
            sample_game,
            sample_game.date,
            sample_game.date + timedelta(hours=3),
        )
        sample_game.players.append(admin_user)
        db_session.commit()
        session_svc.set_attendance(session, admin_user.id, True)
        session_svc.set_attendance(session, admin_user.id, True)  # toggle off
        repo = SessionAttendanceRepository()
        assert repo.find_by_session_and_user(session.id, admin_user.id) is None

    def test_set_attendance_unregistered_player_raises(
        self, db_session, sample_game, session_svc, admin_user
    ):
        from datetime import timedelta
        session = session_svc.create(
            sample_game,
            sample_game.date,
            sample_game.date + timedelta(hours=3),
        )
        with pytest.raises(ValidationError):
            session_svc.set_attendance(session, admin_user.id, True)

    def test_get_attendance_summary(
        self, db_session, sample_game, session_svc, admin_user, regular_user
    ):
        from datetime import timedelta
        session = session_svc.create(
            sample_game,
            sample_game.date,
            sample_game.date + timedelta(hours=3),
        )
        sample_game.players.extend([admin_user, regular_user])
        db_session.commit()
        session_svc.set_attendance(session, admin_user.id, True)
        summary = session_svc.get_attendance_summary(session)
        assert summary[admin_user.id] is True
        assert summary[regular_user.id] is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/services/test_game_session_service.py::TestSessionAttendanceService -v
```

Expected: FAIL — `set_attendance` not defined.

- [ ] **Step 3: Update `GameSessionService.__init__` and add methods**

In `website/services/game_session.py`, update the class definition:

```python
class GameSessionService:
    """Service layer for GameSession operations."""

    def __init__(self, repository=None, discord_service=None):
        self.repo = repository or GameSessionRepository()
        self._discord_service = discord_service

    @property
    def discord_service(self):
        if self._discord_service is None:
            from website.services.discord import DiscordService
            self._discord_service = DiscordService()
        return self._discord_service
```

Then add these two methods to the class (before `_has_conflict`):

```python
def set_attendance(
    self,
    session: GameSession,
    user_id: str,
    is_present: bool,
    by_gm: bool = False,
) -> None:
    """Set or toggle a player's attendance for a session.

    Args:
        session: GameSession instance.
        user_id: ID of the player.
        is_present: True = present, False = absent.
        by_gm: If True, suppress Discord notification.

    Raises:
        ValidationError: If user is not registered in the game.
    """
    from config.constants import HUMAN_TIMEFORMAT
    from website.repositories.session_attendance import SessionAttendanceRepository

    registered_ids = [p.id for p in session.game.players]
    if user_id not in registered_ids:
        raise ValidationError(
            "User is not registered for this game.", field="user_id"
        )

    repo = SessionAttendanceRepository()
    existing = repo.find_by_session_and_user(session.id, user_id)

    if existing and existing.is_present == is_present:
        repo.delete(existing)
        db.session.commit()
        return

    repo.upsert(session.id, user_id, is_present)
    db.session.commit()

    if not is_present and not by_gm:
        self.discord_service.send_game_embed(
            session.game,
            embed_type="attendance-alert",
            player=user_id,
            start=session.start.strftime(HUMAN_TIMEFORMAT),
            end=session.end.strftime(HUMAN_TIMEFORMAT),
        )

def get_attendance_summary(self, session: GameSession) -> dict:
    """Return attendance status for all registered players.

    Args:
        session: GameSession instance.

    Returns:
        Dict mapping user_id to True (present), False (absent), or None (no response).
    """
    from website.repositories.session_attendance import SessionAttendanceRepository

    repo = SessionAttendanceRepository()
    records = repo.find_by_session(session.id)
    attendance_map = {r.user_id: r.is_present for r in records}
    return {
        player.id: attendance_map.get(player.id, None)
        for player in session.game.players
    }
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/services/test_game_session_service.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add website/services/game_session.py tests/services/test_game_session_service.py
git commit -m "feat(session): add set_attendance and get_attendance_summary to GameSessionService"
```

---

## Task 6: Discord Embed + Unregister Cleanup

**Files:**
- Modify: `website/utils/game_embeds.py`
- Modify: `website/services/game.py`
- Test: `tests/services/test_game_service.py`

- [ ] **Step 1: Add `build_attendance_alert_embed` to `game_embeds.py`**

In `website/utils/game_embeds.py`, add after `build_delete_session_embed`:

```python
def build_attendance_alert_embed(
    game,
    start=None,
    end=None,
    player=None,
    old_start=None,
    old_end=None,
    alert_message=None,
) -> tuple[dict, str]:
    """Build embed notifying the GM that a player will be absent.

    Args:
        game: Game instance.
        start: Session start formatted string.
        player: User ID of the absent player.

    Returns:
        Tuple of (embed dict, game channel ID).
    """
    embed = {
        "title": "Absence signalée",
        "color": EMBED_COLOR_YELLOW,
        "description": (
            f"<@{player}> ne sera pas présent·e pour la session du **{start}**."
        ),
    }
    return embed, game.channel
```

Then register it in `send_game_embed` — find the `embed_builders` dict and add the new entry:

```python
embed_builders = {
    "annonce": build_annonce_embed,
    "annonce_details": build_annonce_details_embed,
    "add-session": build_add_session_embed,
    "edit-session": build_edit_session_embed,
    "del-session": build_delete_session_embed,
    "attendance-alert": build_attendance_alert_embed,
    "register": build_register_embed,
    "alert": build_alert_embed,
}
```

Also add the import at the top of `send_game_embed`:

```python
from website.utils.game_embeds import (
    build_add_session_embed,
    build_alert_embed,
    build_annonce_details_embed,
    build_annonce_embed,
    build_attendance_alert_embed,
    build_delete_session_embed,
    build_edit_session_embed,
    build_register_embed,
)
```

- [ ] **Step 2: Write failing test for unregister attendance cleanup**

Add to `tests/services/test_game_service.py` inside `TestGameService`:

```python
def test_unregister_player_deletes_attendance(
    self, db_session, sample_game, game_service, mock_discord, regular_user, oneshot_channel
):
    from datetime import timedelta
    from website.repositories.session_attendance import SessionAttendanceRepository
    from website.services.game_session import GameSessionService

    session_svc = GameSessionService(discord_service=mock_discord)
    sample_game.players.append(regular_user)
    db_session.commit()

    session = session_svc.create(
        sample_game,
        sample_game.date,
        sample_game.date + timedelta(hours=3),
    )
    session_svc.set_attendance(session, regular_user.id, True)

    game_service.unregister_player(sample_game.slug, regular_user.id)

    repo = SessionAttendanceRepository()
    assert repo.find_by_session_and_user(session.id, regular_user.id) is None
```

- [ ] **Step 3: Run test to confirm it fails**

```bash
python -m pytest tests/services/test_game_service.py::TestGameService::test_unregister_player_deletes_attendance -v
```

Expected: FAIL — attendance record not deleted on unregister.

- [ ] **Step 4: Update `GameService.unregister_player`**

In `website/services/game.py`, find `unregister_player` and add the attendance cleanup before `db.session.commit()`:

```python
game.players.remove(user)

# Delete all attendance records for this user across all sessions of this game
from website.repositories.session_attendance import SessionAttendanceRepository
SessionAttendanceRepository().delete_by_game_and_user(game.id, user.id)

# Reopen if it was full
if (
    game.status == "closed"
    and len(game.players) < game.party_size
    and not game.party_selection
):
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/services/test_game_service.py -v
```

Expected: all pass including the new test.

- [ ] **Step 6: Run full suite**

```bash
python -m pytest tests/ -m "not integration" -q
```

Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add website/utils/game_embeds.py website/services/game.py tests/services/test_game_service.py
git commit -m "feat(session): add attendance-alert embed and cleanup on unregister"
```

---

## Task 7: View Routes

**Files:**
- Modify: `website/views/games.py`
- Test: `tests/views/test_games_presence.py`

- [ ] **Step 1: Write failing view tests**

Create `tests/views/test_games_presence.py`:

```python
"""Tests for session presence routes."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.factories import GameFactory, GameSessionFactory
from website.models import SessionAttendance


class TestPresenceRoutes:
    @pytest.fixture
    def open_game(self, db_session, admin_user, regular_user, default_system, default_channel):
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
        self, db_session, logged_in_user, open_game, future_session
    ):
        response = logged_in_user.post(
            f"/annonces/{open_game.slug}/sessions/{future_session.id}/presence/",
            data={"is_present": "0"},
        )
        assert response.status_code == 302
        record = db_session.query(SessionAttendance).filter_by(
            session_id=future_session.id
        ).first()
        assert record is not None
        assert record.is_present is False

    def test_player_marks_present(
        self, db_session, logged_in_user, open_game, future_session
    ):
        response = logged_in_user.post(
            f"/annonces/{open_game.slug}/sessions/{future_session.id}/presence/",
            data={"is_present": "1"},
        )
        assert response.status_code == 302
        record = db_session.query(SessionAttendance).filter_by(
            session_id=future_session.id
        ).first()
        assert record.is_present is True

    def test_player_cannot_set_attendance_on_past_session(
        self, db_session, logged_in_user, open_game, past_session
    ):
        response = logged_in_user.post(
            f"/annonces/{open_game.slug}/sessions/{past_session.id}/presence/",
            data={"is_present": "0"},
            follow_redirects=True,
        )
        assert b"pass" in response.data or response.status_code in (302, 403)
        assert db_session.query(SessionAttendance).filter_by(
            session_id=past_session.id
        ).count() == 0

    def test_unregistered_player_cannot_set_attendance(
        self, db_session, logged_in_admin, open_game, future_session
    ):
        # admin_user is not a player in open_game
        response = logged_in_admin.post(
            f"/annonces/{open_game.slug}/sessions/{future_session.id}/presence/",
            data={"is_present": "0"},
            follow_redirects=True,
        )
        assert db_session.query(SessionAttendance).filter_by(
            session_id=future_session.id
        ).count() == 0

    def test_gm_marks_attendance_for_player(
        self, db_session, logged_in_admin, open_game, future_session, regular_user
    ):
        response = logged_in_admin.post(
            f"/annonces/{open_game.slug}/sessions/{future_session.id}/presence/{regular_user.id}/",
            data={"is_present": "0"},
        )
        assert response.status_code == 302
        record = db_session.query(SessionAttendance).filter_by(
            session_id=future_session.id, user_id=regular_user.id
        ).first()
        assert record is not None
        assert record.is_present is False

    def test_non_gm_cannot_set_attendance_for_player(
        self, db_session, logged_in_user, open_game, future_session, admin_user
    ):
        response = logged_in_user.post(
            f"/annonces/{open_game.slug}/sessions/{future_session.id}/presence/{admin_user.id}/",
            data={"is_present": "0"},
            follow_redirects=True,
        )
        assert db_session.query(SessionAttendance).filter_by(
            session_id=future_session.id
        ).count() == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/views/test_games_presence.py -v
```

Expected: FAIL — routes not found (404).

- [ ] **Step 3: Add presence routes to `website/views/games.py`**

First, update the `session_service` instantiation at the top of the file (around line 46):

```python
session_service = GameSessionService(discord_service=discord_service)
```

Note: `discord_service = DiscordService()` is defined one line below — move it above `session_service`, or define `session_service` lazily. The simplest fix: just swap the two lines so `discord_service` is defined first:

```python
discord_service = DiscordService()
session_service = GameSessionService(discord_service=discord_service)
```

Then add the two presence routes after `remove_game_session`. Also add `timezone` to the imports at the top:

```python
from datetime import datetime, timezone
```

Routes to add:

```python
@game_bp.route("/annonces/<slug>/sessions/<int:session_id>/presence/", methods=["POST"])
@login_required
def set_session_presence(slug, session_id):
    """Player marks their own attendance for a session."""
    payload = who()
    game = game_service.get_by_slug_or_404(slug)
    session = session_service.get_by_id_or_404(session_id)

    if session.end < datetime.now(timezone.utc).replace(tzinfo=None):
        flash("Impossible de modifier la présence d'une session passée.", "danger")
        return redirect(url_for(GAME_DETAILS_ROUTE, slug=slug))

    is_present = bool(int(request.values.get("is_present", 0)))

    try:
        session_service.set_attendance(session, payload["user_id"], is_present, by_gm=False)
        flash("Présence mise à jour.", "success")
    except ValidationError as e:
        flash(e.message, "danger")
    except QuestMasterError:
        logger.exception("Failed to set attendance")
        flash("Une erreur est survenue.", "danger")

    return redirect(url_for(GAME_DETAILS_ROUTE, slug=slug))


@game_bp.route(
    "/annonces/<slug>/sessions/<int:session_id>/presence/<user_id>/",
    methods=["POST"],
)
@login_required
def set_session_presence_gm(slug, session_id, user_id):
    """GM marks attendance for a specific player."""
    payload = who()
    game = game_service.get_by_slug_or_404(slug)

    if payload["user_id"] != game.gm_id and not payload.get("is_admin"):
        flash("Action non autorisée.", "danger")
        return redirect(url_for(GAME_DETAILS_ROUTE, slug=slug))

    session = session_service.get_by_id_or_404(session_id)
    is_present = bool(int(request.values.get("is_present", 0)))

    try:
        session_service.set_attendance(session, user_id, is_present, by_gm=True)
        flash("Présence mise à jour.", "success")
    except ValidationError as e:
        flash(e.message, "danger")
    except QuestMasterError:
        logger.exception("Failed to set attendance for player")
        flash("Une erreur est survenue.", "danger")

    return redirect(url_for(GAME_DETAILS_ROUTE, slug=slug))
```

Also update `add_game_session` to extract and pass location fields:

```python
@game_bp.route("/annonces/<slug>/sessions/ajouter/", methods=["POST"])
@login_required
def add_game_session(slug):
    """Add session to a game and redirect to the game details."""
    payload = who()
    game = _get_game_if_authorized(payload, slug)
    start = datetime.strptime(request.values.get("date_start"), DEFAULT_TIMEFORMAT)
    end = datetime.strptime(request.values.get("date_end"), DEFAULT_TIMEFORMAT)
    location_type = request.values.get("location_type") or None
    location_label = (request.values.get("location_label") or "").strip() or None
    location_url = (request.values.get("location_url") or "").strip() or None

    try:
        session_service.create(
            game, start, end,
            location_type=location_type,
            location_label=location_label,
            location_url=location_url,
        )
        log_game_event(
            "create-session",
            game.id,
            f"Une session a été créée de {start} à {end}.",
            user_id=payload["user_id"],
        )
        logger.info(f"Session {start}/{end} created for Game {game.id}")
        discord_service.send_game_embed(game, embed_type="add-session", start=start, end=end)
        flash("Session ajoutée.", "success")
    except ValidationError as e:
        flash(e.message, "danger")
    except SessionConflictError as e:
        flash(str(e), "danger")
    except QuestMasterError:
        logger.exception("Failed to create game session")
        flash("Une erreur est survenue pendant la création de la session.", "danger")

    return redirect(url_for(GAME_DETAILS_ROUTE, slug=slug))
```

And update `edit_game_session` similarly:

```python
    new_start = datetime.strptime(request.values.get("date_start"), DEFAULT_TIMEFORMAT)
    new_end = datetime.strptime(request.values.get("date_end"), DEFAULT_TIMEFORMAT)
    location_type = request.values.get("location_type") or None
    location_label = (request.values.get("location_label") or "").strip() or None
    location_url = (request.values.get("location_url") or "").strip() or None
    # ... (rest of try block)
        session_service.update(
            session, new_start, new_end,
            location_type=location_type,
            location_label=location_label,
            location_url=location_url,
        )
```

Also update `get_game_details` to pass attendance data with pre-computed counts (Jinja2 cannot reliably count by boolean value with `selectattr`):

```python
@game_bp.route("/annonces/<slug>/", methods=["GET"])
def get_game_details(slug):
    """Display game detail page."""
    payload = who()
    game = game_service.get_by_slug_or_404(slug)
    is_player = "user_id" in payload and game_service.is_player(game, payload["user_id"])
    attendance_data = {}
    for session in game.sessions:
        summary = session_service.get_attendance_summary(session)
        attendance_data[session.id] = {
            "summary": summary,
            "present": sum(1 for v in summary.values() if v is True),
            "absent": sum(1 for v in summary.values() if v is False),
            "no_reply": sum(1 for v in summary.values() if v is None),
        }
    return render_template(
        "game_details.j2",
        game=game,
        is_player=is_player,
        attendance_data=attendance_data,
    )
```

- [ ] **Step 4: Run view tests**

```bash
python -m pytest tests/views/test_games_presence.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/ -m "not integration" -q
```

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add website/views/games.py tests/views/test_games_presence.py
git commit -m "feat(session): add presence routes and pass attendance summaries to game detail"
```

---

## Task 8: Templates

**Files:**
- Modify: `website/templates/game_details/add_session.j2`
- Modify: `website/templates/game_details/edit_session.j2`
- Create: `website/templates/game_details/session_attendance.j2`
- Modify: `website/templates/game_details.j2`

- [ ] **Step 1: Update `add_session.j2` — add location fields**

Replace the entire file content:

```html
<div class="modal fade" id="addSessionModal" tabindex="-1" aria-labelledby="addSessionModal" aria-hidden="true">
  <div class="modal-dialog modal-lg">
    <div class="modal-content">
      <div class="modal-header">
        <h1 class="modal-title fs-5">Ajouter une session</h1>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <form method="post" action="/annonces/{{game.slug}}/sessions/ajouter/" class="row">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <div class="row">
            <div class="input-group mb-3">
              <span class="input-group-text">Début :</span>
              <input id="date_start" name="date_start"
                class="flatpickr flatpickr-start flatpickr-input active form-control" type="text" autocomplete="off"
                onchange="validateDateRange('#date_start', '#date_end', 'add_session')" required>
              <span class="input-group-text">Fin :</span>
              <input name="date_end" id="date_end" class="flatpickr flatpickr-end flatpickr-input active form-control"
                type="text" autocomplete="off" onchange="validateDateRange('#date_start', '#date_end', 'add_session')"
                required>
            </div>
          </div>
          <div class="mb-3">
            <label for="add_location_type" class="form-label">Lieu</label>
            <select class="form-select" id="add_location_type" name="location_type"
              onchange="toggleLocationFields('add')">
              <option value="">Non renseigné</option>
              <option value="online">En ligne</option>
              <option value="inperson">Présentiel</option>
            </select>
          </div>
          <div id="add_location_label_group" class="mb-3" style="display:none;">
            <label for="add_location_label" class="form-label">Nom du lieu <span class="text-danger">*</span></label>
            <input type="text" class="form-control" id="add_location_label" name="location_label"
              placeholder="Ex : Discord, Salle B12...">
          </div>
          <div id="add_location_url_group" class="mb-3" style="display:none;">
            <label for="add_location_url" class="form-label">Lien Google Maps (optionnel)</label>
            <input type="url" class="form-control" id="add_location_url" name="location_url"
              placeholder="https://maps.google.com/...">
          </div>
          <div class="d-grid">
            <button id="add_session" type="submit" class="btn btn-primary" disabled>Ajouter</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</div>

<script>
function toggleLocationFields(prefix) {
  const type = document.getElementById(prefix + '_location_type').value;
  const labelGroup = document.getElementById(prefix + '_location_label_group');
  const urlGroup = document.getElementById(prefix + '_location_url_group');
  labelGroup.style.display = type ? 'block' : 'none';
  urlGroup.style.display = (type === 'inperson') ? 'block' : 'none';
  if (!type) {
    document.getElementById(prefix + '_location_label').value = '';
    document.getElementById(prefix + '_location_url') && (document.getElementById(prefix + '_location_url').value = '');
  }
}
</script>
```

- [ ] **Step 2: Update `edit_session.j2` — add location fields**

Replace the entire file:

```html
<div class="modal fade" id="editSessionModal{{session.id}}" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-lg">
    <div class="modal-content">
      <div class="modal-header">
        <h1 class="modal-title fs-5">Éditer la session du {{session.start|format_datetime}} au
          {{session.end|format_datetime}}</h1>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <form method="post" action="/annonces/{{game.slug}}/sessions/{{session.id}}/editer/" class="row">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <div class="row">
            <div class="input-group mb-3">
              <span class="input-group-text">Début :</span>
              <input id="date_start_{{session.id}}" name="date_start"
                class="flatpickr flatpickr-start flatpickr-input active form-control" type="text" autocomplete="off"
                value="{{session.start}}"
                onchange="validateDateRange('#date_start_{{session.id}}', '#date_end_{{session.id}}', 'edit_session_{{session.id}}')"
                required>
              <span class="input-group-text">Fin :</span>
              <input name="date_end" id="date_end_{{session.id}}"
                class="flatpickr flatpickr-end flatpickr-input active form-control" type="text" autocomplete="off"
                value="{{session.end}}"
                onchange="validateDateRange('#date_start_{{session.id}}', '#date_end_{{session.id}}', 'edit_session_{{session.id}}')"
                required>
            </div>
          </div>
          <div class="mb-3">
            <label class="form-label">Lieu</label>
            <select class="form-select" id="edit_location_type_{{session.id}}" name="location_type"
              onchange="toggleEditLocation({{ session.id }})">
              <option value="" {% if not session.location_type %}selected{% endif %}>Non renseigné</option>
              <option value="online" {% if session.location_type == 'online' %}selected{% endif %}>En ligne</option>
              <option value="inperson" {% if session.location_type == 'inperson' %}selected{% endif %}>Présentiel</option>
            </select>
          </div>
          <div id="edit_{{session.id}}_location_label_group" class="mb-3"
            style="display:{% if session.location_type %}block{% else %}none{% endif %};">
            <label class="form-label">Nom du lieu <span class="text-danger">*</span></label>
            <input type="text" class="form-control" id="edit_{{session.id}}_location_label" name="location_label"
              value="{{ session.location_label or '' }}" placeholder="Ex : Discord, Salle B12...">
          </div>
          <div id="edit_{{session.id}}_location_url_group" class="mb-3"
            style="display:{% if session.location_type == 'inperson' %}block{% else %}none{% endif %};">
            <label class="form-label">Lien Google Maps (optionnel)</label>
            <input type="url" class="form-control" id="edit_{{session.id}}_location_url" name="location_url"
              value="{{ session.location_url or '' }}" placeholder="https://maps.google.com/...">
          </div>
          <div class="d-grid">
            <button id="edit_session_{{session.id}}" type="submit" class="btn btn-primary" disabled>Modifier</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</div>

<script>
function toggleEditLocation(sid) {
  const type = document.getElementById('edit_location_type_' + sid).value;
  document.getElementById('edit_' + sid + '_location_label_group').style.display = type ? 'block' : 'none';
  document.getElementById('edit_' + sid + '_location_url_group').style.display = (type === 'inperson') ? 'block' : 'none';
}
</script>
```

- [ ] **Step 3: Create `website/templates/game_details/session_attendance.j2`**

```html
{# session_attendance.j2 — attendance display for a single session card
   Variables available: session, game, payload, is_player, attendance_data, now (datetime function) #}

{% set data = attendance_data[session.id] %}
{% set summary = data.summary %}
{% set current_time = now() %}
{% set is_future = session.end > current_time %}

{# Location badge #}
{% if session.location_type %}
<div class="mt-2">
  {% if session.location_type == 'online' %}
  <span class="badge bg-primary">En ligne</span>
  {% else %}
  <span class="badge bg-warning text-dark">Présentiel</span>
  {% endif %}
  {% if session.location_label %}
  <span class="ms-1 small">{{ session.location_label }}</span>
  {% endif %}
  {% if session.location_url %}
  <a href="{{ session.location_url }}" target="_blank" class="ms-1 small">
    <i class="bi bi-geo-alt"></i> Carte
  </a>
  {% endif %}
</div>
{% endif %}

{# Player presence buttons (only for registered players, future sessions) #}
{% if is_player %}
{% set my_status = summary.get(payload['user_id']) %}
{% if is_future %}
<div class="mt-2 d-flex gap-2 justify-content-center">
  <form method="post"
    action="/annonces/{{ game.slug }}/sessions/{{ session.id }}/presence/">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="hidden" name="is_present" value="1">
    <button type="submit"
      class="btn btn-sm {% if my_status == true %}btn-success{% else %}btn-outline-success{% endif %}">
      ✓ Présent·e
    </button>
  </form>
  <form method="post"
    action="/annonces/{{ game.slug }}/sessions/{{ session.id }}/presence/">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="hidden" name="is_present" value="0">
    <button type="submit"
      class="btn btn-sm {% if my_status == false %}btn-danger{% else %}btn-outline-danger{% endif %}">
      ✗ Absent·e
    </button>
  </form>
</div>
{% endif %}
{% endif %}

{# Attendance summary (all players + GM) #}
{% if summary %}
<div class="mt-2 small text-muted text-center">
  ✓ {{ data.present }} présent·es · ✗ {{ data.absent }} absent·es · — {{ data.no_reply }} sans réponse
</div>
{% endif %}

{# GM per-player toggle list #}
{% if (payload['user_id'] == game.gm_id or payload['is_admin']) and summary %}
<div class="mt-2">
  <div class="list-group list-group-flush">
    {% for player in game.players %}
    {% set status = summary.get(player.id) %}
    <div class="list-group-item px-0 py-1 d-flex justify-content-between align-items-center">
      <span class="small">{{ player.name }}</span>
      <div class="d-flex gap-1">
        <form method="post"
          action="/annonces/{{ game.slug }}/sessions/{{ session.id }}/presence/{{ player.id }}/">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <input type="hidden" name="is_present" value="1">
          <button type="submit"
            class="btn btn-sm {% if status == true %}btn-success{% else %}btn-outline-success{% endif %} py-0 px-2">
            ✓
          </button>
        </form>
        <form method="post"
          action="/annonces/{{ game.slug }}/sessions/{{ session.id }}/presence/{{ player.id }}/">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <input type="hidden" name="is_present" value="0">
          <button type="submit"
            class="btn btn-sm {% if status == false %}btn-danger{% else %}btn-outline-danger{% endif %} py-0 px-2">
            ✗
          </button>
        </form>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}
```

**Note on `now()`:** Jinja2 does not have a built-in `now()` function. You need to pass it from the view or use a context processor. The simplest approach: add `from datetime import datetime` and pass `now=datetime.utcnow()` in `get_game_details`, or register a context processor in `website/__init__.py`:

```python
@app.context_processor
def inject_now():
    from datetime import datetime
    return {"now": datetime.utcnow}
```

- [ ] **Step 4: Update `game_details.j2` — include attendance partial per session**

In `game_details.j2`, find the session card block (around line 303-335). Inside the `<div class="session-card ...">` but after the `<div class="calendar-wrapper">` closing `</div>`, add the include:

```html
        <div class="session-card p-3 mb-4 rounded shadow-sm text-center">
          <div class="calendar-wrapper">
            {# ... existing calendar button and GM edit/delete buttons ... #}
          </div>
          {% include 'game_details/session_attendance.j2' %}
        </div>
```

The exact insertion point is after `</div>` on line 333 (closing the `calendar-wrapper` div) and before the closing `</div>` of `session-card`.

- [ ] **Step 5: Add context processor for `now` if not already present**

In `website/__init__.py` (the `create_app` function), find where context processors are registered (search for `@app.context_processor`) and add:

```python
@app.context_processor
def inject_now():
    from datetime import datetime
    return {"now": datetime.utcnow}
```

- [ ] **Step 6: Manual smoke test**

Start the dev server and open a game detail page:

```bash
source .venv/bin/activate && set -a && source .env && set +a
flask --app website --debug run -p 8000
```

Check:
- Session cards show location badge when set
- Presence buttons appear for registered players (future sessions only)
- Attendance summary appears below each session
- GM sees per-player toggles
- Add/edit session modals have the location dropdown

- [ ] **Step 7: Run full test suite**

```bash
python -m pytest tests/ -m "not integration" -q
```

Expected: no regressions.

- [ ] **Step 8: Commit**

```bash
git add website/templates/ website/views/games.py
git commit -m "feat(session): add location and attendance UI to session cards"
```

---

## Final Verification

- [ ] Run `python -m pytest tests/ -m "not integration" -q` — all pass
- [ ] Run `black website/ tests/ && isort website/ tests/ && flake8 website/` — no errors
- [ ] Push to main

```bash
git push
```
