from __future__ import annotations
import logging
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_HP_SERIES,
    TC_STATUS_BITS,
    HP_COMPONENT_BITS,
)

_LOGGER = logging.getLogger(__name__)

# Registr 30007 – TC_status bity
_TC_STATUS_ADDRESS = 30007
_TC_STATUS_KEY = "tc_status"

# Registr 30045 – HP_component_status bity
_HP_COMPONENT_ADDRESS = 30045
_HP_COMPONENT_KEY = "hp_component_status"

# Device class pro konkrétní bity
_TC_STATUS_DEVICE_CLASS: dict[int, str | None] = {
    0: None,                              # TČ zapnuto
    1: BinarySensorDeviceClass.RUNNING,   # TČ v provozu
    2: BinarySensorDeviceClass.PROBLEM,   # Porucha TČ
    3: None,                              # Ohřev TUV
    4: BinarySensorDeviceClass.RUNNING,   # Čerpadlo okruh 1
    5: BinarySensorDeviceClass.RUNNING,   # Čerpadlo okruh 2
    6: BinarySensorDeviceClass.RUNNING,   # Solární cirkulace
    7: BinarySensorDeviceClass.RUNNING,   # Bazénová cirkulace
    8: None,                              # Odmrazování
    9: BinarySensorDeviceClass.RUNNING,   # Bivalence
    10: None,                             # Letní provoz
    11: BinarySensorDeviceClass.RUNNING,  # Solankové čerpadlo
    12: None,                             # Chlazení
}

_HP_COMPONENT_DEVICE_CLASS: dict[int, str | None] = {
    0: BinarySensorDeviceClass.RUNNING,   # Kompresor
    1: BinarySensorDeviceClass.RUNNING,   # Ventilátor
    2: BinarySensorDeviceClass.RUNNING,   # Primární čerpadlo
    3: BinarySensorDeviceClass.RUNNING,   # Reverzní ventil
}

# Přátelské názvy z CSV v3.2
_TC_STATUS_NAMES: dict[int, str] = {
    0: "TČ zapnuto",
    1: "TČ v provozu",
    2: "Porucha TČ",
    3: "Ohřev TUV",
    4: "Čerpadlo okruh 1",
    5: "Čerpadlo okruh 2",
    6: "Solární cirkulace",
    7: "Bazénová cirkulace",
    8: "Odmrazování",
    9: "Bivalence",
    10: "Letní provoz",
    11: "Solankové čerpadlo",
    12: "Chlazení",
}

_HP_COMPONENT_NAMES: dict[int, str] = {
    0: "Kompresor",
    1: "Ventilátor",
    2: "Primární čerpadlo",
    3: "Reverzní ventil",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvoř binární senzory ze všech bitů TC_status a HP_component_status.

    Entity pro bity registru, který TČ nepodporuje, budou ve stavu 'unavailable'.
    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    supported_keys = data["supported_keys"]
    hp_series = entry.data.get(CONF_HP_SERIES, "Grandis / Economis")
    host = entry.data[CONF_HOST]

    entities = []

    # TC_status bity (30007) – vždy vytváříme všech 13 bitů
    for bit, key in TC_STATUS_BITS.items():
        entities.append(
            AcondBitSensor(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                hp_series=hp_series,
                host=host,
                register_address=_TC_STATUS_ADDRESS,
                register_key=_TC_STATUS_KEY,
                bit=bit,
                key=f"tc_status_bit_{bit}",
                name=_TC_STATUS_NAMES.get(bit, f"TC status bit {bit}"),
                device_class=_TC_STATUS_DEVICE_CLASS.get(bit),
            )
        )

    # HP_component_status bity (30045) – vždy vytváříme všech 4 bitů
    for bit, key in HP_COMPONENT_BITS.items():
        entities.append(
            AcondBitSensor(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                hp_series=hp_series,
                host=host,
                register_address=_HP_COMPONENT_ADDRESS,
                register_key=_HP_COMPONENT_KEY,
                bit=bit,
                key=f"hp_comp_bit_{bit}",
                name=_HP_COMPONENT_NAMES.get(bit, f"HP component bit {bit}"),
                device_class=_HP_COMPONENT_DEVICE_CLASS.get(bit),
            )
        )

    # Info do logu – kolik z bit-source registrů probe našel
    detected = sum(
        1 for k in (_TC_STATUS_KEY, _HP_COMPONENT_KEY) if k in supported_keys
    )
    _LOGGER.info(
        "Acond: přidávám %s binárních senzorů (zdrojových registrů detekováno: %s/2)",
        len(entities),
        detected,
    )
    async_add_entities(entities)


class AcondBitSensor(CoordinatorEntity, BinarySensorEntity):
    """Binární senzor z jednoho bitu Modbus word registru."""

    def __init__(
        self,
        coordinator,
        entry_id: str,
        hp_series: str,
        host: str,
        register_address: int,
        register_key: str,
        bit: int,
        key: str,
        name: str,
        device_class: str | None,
    ):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._hp_series = hp_series
        self._host = host
        self._register_address = register_address
        self._register_key = register_key
        self._bit = bit

        self._attr_name = name
        self._attr_unique_id = f"acond_{register_address}_{key}"
        self._attr_device_class = device_class
        # Stabilní entity_id – dashboard YAML se na něj spoléhá
        self.entity_id = f"binary_sensor.acond_{register_address}_{key}"

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
        """Přidej registr a číslo bitu jako atributy."""
        return {
            "modbus_register": self._register_address,
            "bit": self._bit,
        }

    @property
    def is_on(self) -> bool | None:
        """Vrať True pokud je bit nastaven na 1."""
        if self.coordinator.data is None:
            return None
        word = self.coordinator.data.get(self._register_key)
        if word is None:
            return None
        return bool((int(word) >> self._bit) & 1)
