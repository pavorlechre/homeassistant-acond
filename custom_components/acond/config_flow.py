"""Config flow a Options flow pro integraci Acond Heat Pump."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_HOST, CONF_HP_SERIES


class AcondConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Průvodce instalací integrace Acond – IP adresa a série TČ."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Krok 1 – IP adresa a série TČ."""
        errors = {}

        if user_input is not None:
            host = user_input.get(CONF_HOST, "").strip()

            if not host:
                errors[CONF_HOST] = "invalid_host"
            else:
                return self.async_create_entry(
                    title=f"Acond ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_HP_SERIES: user_input.get(CONF_HP_SERIES, "Grandis / Economis"),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_HP_SERIES, default="Grandis / Economis"): vol.In(
                    ["Grandis / Economis", "PRO"]
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "series_hint": "Grandis / Economis (registr 30020 = otáčky rpm)\nPRO = PRO série (registr 30020 = výkon W)"
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Vrátí Options Flow pro úpravu IP adresy po instalaci."""
        return AcondOptionsFlow()


class AcondOptionsFlow(config_entries.OptionsFlow):
    """Options Flow – umožňuje uživateli změnit IP adresu TČ bez reinstalace.

    Při změně se config_entry.data aktualizuje a integrace se automaticky
    reloadne (unload + setup). Modbus klient se připojí na novou IP.

    Série TČ (Grandis vs PRO) NENÍ editovatelná – změna by způsobila změnu
    názvů a jednotek mnoha entit (otáčky vs výkon), což by porušilo
    automatizace a dashboardy. Pro změnu série je nutná reinstalace integrace.

    Pozn.: V HA 2024.12+ se config_entry NEpřiřazuje v __init__ – HA ho
    dodává automaticky jako property. Vlastní __init__ by způsobil
    AttributeError při otevření Options Flow.
    """

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Krok 1 – editace IP adresy."""
        errors = {}

        if user_input is not None:
            new_host = user_input.get(CONF_HOST, "").strip()

            if not new_host:
                errors[CONF_HOST] = "invalid_host"
            else:
                # Aktualizuj uložené data v config entry
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_HOST: new_host},
                    title=f"Acond ({new_host})",
                )
                # Spusť reload – integrace se odpoj a znovu nastartuje s novou IP
                await self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(title="", data={})

        # Předvyplň formulář aktuální IP
        current_host = self.config_entry.data.get(CONF_HOST, "")

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current_host): str,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
