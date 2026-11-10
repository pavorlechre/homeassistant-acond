"""Offline tests: use a temporary HA object and prohibit network connections."""

import json
import socket
from pathlib import Path

import pytest
import pytest_asyncio
from homeassistant import loader
from homeassistant.core import HomeAssistant

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "acond"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network access is prohibited in localization tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest_asyncio.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    instance.config.language = "pl"
    loader.async_setup(instance)
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    instance.data[loader.DATA_INTEGRATIONS]["acond"] = loader.Integration(
        instance,
        "custom_components.acond",
        COMPONENT,
        manifest,
        {path.name for path in COMPONENT.iterdir()},
    )
    yield instance
    await instance.async_stop(force=True)
