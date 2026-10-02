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
CONTENT_LIMIT = 2000
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
        return {"content": _truncate("\n".join(lines), CONTENT_LIMIT)}

    names = ", ".join(result.included)
    if not result.games:
        return {"content": _truncate(f"Aucun jeu en commun entre {names}.", CONTENT_LIMIT)}

    shown = result.games[:MAX_GAMES_SHOWN]
    total_line = ""
    if result.total > len(shown):
        total_line = f"\n\n{result.total} jeux en commun, voici les {len(shown)} plus joués."
    body = "\n".join(_game_line(g) for g in shown)
    description = _truncate(body, DESCRIPTION_LIMIT - len(total_line)) + total_line

    embed = {
        "title": _truncate(f"🎮 Jeux en commun — {names}", TITLE_LIMIT),
        "color": EMBED_COLOR_BLUE,
        "description": description,
    }
    if excluded:
        footer = "Non pris en compte : " + " · ".join(excluded)
        embed["footer"] = {"text": _truncate(footer, FOOTER_LIMIT)}
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
