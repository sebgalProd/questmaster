"""Templates must HTML-escape user-controlled values (XSS protection).

Templates use the ``.j2`` extension, which Flask does not autoescape by
default; the app enables it explicitly.
"""

from tests.factories import UserFactory


class TestAutoescape:
    """Discord display names are user-controlled and must be escaped."""

    def test_player_name_is_escaped_on_game_details(
        self, client, mock_discord_lookups, db_session, open_game
    ):
        player = UserFactory(db_session, name="<b>x</b>")
        open_game.players.append(player)
        db_session.flush()

        response = client.get(f"/annonces/{open_game.slug}/")
        body = response.data.decode()

        assert response.status_code == 200
        assert "&lt;b&gt;x&lt;/b&gt;" in body
        assert "<b>x</b>" not in body


class TestTrustedMarkup:
    """HTML built by the app itself must still render as HTML."""

    def test_unknown_badge_user_flash_keeps_link(
        self, logged_in_user, mock_discord_lookups, db_session
    ):
        response = logged_in_user.get("/badges/?user_id=0", follow_redirects=True)
        body = response.data.decode()

        assert response.status_code == 200
        assert '<a href="https://support.discord.com/' in body
        assert "&lt;a href" not in body
