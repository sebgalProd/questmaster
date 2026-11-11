"""User service for user-related business logic."""

import re
from datetime import datetime, timezone

from sqlalchemy import func

from website.exceptions import NotFoundError, ValidationError
from website.extensions import db
from website.models import User
from website.models.user import get_user_profile as _get_user_profile
from website.repositories.user import UserRepository


class UserService:
    """Service layer for User operations.

    Handles user retrieval, creation, and Discord profile management.
    """

    def __init__(self, repository=None):
        self.repo = repository or UserRepository()

    def get_by_id(self, user_id: str) -> User:
        """Get user by ID.

        Args:
            user_id: Discord user ID.

        Returns:
            User instance.

        Raises:
            NotFoundError: If user does not exist.
        """
        user = self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(
                f"User with id {user_id} not found",
                resource_type="User",
                resource_id=user_id,
            )
        return user

    def get_or_create(
        self, user_id: str, name: str = "Inconnu", username: str | None = None
    ) -> tuple[User, bool]:
        """Get an existing user or create a new one.

        Args:
            user_id: Discord user ID.
            name: Display name for new users. Defaults to 'Inconnu'.
            username: Stable Discord username (optional).

        Returns:
            Tuple of (User, created) where created is True if the user was new.
        """
        user = self.repo.get_by_id(user_id)
        if user:
            return user, False
        user = User(id=user_id, name=name, username=username)
        self.repo.add(user)
        db.session.commit()
        user.init_on_load()
        return user, True

    def resolve_member(self, query: str, discord) -> User:
        """Find a member from a Discord ID or a pseudo typed by a person.

        Known members are looked up by name first; otherwise the Discord server is
        searched, and a member found there is created in the database.

        Args:
            query: Discord ID, or name, username or server nickname (a leading @ is ignored).
            discord: DiscordService used to search the server's members.

        Returns:
            The matching User.

        Raises:
            ValidationError: If nobody or several members match.
        """
        query = query.strip().lstrip("@").strip()
        if not query:
            raise ValidationError("Indiquez un pseudo ou un ID Discord.", field="member")
        if re.fullmatch(r"\d{17,21}", query):
            return self.get_or_create(query)[0]

        lowered = query.lower()
        known = (
            User.query.filter(
                (func.lower(User.name) == lowered) | (func.lower(User.username) == lowered)
            )
            .limit(2)
            .all()
        )
        if len(known) == 1:
            return known[0]

        members = discord.search_members(query, limit=10)
        exact = [m for m in members if lowered in _member_names(m)]
        candidates = exact or members
        if not candidates:
            raise ValidationError(
                f"Personne ne s'appelle « {query} » sur le serveur.", field="member"
            )
        if len(candidates) > 1:
            names = ", ".join(_member_label(m) for m in candidates)
            raise ValidationError(
                f"Plusieurs membres correspondent à « {query} » : {names}. "
                "Précisez le pseudo ou utilisez l'ID Discord.",
                field="member",
            )
        member = candidates[0]
        user = member["user"]
        return self.get_or_create(
            user["id"], name=_member_label(member), username=user.get("username")
        )[0]

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

    def get_all(self) -> list[User]:
        """Get all users.

        Returns:
            List of all User instances.
        """
        return self.repo.get_all()

    def get_active_users(self) -> list[User]:
        """Get all users not marked as inactive.

        Returns:
            List of active User instances.
        """
        return self.repo.get_active_users()

    def get_active_user_ids(self) -> list[str]:
        """Get IDs of all users not marked as inactive.

        Lightweight query that avoids loading full ORM objects.

        Returns:
            List of active user ID strings.
        """
        return self.repo.get_active_user_ids()

    def get_inactive_users(self) -> list[User]:
        """Get all users marked as inactive.

        Returns:
            List of inactive User instances.
        """
        return self.repo.get_inactive_users()

    def get_inactive_user_ids(self) -> list[str]:
        """Get IDs of all users marked as inactive.

        Lightweight query that avoids loading full ORM objects.

        Returns:
            List of inactive user ID strings.
        """
        return self.repo.get_inactive_user_ids()

    def get_by_ids(self, ids: list[str]) -> list[User]:
        """Get users by a list of IDs.

        Args:
            ids: List of user ID strings.

        Returns:
            List of User instances matching the given IDs.
        """
        return self.repo.get_by_ids(ids)

    @staticmethod
    def get_user_profile(user_id: str, force_refresh: bool = False) -> dict:
        """Fetch a user's Discord profile.

        Args:
            user_id: Discord user ID.
            force_refresh: If True, bypass cache and fetch from Discord.

        Returns:
            Dict with 'name', 'avatar', and optionally 'not_found' keys.
        """
        return _get_user_profile(user_id, force_refresh=force_refresh)

    def mark_inactive(self, user_id: str) -> User:
        """Mark a user as inactive (left the Discord server).

        Args:
            user_id: Discord user ID.

        Returns:
            Updated User instance.

        Raises:
            NotFoundError: If user does not exist.
        """
        user = self.get_by_id(user_id)
        user.not_player_as_of = datetime.now(timezone.utc)
        db.session.commit()
        return user

    def clear_inactive(self, user_id: str) -> User:
        """Clear the inactive flag for a user (they have rejoined).

        Args:
            user_id: Discord user ID.

        Returns:
            Updated User instance.

        Raises:
            NotFoundError: If user does not exist.
        """
        user = self.get_by_id(user_id)
        user.not_player_as_of = None
        db.session.commit()
        return user


def _member_names(member: dict) -> set[str]:
    user = member.get("user", {})
    names = (member.get("nick"), user.get("global_name"), user.get("username"))
    return {n.lower() for n in names if n}


def _member_label(member: dict) -> str:
    user = member.get("user", {})
    return member.get("nick") or user.get("global_name") or user.get("username") or user["id"]
