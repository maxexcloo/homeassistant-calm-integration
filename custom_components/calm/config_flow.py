"""Configure a Calm account."""

import jwt
import voluptuous as vol
from calm_client import CalmClient
from calm_client.exceptions import CalmAPIError, CalmAuthError
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.httpx_client import get_async_client
from httpx import HTTPError

from .const import CONF_CREDENTIALS, DOMAIN

SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})


class CalmConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle sign-in and reauthentication."""

    VERSION = 1

    async def _async_login(self, user_input):
        """Validate credentials using the same path for setup and reauthentication."""
        client = CalmClient(client=get_async_client(self.hass))
        credentials = await client.login(
            user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
        )
        await client.get_favorites()
        # The ID token comes directly from Calm over TLS, not from user input.
        subject = jwt.decode(credentials.id_token, options={"verify_signature": False})[
            "sub"
        ]
        await self.async_set_unique_id(subject)
        return {CONF_CREDENTIALS: client.credentials.model_dump(mode="json")}

    async def async_step_user(self, user_input=None):
        """Sign in to Calm."""
        return await self._async_step_login("user", user_input)

    async def async_step_reauth(self, entry_data):
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Replace expired credentials for the same account."""
        return await self._async_step_login("reauth_confirm", user_input)

    async def _async_step_login(self, step_id, user_input):
        """Show a sign-in form or save a validated session."""
        errors = {}
        if user_input is not None:
            try:
                data = await self._async_login(user_input)
            except CalmAuthError:
                errors["base"] = "invalid_auth"
            except CalmAPIError, HTTPError, TimeoutError:
                errors["base"] = "cannot_connect"
            except jwt.InvalidTokenError, KeyError, TypeError:
                errors["base"] = "invalid_auth"
            else:
                if step_id == "reauth_confirm":
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data=data
                    )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Calm", data=data)

        return self.async_show_form(step_id=step_id, data_schema=SCHEMA, errors=errors)
