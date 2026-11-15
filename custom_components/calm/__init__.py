"""Set up Calm."""

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
def async_store_credentials(hass: HomeAssistant, entry: CalmConfigEntry) -> None:
    """Persist rotated tokens without retaining the account password."""
    credentials = entry.runtime_data.credentials.model_dump(mode="json")
    if credentials != entry.data[CONF_CREDENTIALS]:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_CREDENTIALS: credentials}
        )


async def async_setup_entry(hass: HomeAssistant, entry: CalmConfigEntry) -> bool:
    """Validate the saved Calm session."""
    client = CalmClient(
        Credentials.model_validate(entry.data[CONF_CREDENTIALS]),
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
        async_store_credentials(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CalmConfigEntry) -> bool:
    """Unload Calm; Home Assistant owns the shared HTTP client."""
    async_store_credentials(hass, entry)
    return True
