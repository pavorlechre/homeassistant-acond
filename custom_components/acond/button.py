from __future__ import annotations
import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_HP_SERIES,
    BUTTON_DEFINITIONS,
)
from .modbus_client import AcondModbusClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvoř button entity pro:

    1) jednorázové akce na TČ (Modbus zápis – BUTTON_DEFINITIONS)
    2) export AI kontextu pro diagnostiku s Claude / ChatGPT
    """
    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    hp_series = entry.data.get(CONF_HP_SERIES, "Grandis / Economis")
    host = entry.data[CONF_HOST]

    entities: list[ButtonEntity] = []

    # --- Modbus tlačítka (potvrzení poruchy, reset PLC, léto/zima) ---
    for button_def in BUTTON_DEFINITIONS:
        entities.append(
            AcondButton(
                client=client,
                button_def=button_def,
                entry_id=entry.entry_id,
                hp_series=hp_series,
                host=host,
            )
        )

    # --- AI kontext export tlačítka (jen 1× na celou integraci) ---
    # Při více config entries (multi-TČ) bychom dostali duplicitní entity_id;
    # příznak v hass.data zajistí, že tlačítka vytvoří jen první entry.
    if not hass.data[DOMAIN].get("_ai_context_buttons_added"):
        hass.data[DOMAIN]["_ai_context_buttons_added"] = True
        for mode in ("acond", "full"):
            entities.append(
                AcondAIContextButton(
                    hass=hass,
                    entry_id=entry.entry_id,
                    hp_series=hp_series,
                    host=host,
                    mode=mode,
                )
            )

    _LOGGER.info("Acond: přidávám %s button entit", len(entities))
    async_add_entities(entities)


class AcondButton(ButtonEntity):
    """Tlačítko pro jednorázovou akci přes Modbus holding registr.

    Při stisku zapíše hodnotu (obvykle 1) do registru.
    TČ si hodnotu samo vrátí na 0 po dokončení akce.

    Příklady:
    - Potvrzení poruchy (bit 5 registru 40006)
    - Reset PLC (registr 40021)
    - Přepnutí léto/zima (bit 8 registru 40006)
    """

    def __init__(self, client, button_def, entry_id: str, hp_series: str, host: str):
        self._button_def = button_def
        self._client: AcondModbusClient = client
        self._hp_series = hp_series
        self._host = host
        self._entry_id = entry_id

        self._attr_name = button_def.name
        self._attr_unique_id = f"acond_{button_def.address}_{button_def.key}"
        # Stabilní entity_id – dashboard YAML se na něj spoléhá
        self.entity_id = f"button.acond_{button_def.address}_{button_def.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Seskup entity pod jedno zařízení v HA."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Acond",
            manufacturer="Acond",
            model="PRO" if self._hp_series == "PRO" else "Grandis / Economis",
            configuration_url=f"http://{self._host}",
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Přidej registr jako atribut – usnadní ladění."""
        attrs = {"modbus_register": self._button_def.address}
        if self._button_def.bit is not None:
            attrs["bit"] = self._button_def.bit
        return attrs

    async def async_press(self) -> None:
        """Proveď akci – zapiš hodnotu do registru (celý nebo bit)."""
        if self._button_def.bit is None:
            # Celý registr – prostý zápis hodnoty (obvykle 1)
            success = await self._client.write_register(
                self._button_def.address, self._button_def.value
            )
        else:
            # Bit v registru – read-modify-write
            result = await self._client.read_holding_register(self._button_def.address)
            if result is None:
                _LOGGER.error(
                    "Acond: nelze přečíst registr %s před zápisem bitu %s",
                    self._button_def.address,
                    self._button_def.bit,
                )
                return
            new_value = result | (1 << self._button_def.bit)
            success = await self._client.write_register(self._button_def.address, new_value)

        if success:
            _LOGGER.debug(
                "Acond: button %s stisknut (registr %s, bit %s, hodnota %s)",
                self._button_def.key,
                self._button_def.address,
                self._button_def.bit,
                self._button_def.value,
            )
        else:
            _LOGGER.error(
                "Acond: stisk button %s selhal (registr %s, bit %s)",
                self._button_def.key,
                self._button_def.address,
                self._button_def.bit,
            )


class AcondAIContextButton(ButtonEntity):
    """Service tlačítko pro export AI kontextu integrace.

    Na rozdíl od `AcondButton` nezapisuje do Modbus, ale volá interní
    funkci `async_export()` z `ai_context.py`, která:

    1) sken HA (entity, automatizace, repairs, log buffery)
    2) redakce secrets
    3) filtr acond-only (jen v acond módu)
    4) zápis markdown souboru do /config/acond_ai_context/
    5) persistent notification s download linkem

    Při chybě posílá fallback notifikaci, aby uživatel věděl proč nic nedostal.
    """

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        hp_series: str,
        host: str,
        mode: str,
    ):
        self._hass = hass
        self._entry_id = entry_id
        self._hp_series = hp_series
        self._host = host
        self._mode = mode  # "acond" nebo "full"

        if mode == "acond":
            self._attr_name = "Export AI kontextu – jen acond"
            self._attr_icon = "mdi:robot-outline"
        elif mode == "full":
            self._attr_name = "Export AI kontextu – celé HA"
            self._attr_icon = "mdi:robot"
        else:
            raise ValueError(f"Neznámý AI context mode: {mode!r}")

        # Stabilní unique_id a entity_id (zarovnané s mode hodnotou)
        key = f"ai_context_{mode}"
        self._attr_unique_id = f"acond_{key}"
        self.entity_id = f"button.acond_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Seskup entity pod jedno zařízení v HA."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Acond",
            manufacturer="Acond",
            model="PRO" if self._hp_series == "PRO" else "Grandis / Economis",
            configuration_url=f"http://{self._host}",
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Diagnostické info – nemá Modbus registr."""
        return {"export_mode": self._mode}

    async def async_press(self) -> None:
        """Spusť export AI kontextu."""
        # Lazy import – ai_context může být velký modul a nechceme ho tahat při startu
        from .ai_context import async_export

        try:
            filepath = await async_export(self._hass, mode=self._mode)
            _LOGGER.info(
                "Acond ai_context: export dokončen, soubor %s", filepath
            )
        except Exception as err:  # noqa: BLE001 – chceme přesně logovat cokoli
            _LOGGER.exception(
                "Acond ai_context: export selhal (mode=%s): %s", self._mode, err
            )
            # Fallback notifikace – ať uživatel ví, že to neproběhlo
            from homeassistant.components import persistent_notification
            persistent_notification.async_create(
                self._hass,
                message=(
                    f"Export AI kontextu selhal:\n\n```\n{err}\n```\n\n"
                    f"Detail najdeš v logu HA (vyhledej `acond`)."
                ),
                title="❌ Acond AI kontext – chyba",
                notification_id=f"acond_ai_context_error_{self._mode}",
            )
