from __future__ import annotations
import logging
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_HP_SERIES,
    NUMBER_DEFINITIONS,
    WRITE_KEY_TO_MIRROR_KEY,
)
from .modbus_client import AcondModbusClient
from ._pending_helper import PendingValue

_LOGGER = logging.getLogger(__name__)

# Klíče, jejichž jednotka a rozsah závisí na sérii TČ
_SERIES_DEPENDENT_KEY = "comp_capacity_max_set"

# Pending timeout – viz select.py pro zdůvodnění
_PENDING_TIMEOUT = 10.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvoř number entity pro zapisovatelné holding registry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]
    hp_series = entry.data.get(CONF_HP_SERIES, "Grandis / Economis")
    host = entry.data[CONF_HOST]

    entities = []
    for number_def in NUMBER_DEFINITIONS:
        entities.append(
            AcondNumber(
                coordinator=coordinator,
                client=client,
                number_def=number_def,
                entry_id=entry.entry_id,
                hp_series=hp_series,
                host=host,
            )
        )

    _LOGGER.info("Acond: přidávám %s number entit", len(entities))
    async_add_entities(entities)


class AcondNumber(CoordinatorEntity, NumberEntity):
    """Zapisovatelná číselná hodnota přes Modbus holding registr.

    Single source of truth: native_value čte ze zrcadla v coordinatoru
    (např. t_set_tuv na 40005 zrcadlí 30005), ne z in-memory _last_value.
    Po user write je krátkodobě překryto pending value pro okamžitý feedback.

    Výjimka: entity korekce z externího čidla (t_corr_*) nemají sémanticky
    čisté zrcadlo – zapisujeme externí teplotu z HA, čteme aktuální čidlo TČ
    v jiném rozsahu. Pro tyto entity zachováváme in-memory _last_value
    (= šedivé pole po restartu HA, ale to je menší zlo než zobrazení
    nesmyslné hodnoty mimo slider rozsah).
    """

    def __init__(self, coordinator, client, number_def, entry_id: str, hp_series: str, host: str):
        super().__init__(coordinator)
        self._number_def = number_def
        self._client: AcondModbusClient = client
        self._hp_series = hp_series
        self._host = host
        self._entry_id = entry_id
        self._pending = PendingValue(timeout=_PENDING_TIMEOUT)
        # Pro t_corr_* entity – fallback in-memory hodnota (žádné zrcadlo)
        self._last_value: float | None = None
        # Cache klíče zrcadla – None pro t_corr_* a další entity bez zrcadla
        self._mirror_key: str | None = WRITE_KEY_TO_MIRROR_KEY.get(number_def.key)

        self._attr_unique_id = f"acond_{number_def.address}_{number_def.key}"
        self._attr_device_class = number_def.device_class
        self._attr_mode = NumberMode.BOX
        # Stabilní entity_id – dashboard YAML se na něj spoléhá
        self.entity_id = f"number.acond_{number_def.address}_{number_def.key}"

        # Dynamické přiřazení podle série pro kompresor
        if number_def.key == _SERIES_DEPENDENT_KEY:
            if hp_series == "PRO":
                self._attr_name = "Max. výkon kompresoru"
                self._attr_native_unit_of_measurement = UnitOfPower.WATT
                self._attr_native_min_value = 2000
                self._attr_native_max_value = 20000
                self._attr_native_step = 100
            else:
                # Standard série (Grandis / Economis): dle Modbus protokolu
                # rozsah 40014 je 1800–6000 rpm (ne 7000, jak bylo dříve – bug fix)
                self._attr_name = "Max. otáčky kompresoru"
                self._attr_native_unit_of_measurement = "rpm"
                self._attr_native_min_value = 1800
                self._attr_native_max_value = 6000
                self._attr_native_step = 1
        else:
            self._attr_name = number_def.name
            self._attr_native_unit_of_measurement = number_def.unit
            self._attr_native_min_value = number_def.min_value
            self._attr_native_max_value = number_def.max_value
            self._attr_native_step = number_def.step

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
        """Přidej registr a info o zdroji hodnoty jako atributy – usnadní ladění."""
        return {
            "modbus_register": self._number_def.address,
            "value_source": "mirror" if self._mirror_key else "in_memory",
            "mirror_register_key": self._mirror_key,
        }

    @property
    def native_value(self) -> float | None:
        """Vrať aktuální hodnotu.

        Priorita:
          1) pending value po user write (max _PENDING_TIMEOUT)
          2) zrcadlo v coordinator.data (pokud existuje mapping)
          3) in-memory _last_value (pro t_corr_* entity bez zrcadla)
          4) None (před prvním zápisem / refresh)
        """
        pending = self._pending.get()
        if pending is not None:
            return pending

        if self._mirror_key is not None:
            if not self.coordinator.data:
                return None
            # Coordinator vrací už naškálovanou hodnotu (round(raw * scale, 2)),
            # což je přesně to, co number entita zobrazuje.
            return self.coordinator.data.get(self._mirror_key)

        # Bez zrcadla (t_corr_*) – in-memory fallback, šedivé pole po restartu
        return self._last_value

    async def async_set_native_value(self, value: float) -> None:
        """Zapiš novou hodnotu do holding registru."""
        # Převeď zobrazovanou hodnotu na raw (dělíme scale)
        raw = round(value / self._number_def.scale)

        success = await self._client.write_register(self._number_def.address, raw)
        if not success:
            _LOGGER.error(
                "Acond: zápis hodnoty %s do registru %s selhal",
                value,
                self._number_def.address,
            )
            return

        # Optimistický feedback – UI zobrazí novou hodnotu okamžitě
        self._pending.set(value)
        # In-memory záloha pro entity bez zrcadla (přežije i po vypršení pending,
        # takže slider nepadá zpět na None u t_corr_*)
        self._last_value = value
        self.async_write_ha_state()

        # Vyžádat rychlou synchronizaci coordinator (debouncer ~200ms),
        # aby zrcadlo dohnalo TČ a pending mohlo bezpečně vypršet
        await self.coordinator.async_request_refresh()

        _LOGGER.debug(
            "Acond: zapsáno %s (raw=%s) do registru %s (zrcadlo: %s)",
            value, raw, self._number_def.address, self._mirror_key or "—",
        )
