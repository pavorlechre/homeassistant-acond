from __future__ import annotations
import logging
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_HP_SERIES,
    SELECT_DEFINITIONS,
    WRITE_KEY_TO_MIRROR_KEY,
)
from .modbus_client import AcondModbusClient
from ._pending_helper import PendingValue

_LOGGER = logging.getLogger(__name__)

# Pending timeout: po user write zobrazujeme optimistic value 10 s.
# Coordinator polluje 15 s, ale po zápisu voláme async_request_refresh()
# který spustí refresh do ~200 ms (debouncer). Synchronizace tedy proběhne
# typicky do 1–2 s, pending je jen pojistka pro feedback při pomalé síti.
_PENDING_TIMEOUT = 10.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvoř select entity pro holding registry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]
    hp_series = entry.data.get(CONF_HP_SERIES, "Grandis / Economis")
    host = entry.data[CONF_HOST]

    entities = []
    for select_def in SELECT_DEFINITIONS:
        entities.append(
            AcondSelect(
                coordinator=coordinator,
                client=client,
                select_def=select_def,
                entry_id=entry.entry_id,
                hp_series=hp_series,
                host=host,
            )
        )

    _LOGGER.info("Acond: přidávám %s select entit", len(entities))
    async_add_entities(entities)


class AcondSelect(CoordinatorEntity, SelectEntity):
    """Select entita pro výběr z pevného seznamu hodnot přes Modbus holding registr.

    Aktuálně: typ regulace (40007) – 0=AcondTherm, 1=Ekvitermní, 2=Standard.

    Single source of truth: current_option čte ze zrcadla v coordinatoru
    (sensor 30015 regulation_type), ne z in-memory _last_option. Po user
    write je krátkodobě překryto pending value pro okamžitý feedback.
    """

    def __init__(self, coordinator, client, select_def, entry_id: str, hp_series: str, host: str):
        super().__init__(coordinator)
        self._select_def = select_def
        self._client: AcondModbusClient = client
        self._hp_series = hp_series
        self._host = host
        self._entry_id = entry_id
        self._pending = PendingValue(timeout=_PENDING_TIMEOUT)

        self._attr_name = select_def.name
        self._attr_unique_id = f"acond_{select_def.address}_{select_def.key}"
        # Stabilní entity_id – dashboard YAML se na něj spoléhá
        self.entity_id = f"select.acond_{select_def.address}_{select_def.key}"
        # Možnosti jako seznam textových hodnot (HA potřebuje list[str])
        self._attr_options = list(select_def.options.values())

        # Zpětné mapování text → číslo pro zápis
        self._options_inv: dict[str, int] = {v: k for k, v in select_def.options.items()}

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
        """Přidej registr a raw_value jako atributy – usnadní ladění a automatizace."""
        attrs = {"modbus_register": self._select_def.address}
        current = self.current_option
        if current is not None:
            attrs["raw_value"] = self._options_inv.get(current)
        return attrs

    @property
    def current_option(self) -> str | None:
        """Vrať aktuálně vybranou možnost.

        Priorita: 1) pending value po user write (max _PENDING_TIMEOUT)
                  2) text ze zrcadla v coordinator data
                  3) None (při startu před prvním refresh)
        """
        pending = self._pending.get()
        if pending is not None:
            return pending

        mirror_key = WRITE_KEY_TO_MIRROR_KEY.get(self._select_def.key)
        if mirror_key is None:
            # Defensivní fallback – select_def.key by měl vždy být v mapě
            return None

        if not self.coordinator.data:
            return None

        # Coordinator vrací číselnou hodnotu (0, 1, 2) – sensor.py rozhoduje
        # o text-mappingu až při displayování senzoru. Tady překládáme stejně.
        raw = self.coordinator.data.get(mirror_key)
        if raw is None:
            return None
        try:
            raw_int = int(raw)
        except (TypeError, ValueError):
            return None
        return self._select_def.options.get(raw_int)

    async def async_select_option(self, option: str) -> None:
        """Zapiš vybranou možnost do holding registru."""
        raw = self._options_inv.get(option)
        if raw is None:
            _LOGGER.error("Acond: neznámá volba '%s' pro select %s", option, self._select_def.key)
            return

        success = await self._client.write_register(self._select_def.address, raw)
        if success:
            # Optimistický feedback – UI zobrazí novou hodnotu okamžitě
            self._pending.set(option)
            self.async_write_ha_state()
            # Vyžádat rychlou synchronizaci (debouncer ~200ms)
            await self.coordinator.async_request_refresh()
            _LOGGER.debug(
                "Acond: select %s nastaven na '%s' (raw=%s, registr %s)",
                self._select_def.key,
                option,
                raw,
                self._select_def.address,
            )
        else:
            _LOGGER.error(
                "Acond: zápis select %s selhal (registr %s)",
                self._select_def.key,
                self._select_def.address,
            )
