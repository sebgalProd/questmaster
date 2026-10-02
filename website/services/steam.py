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

        if games is None:
            result = LibraryResult(STATUS_PRIVATE)
        else:
            result = LibraryResult(STATUS_OK, games)
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
