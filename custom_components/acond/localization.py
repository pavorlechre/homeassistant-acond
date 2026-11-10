"""Presentation-only localization; legacy states and Modbus values stay unchanged."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN, REG_TYPES

_LOGGER = logging.getLogger(__name__)
_DATA_KEY = "acond_localization"
_DISPLAY_FIELDS = frozenset({"title", "name", "heading", "content", "text", "label"})
_SERVICE_FIELDS = frozenset(
    {"data", "service_data", "target", "conditions", "visibility"}
)


async def async_load_localization(hass: HomeAssistant) -> None:
    """Load translations without blocking the event loop or touching the pump."""
    language = hass.config.language or "en"
    messages: dict[str, str] = {}
    dashboard: dict[str, str] = {}
    try:
        messages = await async_get_translations(hass, language, "common", {DOMAIN})
    except Exception:  # Localization must never prevent the integration from loading.
        _LOGGER.warning(
            "Acond: could not load presentation translations", exc_info=True
        )

    # Only bundled language files may be opened. Unsupported languages use the
    # original dashboard; never interpolate a user-controlled language into a path.
    languages = {"pl": "pl.json"}
    filename = languages.get(language.lower().replace("_", "-").split("-")[0])
    if filename:
        path = Path(__file__).parent / "lovelace" / "translations" / filename
        try:
            dashboard = await hass.async_add_executor_job(_read_dashboard_catalog, path)
        except (OSError, ValueError, TypeError):
            _LOGGER.warning(
                "Acond: could not load dashboard translations", exc_info=True
            )
    hass.data[_DATA_KEY] = {"messages": messages, "dashboard": dashboard}


def _read_dashboard_catalog(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        raise ValueError("Dashboard translations must be a string-to-string mapping")
    return data


def text(hass: HomeAssistant, key: str, fallback: str, **values: Any) -> str:
    """Read a standard HA translation with a safe fallback for older installs."""
    messages = hass.data.get(_DATA_KEY, {}).get("messages", {})
    template = messages.get(f"component.{DOMAIN}.common.{key}", fallback)
    try:
        return template.format(**values)
    except (KeyError, ValueError, IndexError):
        return fallback.format(**values)


def localized_state(hass: HomeAssistant, key: str, value: int, fallback: str) -> str:
    """Return a display label; never replace the entity's native state."""
    messages = hass.data.get(_DATA_KEY, {}).get("messages", {})
    translation_key = f"state_{key}_{value}"
    if f"component.{DOMAIN}.common.{translation_key}" in messages:
        return text(hass, translation_key, fallback)
    return text(hass, f"unknown_{key}", fallback, code=value)


def localize_dashboard(hass: HomeAssistant, config: dict) -> dict:
    """Translate presentation fields in a copy, preserving all actions and IDs.

    Call before adding MaR contributions: their content belongs to that project.
    Missing entries fall back to the upstream text after future updates.
    """
    catalog = hass.data.get(_DATA_KEY, {}).get("dashboard", {})
    if not catalog:
        return config

    text_sensors = {
        "sensor.acond_30014_hp_mode",
        "sensor.acond_30015_regulation_type",
        "sensor.acond_30021_err_number",
        "sensor.acond_30023_err_number_driver",
        "sensor.acond_30044_thermal_power",
        "sensor.acond_30032_silent_mode",
        "sensor.acond_30033_silent_mode_start",
        "sensor.acond_30034_silent_mode_stop",
    }
    regulation_entity = "select.acond_40007_sel_regulation_type"
    regulation_icons = {0: "mdi:home-thermometer", 1: "mdi:chart-line"}

    def translate(value: Any) -> Any:
        if isinstance(value, list):
            result = []
            for item in value:
                # The native selector's legacy options are a public API. Use
                # built-in button rows for translated labels with the same
                # select.select_option calls, leaving that API intact.
                if (
                    isinstance(item, dict)
                    and item.get("entity") == regulation_entity
                    and "type" not in item
                ):
                    result.append(
                        {
                            "type": "attribute",
                            "entity": regulation_entity,
                            "attribute": "localized_state",
                            "name": catalog.get(item.get("name"), item.get("name", "")),
                        }
                    )
                    buttons = [
                        {
                            "entity": regulation_entity,
                            "name": localized_state(
                                hass, "regulation_type", code, option
                            ),
                            "icon": regulation_icons.get(code, "mdi:tune"),
                            "tap_action": {
                                "action": "perform-action",
                                "perform_action": "select.select_option",
                                "target": {"entity_id": regulation_entity},
                                "data": {"option": option},
                            },
                        }
                        for code, option in REG_TYPES.items()
                    ]
                    # Keep each translated label visible on narrow mobile cards.
                    result.extend(
                        {"type": "buttons", "entities": buttons[start : start + 2]}
                        for start in range(0, len(buttons), 2)
                    )
                else:
                    result.append(translate(item))
            return result
        if not isinstance(value, dict):
            return value
        result = {
            key: catalog.get(item, item)
            if key in _DISPLAY_FIELDS and isinstance(item, str)
            else item
            if key in _SERVICE_FIELDS
            else translate(item)
            for key, item in value.items()
        }
        entity_id = result.get("entity")
        if result.get("type") == "glance" and any(
            isinstance(item, dict) and item.get("entity") in text_sensors
            for item in result.get("entities", [])
        ):
            # Glance ignores attribute rows and would show legacy Czech states.
            # An ordinary entities card supports the localized_state attribute.
            result["type"] = "entities"
            result.pop("columns", None)
        if result.get("type") in {"tile", "button", "heading", "entity"}:
            # Auto-sized rows let longer Polish names grow with their controls.
            result["grid_options"] = {**result.get("grid_options", {}), "rows": "auto"}
        if isinstance(entity_id, str) and entity_id in text_sensors:
            if "type" not in result:
                result.update(type="attribute", attribute="localized_state")
            elif result.get("type") == "entity":
                result["attribute"] = "localized_state"
        return result

    return translate(deepcopy(config))
