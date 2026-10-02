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
        {"appid": i, "name": f"{'G' * name_len}{i}", "playtime": (n - i) * 60} for i in range(n)
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
