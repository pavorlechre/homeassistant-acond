from __future__ import annotations
import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_HP_SERIES,
    SWITCH_DEFINITIONS,
    MODE_BY_BIT,
    WRITE_KEY_TO_MIRROR_KEY,
)
from .modbus_client import AcondModbusClient
from ._pending_helper import PendingValue

_LOGGER = logging.getLogger(__name__)

# Pending timeout – viz select.py pro zdůvodnění
_PENDING_TIMEOUT = 10.0

# Adresa registru režimů a bity, které jsou v něm exclusive (jen jeden aktivní)
_TC_SET_REGISTER = 40006
_MODE_BITS = (0, 1, 2, 3, 4)
_STATUS_BITS = (6, 7)  # Solár, Bazén – nejsou exclusive, čteno přes tc_status


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvoř switch entity pro holding registry.

    Two-pass setup: vytvoříme všechny entity, pak mode-switche (bity 0-4 v 40006)
    získají vzájemné reference – při kliku na jeden potřebují nastavit pending
    pro ostatní (mutual exclusion).
    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]
    hp_series = entry.data.get(CONF_HP_SERIES, "Grandis / Economis")
    host = entry.data[CONF_HOST]

    entities: list[AcondSwitch] = []
    mode_switches: dict[int, AcondSwitch] = {}

    for switch_def in SWITCH_DEFINITIONS:
        sw = AcondSwitch(
            coordinator=coordinator,
            client=client,
            switch_def=switch_def,
            entry_id=entry.entry_id,
            hp_series=hp_series,
            host=host,
        )
        entities.append(sw)
        if (switch_def.address == _TC_SET_REGISTER
                and switch_def.bit in _MODE_BITS):
            mode_switches[switch_def.bit] = sw

    # Pass 2: každý mode switch dostane referenci na sourozence pro mutual
    # exclusion. Sdílí jeden dict, takže update na jednom je vidět ostatním.
    for sw in mode_switches.values():
        sw._mode_switches = mode_switches

    _LOGGER.info("Acond: přidávám %s switch entit (z toho %s mode switche)",
                 len(entities), len(mode_switches))
    async_add_entities(entities)


class AcondSwitch(CoordinatorEntity, SwitchEntity):
    """Přepínač zapisující do Modbus holding registru.

    Pro bity registru 40006 (TC_set) používá read-modify-write:
    1. Přečti aktuální hodnotu celého registru
    2. Změň pouze příslušný bit
    3. Zapiš zpět celý registr

    POZOR: Acond povoluje pouze jednoho Modbus mastera – read-modify-write
    je atomická na úrovni naší integrace (coordinator nepíše, jen čte),
    ale není chráněna před externími zásahy přes fyzický panel.

    Single source of truth – is_on čte ze zrcadla v coordinatoru, ne z
    in-memory stavu. Tři varianty podle typu switche:

    1) Mode switche (40006 bit 0-4): zrcadlo přes 30014 hp_mode (text)
       a mapu MODE_BY_BIT. Mutually exclusive – klik na jeden ovlivní
       pending u ostatních 4 (zhasnou).

    2) Status bit switche (40006 bit 6, 7 – Solár, Bazén): zrcadlo přes
       30007 tc_status, příslušný bit. Nezávislé na sobě.

    3) Celoregistrové switche (40016, 40017, 40018): přímé zrcadlo přes
       WRITE_KEY_TO_MIRROR_KEY (manual_pwm, manual_eh, silent_mode).
    """

    def __init__(self, coordinator, client, switch_def, entry_id: str, hp_series: str, host: str):
        super().__init__(coordinator)
        self._switch_def = switch_def
        self._client: AcondModbusClient = client
        self._hp_series = hp_series
        self._host = host
        self._entry_id = entry_id
        self._pending = PendingValue(timeout=_PENDING_TIMEOUT)

        # Reference na slovník mode switchů – nastaví ji setup_entry pass 2.
        # Nepoužívá se pro non-mode switche.
        self._mode_switches: dict[int, "AcondSwitch"] | None = None

        self._attr_name = switch_def.name
        self._attr_unique_id = f"acond_{switch_def.address}_{switch_def.key}"
        # Stabilní entity_id – dashboard YAML se na něj spoléhá
        self.entity_id = f"switch.acond_{switch_def.address}_{switch_def.key}"

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
        """Přidej registr a bit jako atributy – usnadní ladění."""
        attrs = {"modbus_register": self._switch_def.address}
        if self._switch_def.bit is not None:
            attrs["bit"] = self._switch_def.bit
        # Indikace zdroje pravdy – pomáhá při ladění
        attrs["value_source"] = self._value_source_label()
        return attrs

    def _value_source_label(self) -> str:
        """Pomocný popis pro debugování – odkud entita čte stav."""
        if self._is_mode_switch():
            return "hp_mode_via_MODE_BY_BIT"
        if self._is_status_bit_switch():
            return "tc_status_bit"
        if self._switch_def.key in WRITE_KEY_TO_MIRROR_KEY:
            return "direct_mirror"
        return "none"

    def _is_mode_switch(self) -> bool:
        return (self._switch_def.address == _TC_SET_REGISTER
                and self._switch_def.bit in _MODE_BITS)

    def _is_status_bit_switch(self) -> bool:
        return (self._switch_def.address == _TC_SET_REGISTER
                and self._switch_def.bit in _STATUS_BITS)

    @property
    def is_on(self) -> bool | None:
        """Vrať aktuální stav přepínače.

        Priorita: 1) pending value po user write
                  2) pravda ze zrcadla podle typu switche
                  3) None (před prvním refresh nebo při chybě)
        """
        pending = self._pending.get()
        if pending is not None:
            return pending

        if not self.coordinator.data:
            return None

        # 1) Mode switche – porovnání čísla hp_mode s MODE_BY_BIT
        # Coordinator drží surovou číselnou hodnotu (text-mapping přes HP_MODES
        # se aplikuje až v sensor entity), proto porovnáváme čísla.
        if self._is_mode_switch():
            hp_mode = self.coordinator.data.get("hp_mode")
            if hp_mode is None:
                return None
            try:
                hp_mode_int = int(hp_mode)  # může přijít float (scale=1.0 → round())
            except (TypeError, ValueError):
                return None
            expected = MODE_BY_BIT.get(self._switch_def.bit)
            return hp_mode_int == expected

        # 2) Status bit switche – bit v 30007 tc_status
        if self._is_status_bit_switch():
            tc_status = self.coordinator.data.get("tc_status")
            if tc_status is None:
                return None
            try:
                tc_status_int = int(tc_status)
            except (TypeError, ValueError):
                return None
            return bool(tc_status_int & (1 << self._switch_def.bit))

        # 3) Celoregistrové switche – přímé zrcadlo (0/1)
        mirror_key = WRITE_KEY_TO_MIRROR_KEY.get(self._switch_def.key)
        if mirror_key is None:
            return None
        value = self.coordinator.data.get(mirror_key)
        if value is None:
            return None
        return bool(int(value))

    async def async_turn_on(self, **kwargs) -> None:
        """Zapni přepínač – zapiš 1 nebo nastav bit."""
        await self._write(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Vypni přepínač – zapiš 0 nebo smaž bit."""
        await self._write(False)

    async def _write(self, turn_on: bool) -> None:
        """Zapiš stav do registru – celý registr nebo bit (read-modify-write)."""
        if self._switch_def.bit is None:
            # Celý registr – prostý zápis 0 nebo 1
            value = 1 if turn_on else 0
            success = await self._client.write_register(self._switch_def.address, value)
        else:
            # Bit v registru – read-modify-write
            current = await self._client.read_holding_register(self._switch_def.address)
            if current is None:
                _LOGGER.error(
                    "Acond: nelze přečíst registr %s před zápisem bitu %s",
                    self._switch_def.address,
                    self._switch_def.bit,
                )
                return
            if turn_on:
                new_value = current | (1 << self._switch_def.bit)
            else:
                new_value = current & ~(1 << self._switch_def.bit)
            success = await self._client.write_register(self._switch_def.address, new_value)

        if not success:
            _LOGGER.error(
                "Acond: zápis switch %s selhal (registr %s, bit %s)",
                self._switch_def.key,
                self._switch_def.address,
                self._switch_def.bit,
            )
            return

        # Optimistický feedback. U mode switchů aktualizujeme i sourozence.
        if self._is_mode_switch() and turn_on and self._mode_switches:
            # Mutual exclusion – kliknutý → True, ostatní 4 → False.
            # Pro turn_on=False nelze rozumně určit, který režim TČ teď je –
            # necháme to vyřešit coordinator refresh.
            for bit, sibling in self._mode_switches.items():
                sibling._pending.set(bit == self._switch_def.bit)
                sibling.async_write_ha_state()
        else:
            # Single switch update (status bity, celoregistrové, mode turn_off)
            self._pending.set(turn_on)
            self.async_write_ha_state()

        # Vyžádat rychlou synchronizaci coordinatoru (debouncer ~200ms)
        await self.coordinator.async_request_refresh()

        _LOGGER.debug(
            "Acond: switch %s nastaven na %s (registr %s, bit %s)",
            self._switch_def.key,
            turn_on,
            self._switch_def.address,
            self._switch_def.bit,
        )
