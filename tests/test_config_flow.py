"""Test account setup and reauthentication."""

from unittest.mock import AsyncMock, patch

import jwt
import pytest
from calm_client.exceptions import CalmAPIError, CalmAuthError
from homeassistant.components.media_source import Unresolvable, async_resolve_media
from homeassistant.data_entry_flow import FlowResultType

from custom_components.calm.const import CONF_CREDENTIALS, DOMAIN

USER_INPUT = {"email": "listener@example.com", "password": "test-password"}


async def test_user(hass, mock_client):
    """Save the validated session instead of the password."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "calm-account"
    assert result["data"] == {
        CONF_CREDENTIALS: mock_client.credentials.model_dump(mode="json")
    }
    assert "password" not in result["data"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [(CalmAuthError(), "invalid_auth"), (CalmAPIError(), "cannot_connect")],
)
async def test_login_errors(hass, mock_client, error, expected):
    """Leave sign-in retryable when authentication or the API fails."""
    mock_client.login.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data=USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_single_account(hass, mock_client, config_entry):
    """Prevent a second account from making the daily media identifier ambiguous."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.parametrize("same_account", [True, False])
@pytest.mark.parametrize("loaded", [True, False])
async def test_reauth(hass, mock_client, config_entry, same_account, loaded):
    """Replace expired tokens only when the account identity is unchanged."""
    mock_client.credentials.token = "replacement-access"
    if not same_account:
        mock_client.credentials.id_token = jwt.encode(
            {"sub": "different-account"}, key=None, algorithm="none"
        )
    with patch(
        "custom_components.calm.CalmClient",
        side_effect=lambda credentials, **_: AsyncMock(credentials=credentials),
    ):
        if loaded:
            assert await hass.config_entries.async_setup(config_entry.entry_id)
        result = await config_entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == (
        "reauth_successful" if same_account else "unique_id_mismatch"
    )
    assert config_entry.data[CONF_CREDENTIALS]["token"] == (
        "replacement-access" if same_account else "test-access"
    )


async def test_reauth_during_playback(hass, mock_client, config_entry):
    """Keep the new sign-in when a playback request finishes during reload."""

    async def reauth_before_feed_returns(_category):
        result = await config_entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        assert result["reason"] == "reauth_successful"
        raise CalmAPIError()

    mock_client.get_category_feed.side_effect = reauth_before_feed_returns
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    replacement = mock_client.credentials.model_copy(
        update={"token": "replacement-access"}
    )
    login_client = AsyncMock(credentials=replacement)
    login_client.login.return_value = replacement
    with (
        patch(
            "custom_components.calm.config_flow.CalmClient", return_value=login_client
        ),
        patch(
            "custom_components.calm.CalmClient",
            side_effect=lambda credentials, **_: AsyncMock(credentials=credentials),
        ),
    ):
        async with config_entry.setup_lock:
            with pytest.raises(Unresolvable, match="Unable to connect"):
                await async_resolve_media(
                    hass, "media-source://calm/daily", target_media_player=None
                )
        await hass.async_block_till_done()
    assert config_entry.data[CONF_CREDENTIALS]["token"] == "replacement-access"
