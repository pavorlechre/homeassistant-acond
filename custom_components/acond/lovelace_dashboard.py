"""Automatická registrace Acond Lovelace dashboardu.

Dashboard se zobrazí jako postranní panel HA po instalaci integrace.
Odpojení integrace panel opět odstraní.

Implementace používá `LovelaceYAML` z interního Lovelace API – pokud by se
v budoucí verzi HA změnilo, registrace selže a uživatel dostane do logu
instrukce pro ruční přidání (integrace samotná funguje dál normálně).
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "acond-dashboard"
DASHBOARD_TITLE = "Acond TČ"
DASHBOARD_ICON = "mdi:heat-pump"
DASHBOARD_YAML_FILENAME = "acond_dashboard.yaml"

# Jak by si měl uživatel dashboard přidat ručně, kdyby automatická
# registrace selhala
_MANUAL_INSTRUCTIONS = (
    "Dashboard můžete přidat ručně: Nastavení → Dashboardy → "
    "Přidat (+) → 'Z YAML souboru', cesta: "
    "custom_components/acond/lovelace/acond_dashboard.yaml"
)


async def async_register_dashboard(hass: HomeAssistant) -> None:
    """Registruj Acond dashboard jako postranní panel."""
    dashboard_path = Path(__file__).parent / "lovelace" / DASHBOARD_YAML_FILENAME

    if not dashboard_path.is_file():
        _LOGGER.warning(
            "Acond: dashboard YAML nenalezen na %s – dashboard nebude registrován",
            dashboard_path,
        )
        return

    # 1) Přidej dashboard do Lovelace storage (pokud tam ještě není).
    #    Import je uvnitř funkce – v případě změny interního API jen selže
    #    registrace, integrace samotná poběží dál.
    try:
        from homeassistant.components.lovelace.dashboard import LovelaceYAML
    except ImportError as err:
        _LOGGER.warning(
            "Acond: nepodporovaná verze Lovelace API (%s). %s",
            err,
            _MANUAL_INSTRUCTIONS,
        )
        return

    lovelace_data = hass.data.get("lovelace")
    if lovelace_data is None:
        _LOGGER.warning(
            "Acond: Lovelace není inicializován. %s", _MANUAL_INSTRUCTIONS
        )
        return

    # `lovelace_data.dashboards` je dict url_path → LovelaceConfig v novějších HA,
    # ve starších verzích atribut `dashboards` na objektu LovelaceData.
    dashboards = getattr(lovelace_data, "dashboards", None)
    if dashboards is None and isinstance(lovelace_data, dict):
        dashboards = lovelace_data.get("dashboards")

    if dashboards is None:
        _LOGGER.warning(
            "Acond: nelze najít Lovelace dashboards kolekci. %s",
            _MANUAL_INSTRUCTIONS,
        )
        return

    if DASHBOARD_URL_PATH in dashboards:
        _LOGGER.debug("Acond: dashboard %s už je registrován", DASHBOARD_URL_PATH)
        return

    dashboard_config = {
        "mode": "yaml",
        "filename": str(dashboard_path),
        "title": DASHBOARD_TITLE,
        "icon": DASHBOARD_ICON,
        "show_in_sidebar": True,
        "require_admin": False,
    }

    try:
        dashboards[DASHBOARD_URL_PATH] = LovelaceYAML(
            hass, DASHBOARD_URL_PATH, dashboard_config
        )
    except Exception as err:  # širší catch – API se může měnit
        _LOGGER.warning(
            "Acond: nelze vytvořit Lovelace dashboard (%s). %s",
            err,
            _MANUAL_INSTRUCTIONS,
        )
        return

    # 2) Zaregistruj postranní panel – bez toho by dashboard v HA menu nebyl.
    try:
        frontend.async_register_built_in_panel(
            hass,
            component_name="lovelace",
            sidebar_title=DASHBOARD_TITLE,
            sidebar_icon=DASHBOARD_ICON,
            frontend_url_path=DASHBOARD_URL_PATH,
            config={"mode": "yaml"},
            require_admin=False,
            update=False,
        )
        _LOGGER.info(
            "Acond: dashboard registrován jako postranní panel '%s' (URL /%s)",
            DASHBOARD_TITLE,
            DASHBOARD_URL_PATH,
        )
    except ValueError:
        # Panel se stejným URL už existuje – není třeba řešit
        _LOGGER.debug("Acond: panel %s už existuje", DASHBOARD_URL_PATH)
    except Exception as err:
        _LOGGER.error(
            "Acond: nelze zaregistrovat panel (%s). %s", err, _MANUAL_INSTRUCTIONS
        )


async def async_unregister_dashboard(hass: HomeAssistant) -> None:
    """Odstraň Acond dashboard z postranního panelu i z Lovelace."""
    # Odeber postranní panel
    try:
        frontend.async_remove_panel(hass, DASHBOARD_URL_PATH)
    except Exception as err:  # panel nemusí existovat – nevadí
        _LOGGER.debug("Acond: odebrání panelu selhalo: %s", err)

    # Odeber dashboard z Lovelace kolekce
    lovelace_data = hass.data.get("lovelace")
    if lovelace_data is None:
        return

    dashboards = getattr(lovelace_data, "dashboards", None)
    if dashboards is None and isinstance(lovelace_data, dict):
        dashboards = lovelace_data.get("dashboards")

    if dashboards is not None and DASHBOARD_URL_PATH in dashboards:
        dashboards.pop(DASHBOARD_URL_PATH, None)
        _LOGGER.info("Acond: dashboard %s odstraněn", DASHBOARD_URL_PATH)
