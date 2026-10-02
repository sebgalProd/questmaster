"""Channel service for Discord category management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from website.exceptions import NotFoundError
from website.extensions import db
from website.models import Channel
from website.repositories.channel import ChannelRepository
from website.utils.logger import logger

# Categories to use when a game type has no category of its own.
# Oneshots and campaigns are both tabletop RPGs and can share a category.
CATEGORY_FALLBACKS = {
    "oneshot": ("campaign",),
    "campaign": ("oneshot",),
    "videogame": ("oneshot", "campaign"),
    "salon": ("oneshot", "campaign"),
}

if TYPE_CHECKING:
    from website.models import Game
    from website.services.discord import DiscordService


class ChannelService:
    """Service layer for Channel (Discord category) management.

    Handles category size tracking for Discord channel organization.
    """

    def __init__(self, repository=None):
        self.repo = repository or ChannelRepository()

    def get_category(self, game_type: str) -> Channel:
        """Get the smallest category for a game type.

        A type without a category of its own uses the categories of
        another type (see ``CATEGORY_FALLBACKS``): oneshots and campaigns
        share their categories, videogames and salons go with the RPGs
        until an admin registers a category for them.

        Args:
            game_type: Type of game (oneshot, campaign, videogame, salon).

        Returns:
            Channel category with smallest size.

        Raises:
            NotFoundError: If no category found for type.
        """
        category = self.repo.get_smallest_by_type(game_type)
        for fallback_type in CATEGORY_FALLBACKS.get(game_type, ()):
            if category:
                break
            category = self.repo.get_smallest_by_type(fallback_type)
            if category:
                logger.info(f"No channel category for type '{game_type}', using '{fallback_type}'")
        if not category:
            raise NotFoundError(
                f"No channel category found for type '{game_type}'",
                resource_type="Channel",
            )
        return category

    def get_voice_category(self) -> Channel | None:
        """Get the voice category, or None if not configured.

        Returns:
            Voice Channel category, or None if not configured.
        """
        return self.repo.get_voice_category()

    def increment_size(self, channel: Channel) -> None:
        """Increment the channel count for a category.

        Args:
            channel: Channel category to increment.
        """
        self.repo.increment_size(channel)

    def adjust_category_size(self, discord_service: DiscordService, game: Game) -> None:
        """Decrement category size when a game channel is deleted.

        Args:
            discord_service: DiscordService instance for API calls.
            game: Game instance with channel to look up.
        """
        try:
            discord_channel = discord_service.get_channel(game.channel)
            parent_id = discord_channel.get("parent_id")
            if parent_id:
                category = self.repo.get_by_id(parent_id)
                if category:
                    self.repo.decrement_size(category)
                    db.session.commit()
                    logger.info(f"Decreased size of category {category.id} to {category.size}")
        except Exception as e:
            logger.warning(f"Failed to adjust category size for game {game.id}: {e}")
