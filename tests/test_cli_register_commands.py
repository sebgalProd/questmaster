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
