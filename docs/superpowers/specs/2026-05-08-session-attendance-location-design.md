# Session Attendance & Location — Design Spec

Date: 2026-05-08

## Overview

Two additions to `GameSession`:
1. **Lieu** — where the session takes place (online or in-person), set per session by the GM when adding or editing a session.
2. **Présence** — players confirm present/absent per session; GM can override any player's status. A Discord notification fires in the game channel only when a player marks themselves absent (not when the GM acts on their behalf).

---

## Data Model

### Extend `GameSession`

Three new nullable columns:

| Column | Type | Description |
|---|---|---|
| `location_type` | Enum(`online`, `inperson`) | Type of location |
| `location_label` | String | Required when `location_type` is set; free text (e.g. "Discord", "Salle B12, Jussieu") |
| `location_url` | String | Optional URL (Google Maps link for inperson, invite link for online) |

`location_type = NULL` means location not yet set (displayed as "Non renseigné").
`location_label` is required if `location_type` is set — `ValidationError` raised otherwise.

### New table `session_attendance`

| Column | Type | Constraints |
|---|---|---|
| `id` | BigInteger | PK |
| `session_id` | BigInteger | FK → game_session.id, NOT NULL, ON DELETE CASCADE |
| `user_id` | String | FK → user.id, NOT NULL, ON DELETE CASCADE |
| `is_present` | Boolean | NOT NULL |

Unique constraint on `(session_id, user_id)`.

A missing row = no response yet (not the same as absent).

Both FKs have `ON DELETE CASCADE`: deleting a session removes its attendance records; unregistering a player from a game must explicitly delete their attendance records for all sessions of that game (handled in `GameService.unregister_player`).

---

## Architecture

Follows existing project conventions (model → repository → service → view).

### Model
`website/models/session_attendance.py` — `SessionAttendance(db.Model, SerializableMixin)`

### Repository
`website/repositories/session_attendance.py` — `SessionAttendanceRepository(BaseRepository)`

Methods:
- `find_by_session(session_id)` → list of attendances for a session
- `find_by_session_and_user(session_id, user_id)` → single record or None
- `upsert(session_id, user_id, is_present)` → create or update
- `delete_by_game_and_user(game_id, user_id)` → delete all attendance records for a user across all sessions of a game (called on unregister)

### Service
New methods added to `GameSessionService`.

`GameSessionService` receives an optional `discord_service` parameter in its constructor (same injection pattern as `GameService`). In production it is instantiated with a real `DiscordService`; in tests it receives a mock.

Methods:

**`set_attendance(session, user_id, is_present, by_gm=False)`**
- Creates or updates the attendance record (upsert).
- Toggle behaviour: if the player clicks their currently-active button (e.g. "Absent" while already absent), the row is deleted — resetting to "no response".
- Discord notification fires only when `is_present=False` and `by_gm=False` (player marking themselves absent for the first time or re-marking after a reset). No notification when GM acts, and no notification when a player changes from absent back to present.
- Raises `ValidationError` if user is not registered in the game.

**`get_attendance_summary(session)`**
Returns `{user_id: True | False | None}` for all players registered in the game. `None` = no response.

Location fields (`location_type`, `location_label`, `location_url`) are passed through the existing `GameSessionService.create()` and `GameSessionService.update()` signatures. Validation: if `location_type` is provided, `location_label` must be non-empty.

### Discord embed

New embed type `attendance-alert` in `game_embeds.py`:
- Posts in `game.channel` (skipped silently if channel is empty, consistent with existing guard).
- Receives `start` and `end` as formatted strings (same pattern as existing session embeds).
- Content: "⚠️ `<@user_id>` ne sera pas présent·e pour la session du **{start}**."

### Views (routes)

Two new routes in `website/views/games.py`:

```
POST /annonces/<slug>/sessions/<session_id>/presence/
```
Player marks own presence. Payload: `is_present=1|0`.
Authorization: must be registered in the game.
Temporal constraint: only available while the session's `end` datetime is in the future (returns 403 if session is past).

```
POST /annonces/<slug>/sessions/<session_id>/presence/<user_id>/
```
GM marks presence for a specific player. Payload: `is_present=1|0`.
Authorization: must be GM of the game or admin.
No temporal constraint for GM (can edit retrospectively).

Both redirect to the game detail page with a flash message.

---

## UI

### Session form (add/edit session)

Add to the existing session modal/form:
- **Lieu** select: `[ Non renseigné | En ligne | Présentiel ]`
- Conditional fields shown/hidden via JS:
  - If "En ligne": text input for platform name (required, e.g. "Discord")
  - If "Présentiel": text input for label (required) + optional URL input labelled "Lien Google Maps"

### Session list (game detail page)

Each session card shows:
- Location badge: Bootstrap `badge bg-primary` ("En ligne") or `badge bg-warning text-dark` ("Présentiel") + label + link if present. Nothing shown if `location_type` is NULL.
- For registered players: two Bootstrap buttons `btn btn-sm btn-outline-success` / `btn btn-outline-danger`; filled (`btn-success` / `btn-danger`) when that status is active. Clicking the active button resets to "no response". Buttons are hidden for past sessions.
- Summary line (visible to all registered players + GM): "✓ 3 présent·es · ✗ 1 absent·e · — 0 sans réponse"

### GM session detail

A `list-group` below the session info listing each registered player with their current status. Each row has an inline toggle (two small `btn btn-sm` buttons: ✓ / ✗) the GM can click to switch. Only visible to GM and admins.

---

## Permissions

| Action | Who |
|---|---|
| Set own attendance | Any registered player (future sessions only) |
| Set attendance for any player | GM of the game, Admin (any session) |
| Set location | GM of the game, Admin |
| View attendance summary | Any registered player + GM + Admin |

---

## Migrations

1. `flask db revision -m "add location fields to game_session"`
2. `flask db revision -m "add session_attendance table"`

---

## Testing

- `tests/models/test_session_attendance.py` — model constraints, unique constraint
- `tests/repositories/test_session_attendance_repository.py` — upsert, find, delete_by_game_and_user
- `tests/services/test_game_session_service.py`:
  - `set_attendance` happy path (player marks absent → Discord notification triggered)
  - toggle: clicking active status resets to no response
  - GM marking absent → no Discord notification
  - player changing absent → present → no new notification
  - unregistered player → ValidationError
  - `get_attendance_summary` returns correct None/True/False per player
- `tests/views/test_games.py`:
  - player presence route: happy path, unauthorized (not registered), past session (403)
  - GM presence route: happy path, unauthorized (not GM)
  - location validation: missing label when type is set → error
