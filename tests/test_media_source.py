"""Test current-day resolution and account access controls."""

from types import SimpleNamespace

import pytest
from calm_client.exceptions import CalmAuthError
from calm_client.models import FeedResponse, Guide, Program
from homeassistant.components.media_source import Unresolvable, async_resolve_media

from custom_components.calm.const import CONF_CREDENTIALS
from custom_components.calm.media_source import async_get_media_source


def daily_feed(guide_id="today", unlocked=True):
    """Model the current home feed, including an older Daily Calm row."""
    return FeedResponse.model_validate(
        {
            "packs": [
                {
                    "pack_class": "past-week-of-daily-calms",
                    "items": [{"guide_id": "yesterday", "type": "guide"}],
                },
                {
                    "pack_class": "todays-daily-calm",
                    "items": [
                        {
                            "guide_id": guide_id,
                            "is_unlocked": unlocked,
                            "type": "guide",
                        }
                    ],
                },
            ]
        }
    )


@pytest.fixture
async def source(hass, mock_client, config_entry):
    """Load Calm with a playable daily session."""
    mock_client.get_category_feed.return_value = daily_feed()
    mock_client.get_guide.return_value = (
        Guide.model_validate(
            {
                "id": "today",
                "title": "Mountains",
                "is_unlocked": True,
                "assets": [
                    {
                        "url": "https://example.com/daily.m4a",
                        "content_type": "audio/mp4",
                    }
                ],
            }
        ),
        Program(id="daily-program", title="Daily Calm", is_unlocked=True),
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    return await async_get_media_source(hass)


async def test_browse(source):
    """Expose a reusable daily selection through the native media picker."""
    root = await source.async_browse_media(SimpleNamespace(identifier=""))
    assert root.children[0].media_content_id == "media-source://calm/daily"
    assert root.children[0].can_play


async def test_current_daily(source, hass, mock_client, config_entry):
    """Resolve fresh guide IDs rather than retaining yesterday's selection."""
    item = SimpleNamespace(identifier="daily")
    result = await async_resolve_media(
        hass, "media-source://calm/daily", target_media_player="media_player.speaker"
    )
    assert result.url == "https://example.com/daily.m4a"
    assert result.mime_type == "audio/mp4"
    mock_client.get_guide.assert_awaited_with("today")

    mock_client.get_category_feed.return_value = daily_feed("tomorrow")
    mock_client.credentials.refresh_token = "rotated-during-playback"
    await source.async_resolve_media(item)
    mock_client.get_guide.assert_awaited_with("tomorrow")
    assert config_entry.data[CONF_CREDENTIALS]["refresh_token"] == (
        "rotated-during-playback"
    )


async def test_missing_daily(source, mock_client):
    """Refuse playback when today's row is missing, even if older guides exist."""
    feed = daily_feed()
    feed.packs.pop()
    mock_client.get_category_feed.return_value = feed
    with pytest.raises(Unresolvable, match="not available"):
        await source.async_resolve_media(SimpleNamespace(identifier="daily"))
    mock_client.get_guide.assert_not_awaited()


@pytest.mark.parametrize("locked_at", ["feed", "guide"])
async def test_locked_daily(source, mock_client, locked_at):
    """Check entitlement both before and after resolving the selected guide."""
    if locked_at == "feed":
        mock_client.get_category_feed.return_value = daily_feed(unlocked=False)
    else:
        guide, program = mock_client.get_guide.return_value
        guide.is_unlocked = False
        program.is_unlocked = False
    with pytest.raises(Unresolvable, match="locked"):
        await source.async_resolve_media(SimpleNamespace(identifier="daily"))


async def test_no_audio(source, mock_client):
    """Do not hand a non-audio asset to the speaker."""
    guide, _ = mock_client.get_guide.return_value
    guide.assets = []
    with pytest.raises(Unresolvable, match="no playable audio"):
        await source.async_resolve_media(SimpleNamespace(identifier="daily"))


async def test_expired_session(source, hass, mock_client):
    """Open reauthentication when a session expires during playback."""
    mock_client.get_category_feed.side_effect = CalmAuthError()
    with pytest.raises(Unresolvable, match="Sign in"):
        await source.async_resolve_media(SimpleNamespace(identifier="daily"))
    await hass.async_block_till_done()
    assert hass.config_entries.flow.async_progress_by_handler("calm")
