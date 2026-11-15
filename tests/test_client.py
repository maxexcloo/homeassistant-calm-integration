"""Exercise authentication recovery through the real Calm client."""

from unittest.mock import patch

import httpx
import pytest
from homeassistant.components.media_source import Unresolvable, async_resolve_media
from homeassistant.config_entries import ConfigEntryState

from custom_components.calm.const import CONF_CREDENTIALS, DOMAIN


@pytest.fixture
async def real_http():
    """Supply a controlled transport without replacing Calm's client."""
    async with httpx.AsyncClient() as client:
        with (
            patch("custom_components.calm.get_async_client", return_value=client),
            patch(
                "custom_components.calm.config_flow.get_async_client",
                return_value=client,
            ),
        ):
            yield client


def fail_token_request(respx_mock, failure):
    """Model an unavailable authentication service."""
    route = respx_mock.post("https://oneid.calm.com/oauth/token")
    if failure == "timeout":
        route.mock(side_effect=httpx.ReadTimeout("Synthetic outage"))
    else:
        route.respond(failure, json={"error": "temporarily_unavailable"})


@pytest.mark.parametrize("failure", [429, 503, "timeout"])
async def test_login_outage(hass, real_http, respx_mock, failure):
    """Keep valid users on the retryable connection-error form."""
    fail_token_request(respx_mock, failure)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={"email": "listener@example.com", "password": "synthetic-password"},
    )
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.parametrize("failure", [429, 503, "timeout"])
async def test_setup_refresh_outage(hass, real_http, respx_mock, config_entry, failure):
    """Retry entry setup without requiring a new sign-in after an outage."""
    saved = {**config_entry.data[CONF_CREDENTIALS], "expires_at": 0}
    hass.config_entries.async_update_entry(config_entry, data={CONF_CREDENTIALS: saved})
    fail_token_request(respx_mock, failure)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert config_entry.data[CONF_CREDENTIALS]["refresh_token"] == "test-refresh"


@pytest.mark.parametrize("failure", [429, 503, "timeout"])
async def test_playback_refresh_outage(
    hass, real_http, respx_mock, config_entry, failure
):
    """Report a playback connection failure without starting reauthentication."""
    respx_mock.get(
        "https://www.calm.com/webapi/authproxy/packs/class/faves-hydrated"
    ).respond(200, json={})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    config_entry.runtime_data.credentials.expires_at = 0
    fail_token_request(respx_mock, failure)
    with pytest.raises(Unresolvable, match="Unable to connect"):
        await async_resolve_media(
            hass,
            "media-source://calm/daily",
            target_media_player="media_player.speaker",
        )
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def test_refresh_persists_tokens(hass, real_http, respx_mock, config_entry):
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
    assert not real_http.is_closed
