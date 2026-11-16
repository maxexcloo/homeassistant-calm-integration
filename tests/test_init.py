"""Test saved sessions and setup recovery."""

from unittest.mock import patch

import httpx
import pytest
from calm_client.exceptions import CalmAPIError, CalmAuthError
from homeassistant.config_entries import ConfigEntryState

from custom_components.calm.const import CONF_CREDENTIALS


async def test_setup_unload(hass, respx_mock, config_entry):
    """Persist actual token rotation while keeping the session and device ID."""
    saved = {
        **config_entry.data[CONF_CREDENTIALS],
        "expires_at": 0,
        "session_token": "synthetic-session",
    }
    hass.config_entries.async_update_entry(config_entry, data={CONF_CREDENTIALS: saved})
    respx_mock.post("https://oneid.calm.com/oauth/token").respond(
        200,
        json={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        },
    )
    favorites = respx_mock.get(
        "https://www.calm.com/webapi/authproxy/packs/class/faves-hydrated"
    ).respond(200, json={})
    async with httpx.AsyncClient() as client:
        with patch("custom_components.calm.get_async_client", return_value=client):
            assert await hass.config_entries.async_setup(config_entry.entry_id)
            stored = config_entry.data[CONF_CREDENTIALS]
            assert stored["token"] == "new-access"
            assert stored["refresh_token"] == "new-refresh"
            assert stored["session_token"] == "synthetic-session"
            assert stored["device_id"] == saved["device_id"]
            assert favorites.calls.last.request.headers["Cookie"] == (
                "calm-user-token=synthetic-session"
            )
            assert await hass.config_entries.async_unload(config_entry.entry_id)
            assert not client.is_closed


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (CalmAuthError(), ConfigEntryState.SETUP_ERROR),
        (CalmAPIError(), ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_setup_errors(hass, mock_client, config_entry, error, expected):
    """Request reauthentication for expired sessions and retry API outages."""
    mock_client.get_favorites.side_effect = error
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is expected
    if isinstance(error, CalmAuthError):
        assert hass.config_entries.flow.async_progress_by_handler("calm")
