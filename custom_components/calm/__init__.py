"""Set up Calm."""

from collections.abc import Mapping

from calm_client import CalmClient, Credentials
from calm_client.exceptions import CalmAPIError, CalmAuthError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.httpx_client import get_async_client
from httpx import HTTPError

from .const import CONF_CREDENTIALS

type CalmConfigEntry = ConfigEntry[CalmClient]


@callback
def async_store_credentials(
    hass: HomeAssistant, entry: CalmConfigEntry, previous_data: Mapping[str, object]
) -> None:
    """Persist rotated tokens only while the entry still uses the original sign-in."""
    if entry.data is not previous_data:
        return
    credentials = entry.runtime_data.credentials.model_dump(mode="json")
    if credentials != entry.data[CONF_CREDENTIALS]:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_CREDENTIALS: credentials}
        )


async def async_setup_entry(hass: HomeAssistant, entry: CalmConfigEntry) -> bool:
    """Validate the saved Calm session."""
    previous_data = entry.data
    client = CalmClient(
        Credentials.model_validate(previous_data[CONF_CREDENTIALS]),
        client=get_async_client(hass),
    )
    entry.runtime_data = client
    try:
        await client.get_favorites()
    except CalmAuthError:
        raise ConfigEntryAuthFailed("Calm sign-in has expired") from None
    except CalmAPIError, HTTPError, TimeoutError:
        raise ConfigEntryNotReady("Unable to connect to Calm") from None
    finally:
        async_store_credentials(hass, entry, previous_data)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CalmConfigEntry) -> bool:
    """Unload Calm; Home Assistant owns the shared HTTP client."""
    return True
