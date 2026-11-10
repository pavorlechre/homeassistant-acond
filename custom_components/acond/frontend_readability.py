"""Load an Acond-only text-wrapping module; it never reads or writes entities."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
_DATA_KEY = "acond_readability"
_URL = "/acond-localization/readability.js"


async def async_register_readability(hass: HomeAssistant) -> None:
    """Register bundled CSS support once, only for a Polish system language."""
    if (
        (hass.config.language or "").split("-")[0].split("_")[0] != "pl"
        or _DATA_KEY in hass.data
        or frontend.DATA_EXTRA_MODULE_URL not in hass.data
        or not getattr(hass, "http", None)
    ):
        return
    path = Path(__file__).parent / "frontend" / "readability.js"
    try:
        digest = await hass.async_add_executor_job(_digest, path)
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_URL, str(path), cache_headers=False)]
        )
        url = f"{_URL}?v={digest}"
        frontend.add_extra_js_url(hass, url)
        hass.data[_DATA_KEY] = url
    except Exception:
        # A presentation failure must not prevent the original integration setup.
        _LOGGER.warning("Acond: could not load dashboard text wrapping", exc_info=True)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
