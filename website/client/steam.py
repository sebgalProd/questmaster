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
