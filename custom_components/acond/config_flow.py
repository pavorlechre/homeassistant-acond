"""Config flow a Options flow pro integraci Acond Heat Pump."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_HP_SERIES,
    CONF_TUV_MAX,
    CONF_COMP_MIN,
    CONF_COMP_MAX,
    TUV_MAX_BOUNDS,
    TUV_MAX_DEFAULT,
    COMP_CAPACITY_BOUNDS,
)


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
        """Vrátí Options Flow pro úpravu nastavení po instalaci."""
        return AcondOptionsFlow()


class AcondOptionsFlow(config_entries.OptionsFlow):
    """Options Flow – uživatelské přizpůsobení po instalaci.

    Editovatelné položky:
      1) IP adresa TČ
      2) Max. teplota TUV (50–60 °C, default 50)
         Default 50 odpovídá tomu, co Acond přijme bez servisního zásahu
         (i když protokol uvádí 46). Hodnoty 51–60 vyžadují servisní odemčení.
      3) Min/Max slideru kompresoru (40014) – rozsah dle série TČ:
         - Grandis / Economis: 1000–6000 rpm (default 1800–6000)
         - PRO:                2000–20000 W  (default 2000–20000)

    Série TČ (Grandis vs PRO) NENÍ editovatelná – změna by způsobila změnu
    názvů a jednotek mnoha entit (otáčky vs výkon), což by porušilo
    automatizace a dashboardy. Pro změnu série je nutná reinstalace integrace.

    Při uložení se options uloží do config_entry.options a integrace se
    automaticky reloadne přes update_listener v __init__.py. Entity dostanou
    nové meze slideru / max_value bez restartu HA.

    Pozn.: V HA 2024.12+ se config_entry NEpřiřazuje v __init__ – HA ho
    dodává automaticky jako property. Vlastní __init__ by způsobil
    AttributeError při otevření Options Flow.
    """

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Krok 1 – editace všech uživatelských nastavení."""
        errors = {}

        # Série TČ z config entry – určuje rozsah a label kompresoru
        hp_series = self.config_entry.data.get(CONF_HP_SERIES, "Grandis / Economis")
        abs_min, abs_max, default_min, default_max, unit, step = COMP_CAPACITY_BOUNDS[hp_series]

        if user_input is not None:
            # Validace – min < max kompresoru. NumberSelector vrací float;
            # převedeme na int (registry očekávají celá čísla).
            new_host = user_input.get(CONF_HOST, "").strip()
            comp_min = int(user_input.get(CONF_COMP_MIN, default_min))
            comp_max = int(user_input.get(CONF_COMP_MAX, default_max))
            tuv_max = int(user_input.get(CONF_TUV_MAX, TUV_MAX_DEFAULT))

            if not new_host:
                errors[CONF_HOST] = "invalid_host"
            elif comp_min >= comp_max:
                # comp min musí být striktně menší než comp max
                errors[CONF_COMP_MIN] = "comp_min_ge_max"
                errors[CONF_COMP_MAX] = "comp_min_ge_max"

            if not errors:
                # IP se ukládá do data (legacy chování – zachováno z předchozí verze),
                # ostatní user-tunable hodnoty do options.
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_HOST: new_host},
                    title=f"Acond ({new_host})",
                )
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_TUV_MAX: tuv_max,
                        CONF_COMP_MIN: comp_min,
                        CONF_COMP_MAX: comp_max,
                    },
                )

        # Předvyplň aktuálními hodnotami (data + options)
        current_host = self.config_entry.data.get(CONF_HOST, "")
        current_tuv_max = self.config_entry.options.get(CONF_TUV_MAX, TUV_MAX_DEFAULT)
        current_comp_min = self.config_entry.options.get(CONF_COMP_MIN, default_min)
        current_comp_max = self.config_entry.options.get(CONF_COMP_MAX, default_max)

        # Label kompresoru dle série – ať uživatel vidí jednotku
        comp_label_min = f"Min. otáček kompresoru ({unit})" if unit == "rpm" else f"Min. výkonu kompresoru ({unit})"
        comp_label_max = f"Max. otáček kompresoru ({unit})" if unit == "rpm" else f"Max. výkonu kompresoru ({unit})"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current_host): str,
                # NumberSelector zobrazí slider s aktuální hodnotou + min/max popisky
                # (čistě vol.Range by HA vykreslil jako prázdný slider bez čísel).
                vol.Required(
                    CONF_TUV_MAX, default=current_tuv_max
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=TUV_MAX_BOUNDS[0],
                        max=TUV_MAX_BOUNDS[1],
                        step=1,
                        unit_of_measurement="°C",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_COMP_MIN, default=current_comp_min
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=abs_min,
                        max=abs_max,
                        step=step,
                        unit_of_measurement=unit,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_COMP_MAX, default=current_comp_max
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=abs_min,
                        max=abs_max,
                        step=step,
                        unit_of_measurement=unit,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "hp_series": hp_series,
                "comp_min_label": comp_label_min,
                "comp_max_label": comp_label_max,
                "comp_abs_range": f"{abs_min}–{abs_max} {unit}",
                "tuv_range": f"{TUV_MAX_BOUNDS[0]}–{TUV_MAX_BOUNDS[1]} °C",
            },
        )
