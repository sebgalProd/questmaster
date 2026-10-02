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
