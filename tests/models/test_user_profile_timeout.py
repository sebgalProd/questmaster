"""The avatar check in get_user_profile must not hang without a timeout."""

from unittest.mock import MagicMock, patch

from website.models.user import get_user_profile


def test_avatar_head_request_has_timeout(test_app):
    bot = MagicMock()
    bot.get_user.return_value = {"user": {"id": "1", "username": "u", "avatar": "abc"}}
    with (
        test_app.app_context(),
        patch("website.models.user.get_bot", return_value=bot),
        patch("website.models.user.cache") as cache,
        patch("website.models.user.requests.head") as head,
    ):
        cache.get.return_value = None
        head.return_value = MagicMock(status_code=200)
        get_user_profile("123456789012345678", force_refresh=True)
    assert head.call_args.kwargs.get("timeout")
