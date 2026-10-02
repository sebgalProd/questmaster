# Jeux Steam en commun — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une commande Discord `/jeux-en-commun @a @b …` qui répond avec les jeux Steam possédés par tous les membres cités (plus l'auteur), et une commande `/steam-statut`.

**Architecture:** Les commandes arrivent dans l'application Flask existante par HTTP (Interactions Endpoint de Discord), vérifiées par signature Ed25519. Le SteamID de chaque membre est lu dans ses connexions Discord à la connexion au site et stocké sur `User`. Un client Steam (`GetOwnedGames`) et un service avec cache Redis de 6 h calculent l'intersection. `/jeux-en-commun` répond « en cours » tout de suite, puis un fil d'exécution modifie la réponse.

**Tech Stack:** Python 3.13, Flask 3.1, Flask-SQLAlchemy, Alembic, Flask-Discord (OAuth), Flask-Caching (Redis), requests, tenacity, PyNaCl, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-steam-jeux-en-commun-design.md`

## Global Constraints

- Style : Black ligne 99, isort, flake8, pydoclint (docstrings Google avec `Args`, `Returns`, `Raises`).
- Couches : models sans logique ; services propriétaires des `db.session.commit()` ; views minces ; client = HTTP brut.
- Commits Conventional Commits, terminés par `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Route des interactions : `POST /discord/interactions/`, avec la barre oblique finale.
- Cache des bibliothèques : clé `steam:library:<steam_id>`, durée 6 h (21600 s), pour les statuts `ok` et `private` seulement.
- `/jeux-en-commun` : options `joueur1` (obligatoire) à `joueur9` (facultatives), type USER (6) ; auteur toujours inclus ; 25 jeux affichés au plus ; tri par temps de jeu cumulé décroissant, puis par nom.
- Statuts de bibliothèque : `ok`, `not_linked`, `private`, `unavailable`.
- Commandes enregistrées sur le serveur (guild), pas globalement.
- Nouvelles variables d'environnement : `STEAM_API_KEY`, `DISCORD_PUBLIC_KEY`. Sans `DISCORD_PUBLIC_KEY`, la route répond 503.
- Dépendance ajoutée : `PyNaCl==1.6.2`.
- La clé Steam n'apparaît jamais dans les journaux ; les SteamID ne sont jamais affichés dans Discord.
- Tests unitaires : `.venv/bin/python -m pytest tests/ -m "not integration" -q`, avec Postgres et Redis locaux démarrés (`docker compose up -d db redis`). Les tests de vues : `.venv/bin/python -m pytest tests/views -q`.

## Review Focus

1. **L'auteur se cite lui-même, ou cite deux fois la même personne** : chaque membre ne compte qu'une fois, et « auteur + lui-même » est refusé comme un groupe d'une seule personne → test dans la tâche 8.
2. **Un bot ou un membre inconnu de QuestMaster est cité** (jamais connecté au site) : il est exclu comme « Steam non relié », sans planter → test dans la tâche 8.
3. **Commande lancée en message privé au bot** : la charge contient `user` au lieu de `member.user` ; l'auteur doit quand même être trouvé → test dans la tâche 8.
4. **Noms de jeux longs ou nombreux** : la description d'un embed Discord est limitée à 4096 caractères et le pied à 2048 ; le message ne doit jamais dépasser ces limites → test dans la tâche 6.
5. **Jeu sans nom dans la réponse Steam** (appli retirée du magasin) : afficher `App <appid>` au lieu de planter → test dans la tâche 3.

---

## Carte des fichiers

| Fichier | Rôle |
|---|---|
| `config/settings.py` (modif.) | `STEAM_API_KEY`, `DISCORD_PUBLIC_KEY` |
| `pyproject.toml` (modif.) | `PyNaCl==1.6.2` |
| `website/exceptions/steam.py` (nouveau), `website/exceptions/__init__.py` (modif.) | `SteamAPIError` |
| `website/models/user.py` (modif.) | colonne `steam_id` |
| `migrations/versions/c5f2d8e1b3a4_add_steam_id_to_user.py` (nouveau) | migration |
| `website/services/user.py` (modif.) | `link_steam_from_connections` |
| `website/views/auth.py` (modif.) | permission `connections` + liaison à la connexion |
| `website/client/steam.py` (nouveau) | appel `GetOwnedGames` |
| `website/services/steam.py` (nouveau) | bibliothèque en cache, intersection |
| `website/utils/discord_signature.py` (nouveau) | vérification Ed25519 |
| `website/utils/steam_embeds.py` (nouveau) | textes et embeds des réponses |
| `website/utils/discord_commands.py` (nouveau) | définition des commandes |
| `website/client/discord.py` (modif.) | `edit_interaction_response`, `register_guild_commands` |
| `website/extensions.py`, `website/__init__.py` (modif.) | CLI `register-discord-commands` |
| `website/views/interactions.py` (nouveau), `website/views/__init__.py` (modif.) | blueprint des interactions |
| `tests/…` | un fichier de tests par module ci-dessus |

---

### Task 1: Socle — configuration, dépendance, exception, colonne `steam_id`

**Files:**
- Modify: `config/settings.py` (après la ligne `ADMIN_CHANNEL_ID = …`)
- Modify: `pyproject.toml` (liste `dependencies`)
- Create: `website/exceptions/steam.py`
- Modify: `website/exceptions/__init__.py`
- Modify: `website/models/user.py` (docstring `Attributes:` et colonnes, vers les lignes 104-120)
- Create: `migrations/versions/c5f2d8e1b3a4_add_steam_id_to_user.py`
- Test: `tests/models/test_user_steam_id.py`

**Interfaces:**
- Produces: `Settings.STEAM_API_KEY`, `Settings.DISCORD_PUBLIC_KEY` (str | None) ; `website.exceptions.SteamAPIError(message: str, status_code: int | None = None)` ; `User.steam_id: str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/models/test_user_steam_id.py
"""Tests for the User.steam_id column and SteamAPIError."""

from website.exceptions import QuestMasterError, SteamAPIError
from website.models import User


def test_user_steam_id_defaults_to_none(db_session):
    user = User(id="999000111", name="Steamless")
    db_session.add(user)
    db_session.flush()
    assert user.steam_id is None


def test_user_steam_id_is_persisted(db_session):
    user = User(id="999000112", name="Steamer", steam_id="76561198000000001")
    db_session.add(user)
    db_session.flush()
    assert db_session.get(User, "999000112").steam_id == "76561198000000001"


def test_steam_api_error_is_questmaster_error():
    err = SteamAPIError("boom", status_code=503)
    assert isinstance(err, QuestMasterError)
    assert err.status_code == 503
    assert "503" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/models/test_user_steam_id.py -v`
Expected: FAIL with `ImportError: cannot import name 'SteamAPIError'`

- [ ] **Step 3: Write minimal implementation**

`website/exceptions/steam.py` :

```python
"""Steam-related exception classes for the QuestMaster application."""

from website.exceptions.base import QuestMasterError


class SteamAPIError(QuestMasterError):
    """Steam Web API request failed.

    Args:
        message: Description of the API error.
        status_code: HTTP status code returned by Steam, if any.
    """

    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(
            message=f"[{status_code}] {message}",
            code=f"STEAM_API_{status_code}",
            details={"status_code": status_code},
        )
```

`website/exceptions/__init__.py` : ajouter `from website.exceptions.steam import SteamAPIError` après l'import de `discord`, et `"SteamAPIError",` dans `__all__` après `"DiscordAPIError",`.

`website/models/user.py` : dans la docstring `Attributes:`, après la ligne `username: …`, ajouter
`        steam_id: SteamID64 read from the user's Discord connections, if linked.`
puis, après `username = db.Column(db.String(), nullable=True)`, ajouter :

```python
    steam_id = db.Column(db.String(), nullable=True)
```

`config/settings.py`, après `ADMIN_CHANNEL_ID = os.environ.get("ADMIN_CHANNEL_ID")` :

```python
    DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY")
    STEAM_API_KEY = os.environ.get("STEAM_API_KEY")
```

`pyproject.toml`, dans `dependencies`, après `"psycopg2-binary==2.9.11",` :

```toml
    "PyNaCl==1.6.2",
```

Puis installer : `uv pip install --python .venv/bin/python PyNaCl==1.6.2`

`migrations/versions/c5f2d8e1b3a4_add_steam_id_to_user.py` :

```python
"""add steam_id to user

Revision ID: c5f2d8e1b3a4
Revises: b4e1c7d2a9f3
Create Date: 2026-10-02 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5f2d8e1b3a4'
down_revision = 'b4e1c7d2a9f3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("steam_id", sa.String(), nullable=True))


def downgrade():
    op.drop_column("user", "steam_id")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/models/test_user_steam_id.py -v`
Expected: 3 passed

- [ ] **Step 5: Verify the migration on a throwaway database**

Les tests vident la base locale `clubjdr` (`drop_all`) : tester la migration sur une base jetable.

```bash
set -a; . ./.env; set +a; U=${POSTGRES_USER:-postgres}
docker compose exec -T db psql -U $U -d postgres -c "create database qm_migtest"
POSTGRES_HOST=localhost POSTGRES_DB=qm_migtest .venv/bin/flask --app website db upgrade
POSTGRES_HOST=localhost POSTGRES_DB=qm_migtest .venv/bin/flask --app website db downgrade
POSTGRES_HOST=localhost POSTGRES_DB=qm_migtest .venv/bin/flask --app website db upgrade
docker compose exec -T db psql -U $U -d qm_migtest -c '\d "user"' | grep steam_id
docker compose exec -T db psql -U $U -d postgres -c "drop database qm_migtest"
```
Expected: upgrade/downgrade/upgrade sans erreur ; la ligne `steam_id | character varying` apparaît.

- [ ] **Step 6: Commit**

```bash
git add config/settings.py pyproject.toml website/exceptions/ website/models/user.py migrations/versions/c5f2d8e1b3a4_add_steam_id_to_user.py tests/models/test_user_steam_id.py
git commit -m "feat(steam): add steam_id to user, Steam settings and SteamAPIError"
```

---

### Task 2: Lier Steam à la connexion au site

**Files:**
- Modify: `website/services/user.py` (nouvelle méthode dans `UserService`)
- Modify: `website/views/auth.py:48` (scope) et `callback()` (vers les lignes 78-96)
- Test: `tests/services/test_user_steam_link.py`, `tests/views/test_auth_steam.py`

**Interfaces:**
- Consumes: `User.steam_id` (Task 1).
- Produces: `UserService.link_steam_from_connections(user: User, connections: list) -> bool` (True si la valeur a changé). Chaque élément de `connections` a les attributs `type` (str) et `id` (str), comme `flask_discord.models.UserConnection`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_user_steam_link.py
"""Tests for UserService.link_steam_from_connections."""

from types import SimpleNamespace

from website.services.user import UserService


def _conn(type_, id_):
    return SimpleNamespace(type=type_, id=id_)


def test_links_steam_connection(db_session, regular_user):
    changed = UserService().link_steam_from_connections(
        regular_user, [_conn("twitch", "t1"), _conn("steam", "76561198000000001")]
    )
    assert changed is True
    assert regular_user.steam_id == "76561198000000001"


def test_no_steam_connection_keeps_existing_value(db_session, regular_user):
    regular_user.steam_id = "76561198000000001"
    changed = UserService().link_steam_from_connections(regular_user, [_conn("twitch", "t1")])
    assert changed is False
    assert regular_user.steam_id == "76561198000000001"


def test_same_steam_id_is_not_a_change(db_session, regular_user):
    regular_user.steam_id = "76561198000000001"
    changed = UserService().link_steam_from_connections(
        regular_user, [_conn("steam", "76561198000000001")]
    )
    assert changed is False
```

```python
# tests/views/test_auth_steam.py
"""Login callback links Steam and never fails because of it."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.constants import TEST_REGULAR_USER_ID


def _fake_discord(connections=None, error=None):
    fake = MagicMock()
    fake.authorized = True
    fake.fetch_user.return_value = SimpleNamespace(id=TEST_REGULAR_USER_ID)
    if error:
        fake.fetch_connections.side_effect = error
    else:
        fake.fetch_connections.return_value = connections or []
    return fake


def test_login_requests_connections_scope(client):
    with patch("website.views.auth.discord") as fake:
        fake.create_session.return_value = "redirecting"
        client.get("/login/")
        fake.create_session.assert_called_once_with(scope=["identify", "connections"])


def test_callback_links_steam(client, db_session, mock_discord_lookups, regular_user):
    fake = _fake_discord([SimpleNamespace(type="steam", id="76561198000000042")])
    with patch("website.views.auth.discord", fake):
        response = client.get("/callback/")
    assert response.status_code in (302, 303)
    assert regular_user.steam_id == "76561198000000042"


def test_callback_succeeds_when_connections_fail(
    client, db_session, mock_discord_lookups, regular_user
):
    fake = _fake_discord(error=RuntimeError("Discord down"))
    with patch("website.views.auth.discord", fake):
        response = client.get("/callback/")
    assert response.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert sess["user_id"] == TEST_REGULAR_USER_ID
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/services/test_user_steam_link.py tests/views/test_auth_steam.py -v`
Expected: FAIL (`AttributeError: 'UserService' object has no attribute 'link_steam_from_connections'`, et assertion du scope)

- [ ] **Step 3: Write minimal implementation**

Dans `website/services/user.py`, ajouter la méthode à `UserService` (après `get_or_create`) :

```python
    def link_steam_from_connections(self, user: User, connections: list) -> bool:
        """Store the SteamID found in the user's Discord connections.

        An absent Steam connection never clears an existing SteamID: the user
        may simply have declined the "connections" permission this time.

        Args:
            user: User to update.
            connections: Discord connections, each with ``type`` and ``id``.

        Returns:
            True if the stored SteamID changed.
        """
        steam = next((c for c in connections if getattr(c, "type", None) == "steam"), None)
        if steam is None or user.steam_id == str(steam.id):
            return False
        user.steam_id = str(steam.id)
        db.session.commit()
        return True
```

Dans `website/views/auth.py` :
- ajouter `from website.utils.logger import logger` aux imports ;
- remplacer `return discord.create_session(scope=["identify"])` par
  `return discord.create_session(scope=["identify", "connections"])` ;
- dans `callback()`, juste après `user.refresh_roles()` et **avant** le test `if not user.is_player:`, ajouter :

```python
        try:
            UserService().link_steam_from_connections(user, discord.fetch_connections())
        except Exception as e:
            logger.warning(f"Could not read Discord connections for user {user.id}: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/services/test_user_steam_link.py tests/views/test_auth_steam.py tests/views/test_auth.py -v`
Expected: tout passe

- [ ] **Step 5: Commit**

```bash
git add website/services/user.py website/views/auth.py tests/services/test_user_steam_link.py tests/views/test_auth_steam.py
git commit -m "feat(steam): link Steam account from Discord connections at login"
```

---

### Task 3: Client Steam

**Files:**
- Create: `website/client/steam.py`
- Test: `tests/client/__init__.py` (vide), `tests/client/test_steam_client.py`

**Interfaces:**
- Consumes: `SteamAPIError` (Task 1).
- Produces: `Steam(api_key: str | None, retry_wait: float = 1.0, timeout: float = 10.0)` ; `Steam.get_owned_games(steam_id: str) -> list[dict] | None`. Chaque dict : `{"appid": int, "name": str, "playtime_forever": int}`. `None` = profil privé. Lève `SteamAPIError` après 3 échecs passagers ou sur une erreur définitive.

- [ ] **Step 1: Write the failing tests**

```python
# tests/client/test_steam_client.py
"""Tests for the low-level Steam client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from website.client.steam import Steam
from website.exceptions import SteamAPIError


def _response(status=200, payload=None):
    r = MagicMock()
    r.status_code = status
    r.ok = 200 <= status < 300
    r.json.return_value = payload if payload is not None else {}
    return r


@pytest.fixture
def steam():
    return Steam("secret-key", retry_wait=0)


def test_returns_games(steam):
    payload = {
        "response": {
            "game_count": 2,
            "games": [
                {"appid": 10, "name": "Counter-Strike", "playtime_forever": 120},
                {"appid": 20, "name": "Valheim", "playtime_forever": 0},
            ],
        }
    }
    with patch("website.client.steam.requests.get", return_value=_response(200, payload)) as get:
        games = steam.get_owned_games("76561198000000001")
    assert games == [
        {"appid": 10, "name": "Counter-Strike", "playtime_forever": 120},
        {"appid": 20, "name": "Valheim", "playtime_forever": 0},
    ]
    params = get.call_args.kwargs["params"]
    assert params["steamid"] == "76561198000000001"
    assert params["include_appinfo"] == 1
    assert params["include_played_free_games"] == 1


def test_private_profile_returns_none(steam):
    with patch("website.client.steam.requests.get", return_value=_response(200, {"response": {}})):
        assert steam.get_owned_games("1") is None


def test_public_empty_library_returns_empty_list(steam):
    payload = {"response": {"game_count": 0, "games": []}}
    with patch("website.client.steam.requests.get", return_value=_response(200, payload)):
        assert steam.get_owned_games("1") == []


def test_game_without_name_gets_fallback(steam):
    payload = {"response": {"games": [{"appid": 42, "playtime_forever": 5}]}}
    with patch("website.client.steam.requests.get", return_value=_response(200, payload)):
        assert steam.get_owned_games("1") == [
            {"appid": 42, "name": "App 42", "playtime_forever": 5}
        ]


def test_retries_transient_error_then_succeeds(steam):
    ok = _response(200, {"response": {"games": []}})
    with patch(
        "website.client.steam.requests.get", side_effect=[_response(503), ok]
    ) as get:
        assert steam.get_owned_games("1") == []
    assert get.call_count == 2


def test_network_error_is_retried(steam):
    ok = _response(200, {"response": {"games": []}})
    with patch(
        "website.client.steam.requests.get",
        side_effect=[requests.ConnectionError("down"), ok],
    ):
        assert steam.get_owned_games("1") == []


def test_gives_up_after_three_transient_errors(steam):
    with patch("website.client.steam.requests.get", return_value=_response(503)) as get:
        with pytest.raises(SteamAPIError):
            steam.get_owned_games("1")
    assert get.call_count == 3


def test_permanent_error_is_not_retried(steam):
    with patch("website.client.steam.requests.get", return_value=_response(403)) as get:
        with pytest.raises(SteamAPIError) as exc:
            steam.get_owned_games("1")
    assert get.call_count == 1
    assert "secret-key" not in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/client/test_steam_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'website.client.steam'`

- [ ] **Step 3: Write minimal implementation**

```python
# website/client/steam.py
"""Steam Web API client for low-level HTTP operations.

Business logic (caching, intersections) belongs in SteamService.
"""

import requests
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from website.exceptions import SteamAPIError
from website.utils.logger import logger

OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"


class _TransientSteamError(Exception):
    """Network error or HTTP 429/5xx worth retrying."""

    def __init__(self, status_code=None):
        self.status_code = status_code
        super().__init__(f"Transient Steam error ({status_code})")


class Steam:
    """Low-level Steam Web API client.

    Attributes:
        api_key: Steam Web API key (never logged).
        retry_wait: Base wait in seconds between retries (0 in tests).
        timeout: Timeout in seconds for each HTTP request.
    """

    def __init__(self, api_key, retry_wait: float = 1.0, timeout: float = 10.0):
        self.api_key = api_key
        self.retry_wait = retry_wait
        self.timeout = timeout

    def _fetch_owned_games(self, steam_id: str) -> dict:
        params = {
            "key": self.api_key,
            "steamid": steam_id,
            "include_appinfo": 1,
            "include_played_free_games": 1,
            "format": "json",
        }
        try:
            r = requests.get(OWNED_GAMES_URL, params=params, timeout=self.timeout)
        except requests.RequestException as e:
            logger.warning(f"Steam request failed for GetOwnedGames: {type(e).__name__}")
            raise _TransientSteamError() from e
        if r.status_code == 429 or r.status_code >= 500:
            raise _TransientSteamError(r.status_code)
        if not r.ok:
            raise SteamAPIError("GetOwnedGames refused", status_code=r.status_code)
        return r.json()

    def get_owned_games(self, steam_id: str) -> list[dict] | None:
        """Return the games owned by a Steam account.

        Args:
            steam_id: SteamID64 of the account.

        Returns:
            List of ``{"appid", "name", "playtime_forever"}`` dicts, or None
            when the profile or its game details are private.

        Raises:
            SteamAPIError: If Steam keeps failing or refuses the request.
        """
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=self.retry_wait, max=4),
                retry=retry_if_exception_type(_TransientSteamError),
                reraise=True,
            ):
                with attempt:
                    data = self._fetch_owned_games(steam_id)
        except _TransientSteamError as e:
            raise SteamAPIError("Steam unavailable", status_code=e.status_code) from e

        response = data.get("response", {})
        if "games" not in response:
            return None
        return [
            {
                "appid": int(g["appid"]),
                "name": g.get("name") or f"App {g['appid']}",
                "playtime_forever": int(g.get("playtime_forever", 0)),
            }
            for g in response["games"]
        ]
```

Créer aussi `tests/client/__init__.py` vide.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/client/test_steam_client.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add website/client/steam.py tests/client/
git commit -m "feat(steam): add Steam Web API client for owned games"
```

---

### Task 4: Service Steam — bibliothèque en cache et jeux en commun

**Files:**
- Create: `website/services/steam.py`
- Test: `tests/services/test_steam_service.py`

**Interfaces:**
- Consumes: `Steam.get_owned_games` (Task 3), `SteamAPIError`, `User.steam_id`.
- Produces:
  - `LibraryResult(status: str, games: list[dict] = [])` (dataclass) ;
  - `CommonGamesResult(included: list[str], excluded: list[tuple[str, str]], games: list[dict], total: int, too_few: bool)` (dataclass) ; chaque jeu de `games` : `{"appid": int, "name": str, "playtime": int}` (minutes cumulées) ;
  - `SteamService(client=None, cache=None)` ; `get_library(user: User | None) -> LibraryResult` ; `common_games(members: list[tuple[str, User | None]]) -> CommonGamesResult` (`str` = pseudo d'affichage) ;
  - constantes `STATUS_OK = "ok"`, `STATUS_NOT_LINKED = "not_linked"`, `STATUS_PRIVATE = "private"`, `STATUS_UNAVAILABLE = "unavailable"`, `LIBRARY_CACHE_TIMEOUT = 21600`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_steam_service.py
"""Tests for SteamService."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from website.exceptions import SteamAPIError
from website.services.steam import (
    LIBRARY_CACHE_TIMEOUT,
    STATUS_NOT_LINKED,
    STATUS_OK,
    STATUS_PRIVATE,
    STATUS_UNAVAILABLE,
    SteamService,
)


class FakeCache:
    def __init__(self):
        self.store = {}
        self.timeouts = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, timeout=None):
        self.store[key] = value
        self.timeouts[key] = timeout


def _user(steam_id):
    return SimpleNamespace(steam_id=steam_id)


def _game(appid, name, minutes):
    return {"appid": appid, "name": name, "playtime_forever": minutes}


@pytest.fixture
def cache():
    return FakeCache()


def test_not_linked_user(cache):
    client = MagicMock()
    service = SteamService(client=client, cache=cache)
    assert service.get_library(_user(None)).status == STATUS_NOT_LINKED
    assert service.get_library(None).status == STATUS_NOT_LINKED
    client.get_owned_games.assert_not_called()


def test_library_is_cached(cache):
    client = MagicMock()
    client.get_owned_games.return_value = [_game(1, "A", 10)]
    service = SteamService(client=client, cache=cache)
    first = service.get_library(_user("s1"))
    second = service.get_library(_user("s1"))
    assert first.status == second.status == STATUS_OK
    assert second.games == [_game(1, "A", 10)]
    client.get_owned_games.assert_called_once_with("s1")
    assert cache.timeouts["steam:library:s1"] == LIBRARY_CACHE_TIMEOUT


def test_private_library_is_cached(cache):
    client = MagicMock()
    client.get_owned_games.return_value = None
    service = SteamService(client=client, cache=cache)
    assert service.get_library(_user("s1")).status == STATUS_PRIVATE
    assert service.get_library(_user("s1")).status == STATUS_PRIVATE
    client.get_owned_games.assert_called_once()


def test_unavailable_is_never_cached(cache):
    client = MagicMock()
    client.get_owned_games.side_effect = SteamAPIError("down", status_code=503)
    service = SteamService(client=client, cache=cache)
    assert service.get_library(_user("s1")).status == STATUS_UNAVAILABLE
    assert service.get_library(_user("s1")).status == STATUS_UNAVAILABLE
    assert client.get_owned_games.call_count == 2
    assert "steam:library:s1" not in cache.store


def test_common_games_intersection_sorted_by_group_playtime(cache):
    libraries = {
        "a": [_game(1, "Zeta", 10), _game(2, "Alpha", 500), _game(3, "Only A", 9999)],
        "b": [_game(1, "Zeta", 600), _game(2, "Alpha", 5)],
    }
    client = MagicMock()
    client.get_owned_games.side_effect = lambda sid: libraries[sid]
    service = SteamService(client=client, cache=cache)

    result = service.common_games([("Alice", _user("a")), ("Bob", _user("b"))])

    assert result.included == ["Alice", "Bob"]
    assert result.excluded == []
    assert result.too_few is False
    assert result.total == 2
    assert result.games == [
        {"appid": 1, "name": "Zeta", "playtime": 610},
        {"appid": 2, "name": "Alpha", "playtime": 505},
    ]


def test_ties_are_sorted_by_name(cache):
    libraries = {"a": [_game(1, "Beta", 0), _game(2, "Alpha", 0)], "b": [_game(1, "Beta", 0), _game(2, "Alpha", 0)]}
    client = MagicMock()
    client.get_owned_games.side_effect = lambda sid: libraries[sid]
    result = SteamService(client=client, cache=cache).common_games(
        [("A", _user("a")), ("B", _user("b"))]
    )
    assert [g["name"] for g in result.games] == ["Alpha", "Beta"]


def test_excluded_members_and_too_few(cache):
    client = MagicMock()
    client.get_owned_games.side_effect = lambda sid: None if sid == "priv" else [_game(1, "A", 1)]
    service = SteamService(client=client, cache=cache)

    result = service.common_games(
        [("Alice", _user("a")), ("Bob", None), ("Carole", _user("priv"))]
    )

    assert result.included == ["Alice"]
    assert result.excluded == [("Bob", STATUS_NOT_LINKED), ("Carole", STATUS_PRIVATE)]
    assert result.too_few is True
    assert result.games == []
    assert result.total == 0


def test_no_common_game(cache):
    libraries = {"a": [_game(1, "A", 1)], "b": [_game(2, "B", 1)]}
    client = MagicMock()
    client.get_owned_games.side_effect = lambda sid: libraries[sid]
    result = SteamService(client=client, cache=cache).common_games(
        [("A", _user("a")), ("B", _user("b"))]
    )
    assert result.too_few is False
    assert result.games == []
    assert result.total == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/services/test_steam_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'website.services.steam'`

- [ ] **Step 3: Write minimal implementation**

```python
# website/services/steam.py
"""Steam service: cached libraries and games shared by a group."""

from __future__ import annotations

from dataclasses import dataclass, field

from flask import current_app

from website.exceptions import SteamAPIError
from website.utils.logger import logger

STATUS_OK = "ok"
STATUS_NOT_LINKED = "not_linked"
STATUS_PRIVATE = "private"
STATUS_UNAVAILABLE = "unavailable"
LIBRARY_CACHE_TIMEOUT = 6 * 3600


@dataclass
class LibraryResult:
    """Steam library of one member.

    Attributes:
        status: One of ok, not_linked, private, unavailable.
        games: Owned games when status is ok.
    """

    status: str
    games: list[dict] = field(default_factory=list)


@dataclass
class CommonGamesResult:
    """Games owned by every readable member of a group.

    Attributes:
        included: Display names of members whose library was read.
        excluded: (display name, status) of members left out.
        games: Shared games sorted by group playtime, then name.
        total: Number of shared games.
        too_few: True when fewer than two libraries could be read.
    """

    included: list[str]
    excluded: list[tuple[str, str]]
    games: list[dict]
    total: int
    too_few: bool


class SteamService:
    """Service layer for Steam libraries."""

    def __init__(self, client=None, cache=None):
        if client is None:
            from website.client.steam import Steam

            client = Steam(current_app.config.get("STEAM_API_KEY"))
        if cache is None:
            from website.extensions import cache as app_cache

            cache = app_cache
        self.client = client
        self.cache = cache

    def get_library(self, user) -> LibraryResult:
        """Return a member's Steam library, cached for six hours.

        Args:
            user: User with a ``steam_id`` attribute, or None if unknown.

        Returns:
            LibraryResult with the member's status and games.
        """
        steam_id = getattr(user, "steam_id", None)
        if not steam_id:
            return LibraryResult(STATUS_NOT_LINKED)

        key = f"steam:library:{steam_id}"
        cached = self.cache.get(key)
        if cached is not None:
            return LibraryResult(cached["status"], cached["games"])

        try:
            games = self.client.get_owned_games(steam_id)
        except SteamAPIError as e:
            logger.warning(f"Steam library unavailable: {e}")
            return LibraryResult(STATUS_UNAVAILABLE)

        result = LibraryResult(STATUS_PRIVATE) if games is None else LibraryResult(STATUS_OK, games)
        self.cache.set(
            key, {"status": result.status, "games": result.games}, timeout=LIBRARY_CACHE_TIMEOUT
        )
        return result

    def common_games(self, members: list[tuple[str, object]]) -> CommonGamesResult:
        """Compute the games owned by every readable member.

        Args:
            members: (display name, User or None) for each member of the group.

        Returns:
            CommonGamesResult with included/excluded members and shared games.
        """
        included, excluded, libraries = [], [], []
        for name, user in members:
            library = self.get_library(user)
            if library.status == STATUS_OK:
                included.append(name)
                libraries.append({g["appid"]: g for g in library.games})
            else:
                excluded.append((name, library.status))

        if len(libraries) < 2:
            return CommonGamesResult(included, excluded, [], 0, True)

        shared_ids = set(libraries[0]).intersection(*libraries[1:])
        games = [
            {
                "appid": appid,
                "name": libraries[0][appid]["name"],
                "playtime": sum(lib[appid]["playtime_forever"] for lib in libraries),
            }
            for appid in shared_ids
        ]
        games.sort(key=lambda g: (-g["playtime"], g["name"].lower()))
        return CommonGamesResult(included, excluded, games, len(games), False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/services/test_steam_service.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add website/services/steam.py tests/services/test_steam_service.py
git commit -m "feat(steam): add SteamService with cached libraries and common games"
```

---

### Task 5: Vérification de la signature Discord

**Files:**
- Create: `website/utils/discord_signature.py`
- Test: `tests/utils/test_discord_signature.py`

**Interfaces:**
- Produces: `verify_discord_signature(public_key: str, signature: str, timestamp: str, body: bytes) -> bool` (clé et signature en hexadécimal ; ne lève jamais d'exception).

- [ ] **Step 1: Write the failing test**

```python
# tests/utils/test_discord_signature.py
"""Tests for Discord Ed25519 request signature verification."""

import pytest
from nacl.signing import SigningKey

from website.utils.discord_signature import verify_discord_signature


@pytest.fixture
def keys():
    signing = SigningKey.generate()
    return signing, signing.verify_key.encode().hex()


def _sign(signing, timestamp, body):
    return signing.sign(timestamp.encode() + body).signature.hex()


def test_valid_signature(keys):
    signing, public = keys
    body = b'{"type":1}'
    assert verify_discord_signature(public, _sign(signing, "123", body), "123", body)


def test_modified_body_is_rejected(keys):
    signing, public = keys
    sig = _sign(signing, "123", b'{"type":1}')
    assert not verify_discord_signature(public, sig, "123", b'{"type":2}')


def test_modified_timestamp_is_rejected(keys):
    signing, public = keys
    body = b'{"type":1}'
    assert not verify_discord_signature(public, _sign(signing, "123", body), "124", body)


def test_other_key_is_rejected(keys):
    signing, _ = keys
    other_public = SigningKey.generate().verify_key.encode().hex()
    body = b"{}"
    assert not verify_discord_signature(other_public, _sign(signing, "1", body), "1", body)


@pytest.mark.parametrize("signature", ["", "zz", "00"])
def test_malformed_signature_is_rejected(keys, signature):
    _, public = keys
    assert not verify_discord_signature(public, signature, "1", b"{}")


def test_malformed_public_key_is_rejected(keys):
    signing, _ = keys
    body = b"{}"
    assert not verify_discord_signature("not-hex", _sign(signing, "1", body), "1", body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/utils/test_discord_signature.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'website.utils.discord_signature'`

- [ ] **Step 3: Write minimal implementation**

```python
# website/utils/discord_signature.py
"""Verification of Discord interaction request signatures (Ed25519)."""

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


def verify_discord_signature(public_key: str, signature: str, timestamp: str, body: bytes) -> bool:
    """Check that a request was signed by Discord.

    Args:
        public_key: Application public key, hex-encoded.
        signature: Value of the X-Signature-Ed25519 header, hex-encoded.
        timestamp: Value of the X-Signature-Timestamp header.
        body: Raw request body, exactly as received.

    Returns:
        True if the signature is valid, False otherwise (never raises).
    """
    try:
        VerifyKey(bytes.fromhex(public_key)).verify(
            timestamp.encode() + body, bytes.fromhex(signature)
        )
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/utils/test_discord_signature.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add website/utils/discord_signature.py tests/utils/test_discord_signature.py
git commit -m "feat(discord): add Ed25519 signature verification for interactions"
```

---

### Task 6: Messages des réponses (textes et embeds)

**Files:**
- Create: `website/utils/steam_embeds.py`
- Test: `tests/utils/test_steam_embeds.py`

**Interfaces:**
- Consumes: `CommonGamesResult`, constantes `STATUS_*` (Task 4).
- Produces:
  - `EXCLUSION_REASONS: dict[str, str]` ;
  - `build_common_games_payload(result: CommonGamesResult) -> dict` : charge du message Discord (`{"content": str}` ou `{"content": "", "embeds": [dict]}`) ;
  - `build_steam_status_message(status: str, game_count: int, login_url: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/utils/test_steam_embeds.py
"""Tests for Steam command response builders."""

from website.services.steam import (
    STATUS_NOT_LINKED,
    STATUS_OK,
    STATUS_PRIVATE,
    STATUS_UNAVAILABLE,
    CommonGamesResult,
)
from website.utils.steam_embeds import build_common_games_payload, build_steam_status_message


def _games(n, name_len=10):
    return [
        {"appid": i, "name": f"{'G' * name_len}{i}", "playtime": (n - i) * 60}
        for i in range(n)
    ]


def test_embed_lists_games_with_store_links():
    result = CommonGamesResult(["Alice", "Bob"], [], _games(2), 2, False)
    payload = build_common_games_payload(result)
    embed = payload["embeds"][0]
    assert embed["title"] == "🎮 Jeux en commun — Alice, Bob"
    assert "https://store.steampowered.com/app/0" in embed["description"]
    assert "https://store.steampowered.com/app/1" in embed["description"]
    assert "footer" not in embed


def test_list_is_cut_at_25_with_total():
    result = CommonGamesResult(["A", "B"], [], _games(47), 47, False)
    embed = build_common_games_payload(result)["embeds"][0]
    assert embed["description"].count("store.steampowered.com/app/") == 25
    assert "47 jeux en commun, voici les 25 plus joués." in embed["description"]


def test_footer_lists_excluded_members():
    result = CommonGamesResult(
        ["A", "B"], [("Bob", STATUS_NOT_LINKED), ("Carole", STATUS_PRIVATE)], _games(1), 1, False
    )
    footer = build_common_games_payload(result)["embeds"][0]["footer"]["text"]
    assert "Bob : Steam non relié" in footer
    assert "Carole : profil Steam privé" in footer


def test_embed_respects_discord_limits():
    names = [f"Joueur{i}" * 10 for i in range(10)]
    excluded = [(n, STATUS_UNAVAILABLE) for n in names]
    result = CommonGamesResult(names, excluded, _games(200, name_len=300), 200, False)
    embed = build_common_games_payload(result)["embeds"][0]
    assert len(embed["description"]) <= 4096
    assert len(embed["title"]) <= 256
    assert len(embed["footer"]["text"]) <= 2048


def test_too_few_members_message():
    result = CommonGamesResult(["Alice"], [("Bob", STATUS_PRIVATE)], [], 0, True)
    payload = build_common_games_payload(result)
    assert "embeds" not in payload
    assert "au moins deux" in payload["content"]
    assert "Bob : profil Steam privé" in payload["content"]


def test_no_common_game_message():
    result = CommonGamesResult(["Alice", "Bob"], [], [], 0, False)
    assert build_common_games_payload(result)["content"] == (
        "Aucun jeu en commun entre Alice, Bob."
    )


def test_status_messages():
    url = "https://example.test/login/"
    assert url in build_steam_status_message(STATUS_NOT_LINKED, 0, url)
    assert "Public" in build_steam_status_message(STATUS_PRIVATE, 0, url)
    assert "12 jeux" in build_steam_status_message(STATUS_OK, 12, url)
    assert "réessaie" in build_steam_status_message(STATUS_UNAVAILABLE, 0, url)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/utils/test_steam_embeds.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'website.utils.steam_embeds'`

- [ ] **Step 3: Write minimal implementation**

```python
# website/utils/steam_embeds.py
"""Discord message builders for the Steam commands."""

from config.constants import EMBED_COLOR_BLUE
from website.services.steam import (
    STATUS_NOT_LINKED,
    STATUS_OK,
    STATUS_PRIVATE,
    STATUS_UNAVAILABLE,
)

MAX_GAMES_SHOWN = 25
MAX_GAME_NAME = 80
TITLE_LIMIT = 256
DESCRIPTION_LIMIT = 4096
FOOTER_LIMIT = 2048
STORE_URL = "https://store.steampowered.com/app/{appid}"

EXCLUSION_REASONS = {
    STATUS_NOT_LINKED: "Steam non relié",
    STATUS_PRIVATE: "profil Steam privé",
    STATUS_UNAVAILABLE: "Steam n'a pas répondu",
}


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _excluded_lines(excluded) -> list[str]:
    return [f"{name} : {EXCLUSION_REASONS.get(status, status)}" for name, status in excluded]


def _game_line(game: dict) -> str:
    name = _truncate(game["name"], MAX_GAME_NAME).replace("[", "(").replace("]", ")")
    hours = game["playtime"] // 60
    return f"• [{name}]({STORE_URL.format(appid=game['appid'])}) — {hours} h à vous tous"


def build_common_games_payload(result) -> dict:
    """Build the Discord message answering /jeux-en-commun.

    Args:
        result: CommonGamesResult computed by SteamService.

    Returns:
        Discord message payload (content and/or embeds).
    """
    excluded = _excluded_lines(result.excluded)

    if result.too_few:
        lines = ["Il faut au moins deux bibliothèques Steam lisibles pour comparer."]
        lines += [f"- {line}" for line in excluded]
        lines.append("Chacun peut vérifier sa liaison avec /steam-statut.")
        return {"content": _truncate("\n".join(lines), 2000)}

    names = ", ".join(result.included)
    if not result.games:
        return {"content": _truncate(f"Aucun jeu en commun entre {names}.", 2000)}

    shown = result.games[:MAX_GAMES_SHOWN]
    footer_line = ""
    if result.total > len(shown):
        footer_line = (
            f"\n\n{result.total} jeux en commun, voici les {len(shown)} plus joués."
        )
    body = "\n".join(_game_line(g) for g in shown)
    description = _truncate(body, DESCRIPTION_LIMIT - len(footer_line)) + footer_line

    embed = {
        "title": _truncate(f"🎮 Jeux en commun — {names}", TITLE_LIMIT),
        "color": EMBED_COLOR_BLUE,
        "description": description,
    }
    if excluded:
        embed["footer"] = {"text": _truncate("Non pris en compte : " + " · ".join(excluded), FOOTER_LIMIT)}
    return {"content": "", "embeds": [embed]}


def build_steam_status_message(status: str, game_count: int, login_url: str) -> str:
    """Build the private answer to /steam-statut.

    Args:
        status: Library status of the member.
        game_count: Number of games when status is ok.
        login_url: QuestMaster login URL.

    Returns:
        Message text.
    """
    if status == STATUS_OK:
        return f"✅ Steam relié : {game_count} jeux trouvés dans ta bibliothèque."
    if status == STATUS_PRIVATE:
        return (
            "🔒 Ton Steam est relié, mais tes jeux sont privés. Dans Steam : Profil → Modifier "
            "le profil → Confidentialité → Détails des jeux : **Public**. "
            "La prise en compte peut prendre jusqu'à 6 h."
        )
    if status == STATUS_UNAVAILABLE:
        return "⚠️ Steam ne répond pas pour le moment, réessaie plus tard."
    return (
        "❌ Steam n'est pas relié. Dans Discord : Paramètres → Connexions → Steam, "
        f"puis reconnecte-toi sur QuestMaster : {login_url}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/utils/test_steam_embeds.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add website/utils/steam_embeds.py tests/utils/test_steam_embeds.py
git commit -m "feat(steam): add Discord message builders for Steam commands"
```

---

### Task 7: Client Discord (suivi d'interaction) et enregistrement des commandes

**Files:**
- Modify: `website/client/discord.py` (nouvelles méthodes à la fin de la classe `Discord`)
- Create: `website/utils/discord_commands.py`
- Modify: `website/extensions.py` (nouvelle commande CLI après `seed_trophies`)
- Modify: `website/__init__.py:83-84` (enregistrement de la commande CLI)
- Test: `tests/client/test_discord_interactions_client.py`, `tests/test_cli_register_commands.py`

**Interfaces:**
- Consumes: `get_bot()` (`website/bot.py`).
- Produces:
  - `Discord.edit_interaction_response(application_id: str, token: str, payload: dict) -> dict` ;
  - `Discord.register_guild_commands(application_id: str, commands: list[dict]) -> list | dict` ;
  - `DISCORD_COMMANDS: list[dict]` dans `website/utils/discord_commands.py` ;
  - commande CLI `flask register-discord-commands`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/client/test_discord_interactions_client.py
"""Tests for interaction-related Discord client methods."""

from unittest.mock import MagicMock

from website.client.discord import Discord
from website.utils.discord_commands import DISCORD_COMMANDS


def _client():
    client = Discord.__new__(Discord)  # skip __init__, which calls the live API
    client.guild_id = "guild1"
    client._request = MagicMock(return_value={})
    return client


def test_edit_interaction_response():
    client = _client()
    client.edit_interaction_response("app1", "tok", {"content": "hi"})
    client._request.assert_called_once_with(
        "PATCH", "/webhooks/app1/tok/messages/@original", json={"content": "hi"}
    )


def test_register_guild_commands():
    client = _client()
    client.register_guild_commands("app1", DISCORD_COMMANDS)
    client._request.assert_called_once_with(
        "PUT", "/applications/app1/guilds/guild1/commands", json=DISCORD_COMMANDS
    )


def test_command_definitions():
    by_name = {c["name"]: c for c in DISCORD_COMMANDS}
    assert set(by_name) == {"steam-statut", "jeux-en-commun"}
    options = by_name["jeux-en-commun"]["options"]
    assert [o["name"] for o in options] == [f"joueur{i}" for i in range(1, 10)]
    assert all(o["type"] == 6 for o in options)
    assert options[0]["required"] is True
    assert not any(o.get("required") for o in options[1:])
```

```python
# tests/test_cli_register_commands.py
"""Tests for the register-discord-commands CLI command."""

from unittest.mock import MagicMock, patch

from website.utils.discord_commands import DISCORD_COMMANDS


def test_register_discord_commands(test_app, monkeypatch):
    bot = MagicMock()
    bot.register_guild_commands.return_value = [{"name": "a"}, {"name": "b"}]
    monkeypatch.setitem(test_app.config, "DISCORD_CLIENT_ID", "app1")
    with patch("website.extensions.get_bot", return_value=bot):
        result = test_app.test_cli_runner().invoke(args=["register-discord-commands"])
    assert result.exit_code == 0, result.output
    bot.register_guild_commands.assert_called_once_with("app1", DISCORD_COMMANDS)
    assert "2 commandes" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/client/test_discord_interactions_client.py tests/test_cli_register_commands.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'website.utils.discord_commands'`

- [ ] **Step 3: Write minimal implementation**

`website/utils/discord_commands.py` :

```python
"""Definitions of QuestMaster's Discord slash commands."""

USER_OPTION = 6
MAX_PLAYERS = 9

DISCORD_COMMANDS = [
    {
        "name": "steam-statut",
        "description": "Vérifier si ton compte Steam est relié à QuestMaster",
        "type": 1,
    },
    {
        "name": "jeux-en-commun",
        "description": "Trouver les jeux Steam que vous possédez tous",
        "type": 1,
        "options": [
            {
                "name": f"joueur{i}",
                "description": "Un joueur avec qui comparer ta bibliothèque Steam",
                "type": USER_OPTION,
                "required": i == 1,
            }
            for i in range(1, MAX_PLAYERS + 1)
        ],
    },
]
```

Dans `website/client/discord.py`, à la fin de la classe `Discord` :

```python
    def edit_interaction_response(self, application_id: str, token: str, payload: dict) -> dict:
        """Replace the original response of an interaction.

        Args:
            application_id: Discord application ID (from the interaction).
            token: Interaction token, valid for 15 minutes.
            payload: New message payload (content, embeds).

        Returns:
            The edited message object.
        """
        return self._request(
            "PATCH", f"/webhooks/{application_id}/{token}/messages/@original", json=payload
        )

    def register_guild_commands(self, application_id: str, commands: list[dict]):
        """Overwrite the application's slash commands on the guild.

        Args:
            application_id: Discord application ID.
            commands: Command definitions.

        Returns:
            The list of registered commands.
        """
        return self._request(
            "PUT", f"/applications/{application_id}/guilds/{self.guild_id}/commands", json=commands
        )
```

Dans `website/extensions.py` : ajouter aux imports `from flask import current_app` et `from website.bot import get_bot` (en tête du module, avec les autres imports), puis après la commande `seed_trophies` :

```python
@click.command("register-discord-commands")
@with_appcontext
def register_discord_commands():
    """CLI command to register QuestMaster's slash commands on the guild."""
    from website.utils.discord_commands import DISCORD_COMMANDS

    registered = get_bot().register_guild_commands(
        current_app.config["DISCORD_CLIENT_ID"], DISCORD_COMMANDS
    )
    click.echo(f"{len(registered)} commandes enregistrées.")
```

`website/bot.py` n'importe rien du projet : l'importer en tête de `extensions.py` ne crée pas d'import circulaire (vérifier quand même avec `.venv/bin/python -c "import website"`).

Dans `website/__init__.py` : ajouter `register_discord_commands` à l'import `from website.extensions import …` et, après `app.cli.add_command(setup_test_db)` :

```python
    app.cli.add_command(register_discord_commands)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/client/test_discord_interactions_client.py tests/test_cli_register_commands.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add website/client/discord.py website/utils/discord_commands.py website/extensions.py website/__init__.py tests/client/test_discord_interactions_client.py tests/test_cli_register_commands.py
git commit -m "feat(discord): add interaction follow-up and slash command registration"
```

---

### Task 8: Blueprint des interactions (`/steam-statut`, `/jeux-en-commun`)

**Files:**
- Create: `website/views/interactions.py`
- Modify: `website/views/__init__.py` (import et `register_blueprints`)
- Test: `tests/views/test_interactions.py`

**Interfaces:**
- Consumes: `verify_discord_signature` (Task 5), `SteamService`, `STATUS_OK` (Task 4), `build_common_games_payload`, `build_steam_status_message` (Task 6), `Discord.edit_interaction_response` via `get_bot()` (Task 7), `UserService().repo.get_by_id(user_id) -> User | None`.
- Produces: blueprint `interactions_bp`, route `POST /discord/interactions/` ; fonctions internes `_start_background(target, *args)` (patchée dans les tests) et `_run_common_games(app, application_id, token, members)` où `members: list[tuple[str, str]]` = (identifiant Discord, pseudo).

- [ ] **Step 1: Write the failing tests**

```python
# tests/views/test_interactions.py
"""Tests for the Discord interactions endpoint."""

import json
from unittest.mock import MagicMock, patch

import pytest
from nacl.signing import SigningKey

from tests.constants import TEST_ADMIN_USER_ID, TEST_REGULAR_USER_ID
from website.services.steam import STATUS_NOT_LINKED, STATUS_OK, CommonGamesResult, LibraryResult

URL = "/discord/interactions/"


@pytest.fixture
def signing_key(test_app):
    key = SigningKey.generate()
    previous = test_app.config.get("DISCORD_PUBLIC_KEY")
    test_app.config["DISCORD_PUBLIC_KEY"] = key.verify_key.encode().hex()
    yield key
    test_app.config["DISCORD_PUBLIC_KEY"] = previous


def _post(client, key, payload, tamper=False):
    body = json.dumps(payload).encode()
    timestamp = "1700000000"
    signature = key.sign(timestamp.encode() + body).signature.hex()
    if tamper:
        body = body.replace(b"}", b' }', 1)
    return client.post(
        URL,
        data=body,
        content_type="application/json",
        headers={"X-Signature-Ed25519": signature, "X-Signature-Timestamp": timestamp},
    )


def _command(name, options=None, resolved=None, invoker=TEST_REGULAR_USER_ID, dm=False):
    payload = {
        "type": 2,
        "application_id": "app1",
        "token": "tok",
        "data": {"name": name, "options": options or [], "resolved": {"users": resolved or {}}},
    }
    user = {"id": invoker, "username": "invoker", "global_name": "Invoker"}
    if dm:
        payload["user"] = user
    else:
        payload["member"] = {"user": user, "nick": None}
    return payload


def _opt(i, user_id):
    return {"name": f"joueur{i}", "type": 6, "value": user_id}


def test_ping(client, db_session, signing_key):
    response = _post(client, signing_key, {"type": 1})
    assert response.status_code == 200
    assert response.get_json() == {"type": 1}


def test_bad_signature_is_rejected(client, db_session, signing_key):
    response = _post(client, signing_key, {"type": 1}, tamper=True)
    assert response.status_code == 401


def test_missing_public_key_returns_503(client, db_session, test_app):
    previous = test_app.config.get("DISCORD_PUBLIC_KEY")
    test_app.config["DISCORD_PUBLIC_KEY"] = None
    try:
        response = client.post(URL, data=b'{"type":1}', content_type="application/json")
    finally:
        test_app.config["DISCORD_PUBLIC_KEY"] = previous
    assert response.status_code == 503


def test_steam_status_is_ephemeral(client, db_session, signing_key):
    service = MagicMock()
    service.get_library.return_value = LibraryResult(STATUS_OK, [{"appid": 1}] * 3)
    with patch("website.views.interactions.SteamService", return_value=service):
        response = _post(client, signing_key, _command("steam-statut"))
    data = response.get_json()
    assert data["type"] == 4
    assert data["data"]["flags"] == 64
    assert "3 jeux" in data["data"]["content"]


def test_common_games_defers_then_edits_response(client, db_session, signing_key):
    service = MagicMock()
    service.common_games.return_value = CommonGamesResult(
        ["Invoker", "Admin"], [], [{"appid": 7, "name": "Valheim", "playtime": 120}], 1, False
    )
    bot = MagicMock()
    options = [_opt(1, TEST_ADMIN_USER_ID)]
    resolved = {TEST_ADMIN_USER_ID: {"id": TEST_ADMIN_USER_ID, "username": "admin", "global_name": "Admin"}}
    with (
        patch("website.views.interactions.SteamService", return_value=service),
        patch("website.views.interactions.get_bot", return_value=bot),
        patch(
            "website.views.interactions._start_background",
            side_effect=lambda target, *args: target(*args),
        ),
    ):
        response = _post(client, signing_key, _command("jeux-en-commun", options, resolved))

    assert response.get_json() == {"type": 5}
    members = service.common_games.call_args.args[0]
    assert [name for name, _ in members] == ["Invoker", "Admin"]
    app_id, token, payload = bot.edit_interaction_response.call_args.args
    assert (app_id, token) == ("app1", "tok")
    assert "Valheim" in payload["embeds"][0]["description"]


def test_duplicates_and_self_mention_count_once(client, db_session, signing_key):
    options = [_opt(1, TEST_REGULAR_USER_ID), _opt(2, TEST_REGULAR_USER_ID)]
    with patch("website.views.interactions._start_background") as start:
        response = _post(client, signing_key, _command("jeux-en-commun", options))
    data = response.get_json()
    assert data["type"] == 4
    assert data["data"]["flags"] == 64
    assert "au moins un autre joueur" in data["data"]["content"]
    start.assert_not_called()


def test_unknown_member_is_not_linked(client, db_session, signing_key):
    service = MagicMock()
    service.common_games.return_value = CommonGamesResult(
        ["Invoker"], [("Robot", STATUS_NOT_LINKED)], [], 0, True
    )
    options = [_opt(1, "123456789012345678")]
    resolved = {"123456789012345678": {"id": "123456789012345678", "username": "robot", "global_name": "Robot", "bot": True}}
    with (
        patch("website.views.interactions.SteamService", return_value=service),
        patch("website.views.interactions.get_bot", return_value=MagicMock()),
        patch(
            "website.views.interactions._start_background",
            side_effect=lambda target, *args: target(*args),
        ),
    ):
        _post(client, signing_key, _command("jeux-en-commun", options, resolved))
    members = service.common_games.call_args.args[0]
    assert members[1] == ("Robot", None)


def test_command_from_direct_message(client, db_session, signing_key):
    service = MagicMock()
    service.get_library.return_value = LibraryResult(STATUS_NOT_LINKED)
    with patch("website.views.interactions.SteamService", return_value=service):
        response = _post(client, signing_key, _command("steam-statut", dm=True))
    assert response.status_code == 200
    user_arg = service.get_library.call_args.args[0]
    assert user_arg is not None and user_arg.id == TEST_REGULAR_USER_ID


def test_background_error_edits_response_with_error_message(client, db_session, signing_key):
    service = MagicMock()
    service.common_games.side_effect = RuntimeError("boom")
    bot = MagicMock()
    with (
        patch("website.views.interactions.SteamService", return_value=service),
        patch("website.views.interactions.get_bot", return_value=bot),
        patch(
            "website.views.interactions._start_background",
            side_effect=lambda target, *args: target(*args),
        ),
    ):
        _post(client, signing_key, _command("jeux-en-commun", [_opt(1, TEST_ADMIN_USER_ID)]))
    payload = bot.edit_interaction_response.call_args.args[2]
    assert payload == {"content": "Une erreur est survenue, réessaie plus tard."}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/views/test_interactions.py -v`
Expected: FAIL (404 sur `/discord/interactions/`)

- [ ] **Step 3: Write minimal implementation**

```python
# website/views/interactions.py
"""Discord interactions endpoint (slash commands received over HTTP)."""

import json
import threading

from flask import Blueprint, current_app, jsonify, request

from config.constants import SITE_BASE_URL
from website.bot import get_bot
from website.extensions import csrf, db
from website.services.steam import STATUS_OK, SteamService
from website.services.user import UserService
from website.utils.discord_signature import verify_discord_signature
from website.utils.logger import logger
from website.utils.steam_embeds import build_common_games_payload, build_steam_status_message

interactions_bp = Blueprint("interactions", __name__)
csrf.exempt(interactions_bp)

PING = 1
APPLICATION_COMMAND = 2
PONG = 1
CHANNEL_MESSAGE = 4
DEFERRED_CHANNEL_MESSAGE = 5
EPHEMERAL = 64
ERROR_MESSAGE = "Une erreur est survenue, réessaie plus tard."


def _ephemeral(content: str) -> dict:
    return {"type": CHANNEL_MESSAGE, "data": {"content": content, "flags": EPHEMERAL}}


def _display_name(user: dict, nick=None) -> str:
    return nick or user.get("global_name") or user.get("username") or "Inconnu"


def _invoker(payload: dict) -> tuple[str, str]:
    member = payload.get("member")
    if member:
        return member["user"]["id"], _display_name(member["user"], member.get("nick"))
    user = payload.get("user", {})
    return user.get("id"), _display_name(user)


def _start_background(target, *args):
    threading.Thread(target=target, args=args, daemon=True).start()


def _steam_status(payload: dict) -> dict:
    user_id, _ = _invoker(payload)
    user = UserService().repo.get_by_id(user_id)
    library = SteamService().get_library(user)
    count = len(library.games) if library.status == STATUS_OK else 0
    return _ephemeral(build_steam_status_message(library.status, count, f"{SITE_BASE_URL}/login/"))


def _run_common_games(app, application_id: str, token: str, members: list[tuple[str, str]]):
    with app.app_context():
        try:
            repo = UserService().repo
            group = [(name, repo.get_by_id(user_id)) for user_id, name in members]
            message = build_common_games_payload(SteamService().common_games(group))
        except Exception:
            logger.exception("Failed to compute common Steam games")
            message = {"content": ERROR_MESSAGE}
        try:
            get_bot().edit_interaction_response(application_id, token, message)
        except Exception:
            logger.exception("Failed to edit interaction response")
        finally:
            db.session.remove()


def _common_games(payload: dict) -> dict:
    data = payload.get("data", {})
    resolved = data.get("resolved", {}).get("users", {})
    invoker_id, invoker_name = _invoker(payload)

    members, seen = [(invoker_id, invoker_name)], {invoker_id}
    for option in data.get("options", []):
        user_id = option.get("value")
        if user_id and user_id not in seen:
            seen.add(user_id)
            members.append((user_id, _display_name(resolved.get(user_id, {}))))

    if len(members) < 2:
        return _ephemeral("Mentionne au moins un autre joueur que toi.")

    _start_background(
        _run_common_games,
        current_app._get_current_object(),
        payload["application_id"],
        payload["token"],
        members,
    )
    return {"type": DEFERRED_CHANNEL_MESSAGE}


@interactions_bp.route("/discord/interactions/", methods=["POST"])
def interactions():
    """Receive and answer Discord interactions."""
    public_key = current_app.config.get("DISCORD_PUBLIC_KEY")
    if not public_key:
        logger.error("DISCORD_PUBLIC_KEY is not configured, refusing interactions")
        return jsonify(error="interactions not configured"), 503

    body = request.get_data()
    if not verify_discord_signature(
        public_key,
        request.headers.get("X-Signature-Ed25519", ""),
        request.headers.get("X-Signature-Timestamp", ""),
        body,
    ):
        return jsonify(error="invalid request signature"), 401

    payload = json.loads(body)
    if payload.get("type") == PING:
        return jsonify(type=PONG)

    if payload.get("type") == APPLICATION_COMMAND:
        name = payload.get("data", {}).get("name")
        if name == "steam-statut":
            return jsonify(_steam_status(payload))
        if name == "jeux-en-commun":
            return jsonify(_common_games(payload))

    return jsonify(_ephemeral("Commande inconnue."))
```

Dans `website/views/__init__.py` : ajouter `from .interactions import interactions_bp` aux imports et `app.register_blueprint(interactions_bp)` à la fin de `register_blueprints`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/views/test_interactions.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add website/views/interactions.py website/views/__init__.py tests/views/test_interactions.py
git commit -m "feat(discord): add interactions endpoint with /steam-statut and /jeux-en-commun"
```

---

### Task 9: Vérification complète, documentation et mise en service

**Files:**
- Modify: `decisions.md` (nouvelle section)
- Modify: `CLAUDE.md` du projet uniquement s'il est suivi par git (`git ls-files CLAUDE.md`) ; sinon ne pas y toucher.

- [ ] **Step 1: Run the full test suite and linters**

```bash
.venv/bin/python -m pytest tests/ -m "not integration" -q
.venv/bin/python -m pytest tests/views -q
.venv/bin/black -l 99 --check website/ config/ tests/
.venv/bin/isort --check website/ config/ tests/
.venv/bin/flake8 website/
.venv/bin/pydoclint website/
```
Expected: tous les tests passent, sauf les 2 tests `tests/views/test_e2e.py` qui appellent le vrai Discord et échouaient déjà avant ce travail. Aucune nouvelle alerte des linters dans les fichiers créés ou modifiés (les 2 alertes E501 existantes de `website/client/discord.py:205` et `website/services/game.py` restent hors périmètre).

- [ ] **Step 2: Fresh dependency resolution (as on the server)**

```bash
S=$(mktemp -d); uv venv -q -p 3.13 $S/venv && VIRTUAL_ENV=$S/venv uv pip install -q --no-cache .
$S/venv/bin/python -c "import nacl, sqlalchemy; print(nacl.__version__, sqlalchemy.__version__)"
rm -rf $S
```
Expected: `1.6.2 2.0.49`. L'image Docker est sous Alpine : si PyNaCl n'a pas de wheel musllinux pour cette version, il se compile avec `build-base` et `libffi-dev`, déjà présents dans l'étape `builder` du `Dockerfile`. Rien à ajouter, mais le build sera plus long.

- [ ] **Step 3: Document the decisions**

Ajouter à la fin de `decisions.md` :

```markdown
## 9. Jeux Steam en commun (2026-10-02)

Conception complète : `docs/superpowers/specs/2026-10-02-steam-jeux-en-commun-design.md`.

- Commandes Discord reçues par HTTP sur `POST /discord/interactions/` (signature Ed25519
  vérifiée), sans bot connecté en permanence.
- SteamID lu dans les connexions Discord à la connexion au site (permission « connexions »).
  Une connexion Steam absente n'efface jamais un SteamID déjà enregistré.
- Bibliothèques gardées 6 h dans Redis (`steam:library:<steam_id>`) ; « Steam indisponible »
  n'est jamais mis en cache.
- `/jeux-en-commun` : auteur toujours inclus, doublons ignorés, 25 jeux au plus, triés par temps
  de jeu cumulé puis par nom. Les membres non reliés, privés ou injoignables sont exclus et cités.
- Commandes enregistrées sur le serveur du club seulement (`flask register-discord-commands`).
```

- [ ] **Step 4: Commit**

```bash
git add decisions.md
git commit -m "docs: record Steam common games decisions"
```

- [ ] **Step 5: Mise en service (manuel, par Séb, après accord)**

Ne pas pousser ni déployer sans l'accord de Séb. Une fois d'accord :
1. Créer la clé d'API Steam sur https://steamcommunity.com/dev/apikey (nom de domaine : `questmaster.sebgal.net`).
2. Portail développeur Discord → application QuestMaster → General Information : copier la **Public Key**.
3. Portainer : ajouter `STEAM_API_KEY` et `DISCORD_PUBLIC_KEY` aux variables de la stack. Dans `docker-compose.prod.yml`, ajouter aussi les lignes `- STEAM_API_KEY=${STEAM_API_KEY}` et `- DISCORD_PUBLIC_KEY=${DISCORD_PUBLIC_KEY}` dans la liste `environment:` du service `app` (même format que `- DISCORD_CLIENT_ID=${DISCORD_CLIENT_ID}`, ligne 23), dans un commit avant le push.
4. `git push origin main`, puis « Pull and redeploy » (sans « Re-pull image »). La migration `steam_id` s'applique au démarrage.
5. Dans le conteneur : `docker exec questmaster-app-1 flask register-discord-commands` → « 2 commandes enregistrées. »
6. Portail Discord → General Information → **Interactions Endpoint URL** : `https://questmaster.sebgal.net/discord/interactions/` → Save (Discord valide l'adresse par un PING signé).
7. Test : `/steam-statut`, puis `/jeux-en-commun @quelqu'un` dans un salon du serveur.
