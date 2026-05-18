from __future__ import annotations
import logging
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
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
    SENSOR_DEFINITIONS,
    ERROR_CODES,
    DRIVER_ERROR_CODES,
    HP_MODES,
    REG_TYPES,
    THERMAL_POWER,
)

_LOGGER = logging.getLogger(__name__)

# Klíče jejichž jednotka závisí na sérii TČ (PRO = W, Standard = rpm)
_SERIES_UNIT_KEYS = {"comp_rpm_max", "comp_rpm_actual"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvoř senzory pro všechny definované registry.

    Entity pro registry, které TČ nepodporuje, budou ve stavu 'unavailable'.
    Tento přístup je čistější než probe filtr – uživatel nedostává „Entity not
    available" v Lovelace a po update firmware TČ se entity samy „probudí".
    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    supported_keys = data["supported_keys"]
    hp_series = entry.data.get(CONF_HP_SERIES, "Standard")
    host = entry.data[CONF_HOST]

    entities = []
    for sensor_def in SENSOR_DEFINITIONS:
        entities.append(
            AcondSensor(
                coordinator=coordinator,
                sensor_def=sensor_def,
                entry_id=entry.entry_id,
                hp_series=hp_series,
                host=host,
            )
        )

    _LOGGER.info(
        "Acond: přidávám %s senzorů (z toho %s detekovaných probou)",
        len(entities),
        len(supported_keys),
    )
    async_add_entities(entities)


class AcondSensor(CoordinatorEntity, SensorEntity):
    """Senzor čtený z coordinatoru."""

    def __init__(self, coordinator, sensor_def, entry_id: str, hp_series: str, host: str):
        super().__init__(coordinator)
        self._sensor_def = sensor_def
        self._hp_series = hp_series
        self._host = host
        self._entry_id = entry_id

        self._attr_name = sensor_def.name
        self._attr_unique_id = f"acond_{sensor_def.address}_{sensor_def.key}"
        # Stabilní entity_id – dashboard YAML se na něj spoléhá
        self.entity_id = f"sensor.acond_{sensor_def.address}_{sensor_def.key}"
        self._attr_device_class = sensor_def.device_class
        self._attr_state_class = sensor_def.state_class

        # Jednotka a název – pro kompresorové senzory závisí na sérii
        # Standard série: name z const.py (obsahuje "otáčky"), unit "rpm"
        # PRO série: name přepsán "otáčky" → "výkon", unit W
        if sensor_def.key in _SERIES_UNIT_KEYS:
            if hp_series == "PRO":
                self._attr_native_unit_of_measurement = UnitOfPower.WATT
                self._attr_name = (
                    sensor_def.name
                    .replace("otáčky", "výkon")
                    .replace("Otáčky", "Výkon")
                )
            else:
                self._attr_native_unit_of_measurement = "rpm"
                # name zůstane z const.py – už obsahuje "otáčky"
        else:
            self._attr_native_unit_of_measurement = sensor_def.unit

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
        return {"modbus_register": self._sensor_def.address}

    @property
    def native_value(self):
        """Vrať hodnotu z coordinatoru, textové překlady dle slovníků."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self._sensor_def.key)
        if value is None:
            return None

        key = self._sensor_def.key

        # Chybové kódy → text
        if key == "err_number":
            return ERROR_CODES.get(int(value), f"Neznámá chyba {int(value)}")
        if key == "err_number_driver":
            return DRIVER_ERROR_CODES.get(int(value), f"Neznámá chyba driveru {int(value)}")

        # Režim TČ → text
        if key == "hp_mode":
            return HP_MODES.get(int(value), f"Neznámý režim {int(value)}")

        # Typ regulace → text
        if key == "regulation_type":
            return REG_TYPES.get(int(value), f"Neznámá regulace {int(value)}")

        # Třída výkonu → text
        if key == "thermal_power":
            return THERMAL_POWER.get(int(value), f"Neznámý výkon {int(value)}")

        return value
