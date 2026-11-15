"""Test saved sessions and setup recovery."""

import pytest
from calm_client.exceptions import CalmAPIError, CalmAuthError
from homeassistant.config_entries import ConfigEntryState

from custom_components.calm.const import CONF_CREDENTIALS


async def test_setup_unload(hass, mock_client, config_entry):
    """Persist refreshed tokens and leave the shared HTTP client open."""
    mock_client.credentials.refresh_token = "rotated-refresh"
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.runtime_data is mock_client
    assert config_entry.data[CONF_CREDENTIALS]["refresh_token"] == "rotated-refresh"
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    mock_client.close.assert_not_called()


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
