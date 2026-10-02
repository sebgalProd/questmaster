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
    """Run ``target(*args)`` in a daemon thread that closes its DB session at the end."""

    def runner():
        try:
            target(*args)
        finally:
            db.session.remove()

    threading.Thread(target=runner, daemon=True).start()


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
    """Receive and answer Discord interactions.

    Returns:
        JSON response for Discord, or 401/503 on a bad signature or missing key.
    """
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
