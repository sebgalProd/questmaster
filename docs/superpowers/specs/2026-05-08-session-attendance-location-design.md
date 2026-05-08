# Session Attendance & Location — Design Spec

Date: 2026-05-08

## Overview

Two additions to `GameSession`:
1. **Lieu** — where the session takes place (online or in-person), set per session by the GM when adding or editing a session.
2. **Présence** — players confirm present/absent per session; GM can override any player's status. A Discord notification fires when a player marks absent.

---

## Data Model

### Extend `GameSession`

Three new nullable columns:

| Column | Type | Description |
|---|---|---|
| `location_type` | Enum(`online`, `inperson`) | Type of location |
| `location_label` | String | Free text (e.g. "Salle B12, Jussieu") |
| `location_url` | String | Optional Google Maps link |

`location_type = NULL` means location not yet set (displayed as "Non renseigné").

### New table `session_attendance`

| Column | Type | Constraints |
|---|---|---|
| `id` | BigInteger | PK |
| `session_id` | Integer | FK → game_session.id, NOT NULL, ON DELETE CASCADE |
| `user_id` | String | FK → user.id, NOT NULL |
| `is_present` | Boolean | NOT NULL |

Unique constraint on `(session_id, user_id)`.

A missing row = no response yet (not the same as absent).

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

### Service
New methods added to `GameSessionService`:

- `set_attendance(session, user_id, is_present, by_gm=False)` — creates or updates the record; if `is_present=False` and `by_gm=False` (player marking themselves absent), triggers Discord notification
- `get_attendance_summary(session)` → dict `{user_id: is_present | None}` for all registered players

The Discord notification calls `discord_service.send_game_embed(game, embed_type="attendance-alert", player=user_id, session=session)`.

Location fields are set via the existing `GameSessionService.create()` and `GameSessionService.update()` — just pass the new fields through.

### Discord embed

New embed type `attendance-alert` in `game_embeds.py`:
- Posts in `game.channel`
- Content: "⚠️ `@PlayerName` ne sera pas présent·e pour la session du **{date}**."

### Views (routes)

Two new routes in `website/views/games.py`:

```
POST /annonces/<slug>/sessions/<session_id>/presence/
```
Player marks own presence. Payload: `is_present=true|false`.
Authorization: must be registered in the game.

```
POST /annonces/<slug>/sessions/<session_id>/presence/<user_id>/
```
GM marks presence for a specific player. Authorization: must be GM or admin.

Both redirect to game detail page with flash message.

---

## UI

### Session form (add/edit session)

Add to the existing session modal/form:
- **Lieu** dropdown: `[ Non renseigné | En ligne | Présentiel ]`
- If "En ligne": text input for platform name (ex: "Discord")
- If "Présentiel": text input for label + optional URL input for Google Maps

### Session list (game detail page)

Each session card shows:
- Location badge: Bootstrap `badge bg-primary` ("En ligne") or `badge bg-warning text-dark` ("Présentiel") + label text + Maps link if present
- For registered players: two buttons `btn btn-outline-success` / `btn btn-outline-danger`, filled (`btn-success` / `btn-danger`) when selected
- Summary line: "✓ 3 présent·es · ✗ 1 absent·e · — 0 sans réponse"

### GM session detail

Below session info, a `list-group` showing each registered player with their status and a "Modifier" button (dropdown or toggle). Only visible to GM and admins.

---

## Permissions

| Action | Who |
|---|---|
| Set own attendance | Any registered player |
| Set attendance for any player | GM of the game, Admin |
| Set location | GM of the game, Admin |
| View attendance summary | Any registered player + GM + Admin |

---

## Migrations

1. `flask db revision -m "add location fields to game_session"`
2. `flask db revision -m "add session_attendance table"`

---

## Testing

- `tests/models/test_session_attendance.py` — model constraints
- `tests/repositories/test_session_attendance_repository.py` — upsert, find methods
- `tests/services/test_game_session_service.py` — set_attendance, summary, Discord notification trigger
- `tests/views/test_games.py` — presence routes (auth, happy path, unauthorized)
