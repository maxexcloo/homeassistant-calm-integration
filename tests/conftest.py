"""Shared Home Assistant test fixtures."""

from unittest.mock import AsyncMock, patch

import jwt
import pytest
from calm_client import Credentials
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.calm.const import CONF_CREDENTIALS, DOMAIN


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load this custom integration."""


@pytest.fixture
def credentials():
    """Return synthetic Calm credentials."""
    return Credentials(
        token="test-access",
        refresh_token="test-refresh",
        id_token=jwt.encode({"sub": "calm-account"}, key=None, algorithm="none"),
    )


@pytest.fixture
def mock_client(credentials):
    """Mock network calls while using the library's real models."""
    client = AsyncMock()
    client.credentials = credentials
    client.login.return_value = credentials
    client.get_favorites.return_value = []
    with (
        patch("custom_components.calm.CalmClient", return_value=client),
        patch("custom_components.calm.config_flow.CalmClient", return_value=client),
    ):
        yield client


@pytest.fixture
def config_entry(hass, credentials):
    """Add a Calm account to Home Assistant."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Calm",
        unique_id="calm-account",
        data={CONF_CREDENTIALS: credentials.model_dump(mode="json")},
    )
    entry.add_to_hass(hass)
    return entry
