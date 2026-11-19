"""Resolve today's Daily Calm through Home Assistant's media browser."""

import asyncio

from calm_client import is_available
from calm_client.exceptions import CalmAPIError, CalmAuthError
from homeassistant.components.media_player import BrowseError, MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant
from httpx import HTTPError

from . import CalmConfigEntry, async_store_credentials
from .const import DOMAIN

DAILY_MEDIA_ID = "daily"


async def async_get_media_source(hass: HomeAssistant) -> CalmMediaSource:
    """Return the Calm media source."""
    return CalmMediaSource(hass)


class CalmMediaSource(MediaSource):
    """Expose a stable identifier for the changing daily session."""

    name = "Calm"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the media source."""
        super().__init__(DOMAIN)
        self.hass = hass
        self._lock = asyncio.Lock()

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Offer Daily Calm in the media picker."""
        if item.identifier:
            raise BrowseError("Unknown Calm folder")
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.APP,
            media_content_type="",
            title=self.name,
            can_play=False,
            can_expand=True,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=DAILY_MEDIA_ID,
                    media_class=MediaClass.TRACK,
                    media_content_type=MediaType.MUSIC,
                    title="Daily Calm",
                    can_play=True,
                    can_expand=False,
                )
            ],
        )

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Fetch the latest session and resolve its audio at playback time."""
        if item.identifier != DAILY_MEDIA_ID:
            raise Unresolvable("Unknown Calm media")
        async with self._lock:
            entries = self.hass.config_entries.async_loaded_entries(DOMAIN)
            if not entries:
                raise Unresolvable("Set up Calm before playing Daily Calm")
            entry: CalmConfigEntry = entries[0]
            client = entry.runtime_data
            try:
                feed = await client.get_category_feed("home")
                daily = next(
                    (
                        guide
                        for pack in feed.packs
                        if pack.pack_class == "todays-daily-calm"
                        for guide in pack.items
                        if guide.guide_id
                    ),
                    None,
                )
                if daily is None:
                    raise Unresolvable("Today's Daily Calm is not available")
                if not is_available(daily):
                    raise Unresolvable("Daily Calm is locked for this account")
                guide, program = await client.get_guide(daily.guide_id)
                if not is_available(guide, program):
                    raise Unresolvable("Daily Calm is locked for this account")
                asset = guide.audio_asset
                if asset is None:
                    raise Unresolvable("Daily Calm has no playable audio")
                return PlayMedia(asset.url, asset.content_type)
            except CalmAuthError:
                entry.async_start_reauth(self.hass)
                raise Unresolvable("Sign in to Calm again") from None
            except CalmAPIError, HTTPError, TimeoutError:
                raise Unresolvable("Unable to connect to Calm") from None
            finally:
                async_store_credentials(self.hass, entry)
