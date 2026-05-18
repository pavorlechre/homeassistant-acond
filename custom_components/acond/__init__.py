from __future__ import annotations
import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_HP_SERIES,
    DEFAULT_SCAN_INTERVAL,
    SENSOR_DEFINITIONS,
    HOLDING_REGISTERS_TO_POLL,
)
from .modbus_client import AcondModbusClient
from .lovelace_dashboard import async_register_dashboard, async_unregister_dashboard
from .ai_context import (
    install_log_collector,
    uninstall_log_collector,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "number", "switch", "select", "button"]


async def _probe_registers(client: AcondModbusClient) -> list[str]:
    """Zjisti které registry Acond podporuje. Vrátí seznam klíčů.

    Chybějící registry jsou normální stav pro starší firmware – logujeme
    jako DEBUG aby byl log čistý.
    """
    supported = []
    for sensor in SENSOR_DEFINITIONS:
        count = 2 if sensor.dint else 1
        result = await client.read_input_registers(sensor.address, count=count)
        if result is not None:
            supported.append(sensor.key)
            _LOGGER.debug(
                "Acond probe: registr %s (%s) nalezen", sensor.address, sensor.key
            )
        else:
            _LOGGER.debug(
                "Acond probe: registr %s (%s) nenalezen – starší firmware nebo volitelný registr",
                sensor.address,
                sensor.key,
            )
    _LOGGER.info(
        "Acond probe: nalezeno %s z %s registrů", len(supported), len(SENSOR_DEFINITIONS)
    )
    return supported


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Acond integration from a config entry."""
    host = entry.data[CONF_HOST]
    hp_series = entry.data.get(CONF_HP_SERIES, "Grandis / Economis")

    _LOGGER.info("Acond: nastavuji integraci pro %s (série: %s)", host, hp_series)

    # Ring buffer pro logy integrace – používá ho ai_context export
    install_log_collector()

    # Stažení ai_context souborů jde přes /local/acond_ai_context/<filename>
    # (statický asset z /config/www/acond_ai_context/, bez autorizace).
    # Žádná HTTP view se neregistruje.

    client = AcondModbusClient(host)
    connected = await client.connect()
    if not connected:
        _LOGGER.error("Acond: nelze se připojit na %s", host)

    # Probe – zjisti které registry TČ podporuje
    supported_keys = await _probe_registers(client)

    # Coordinator – poluje všechny nalezené input registry (FC4)
    # plus vybrané holding registry přímo přes FC3 (KROK 2.5 – FC3 read-back).
    async def async_update_data() -> dict:
        """Načti data ze všech nalezených registrů.

        Dvě fáze:
        1. Input registry (30xxx, FC4) – přes probe-detekované klíče
        2. Holding registry (40xxx, FC3) – statický seznam HOLDING_REGISTERS_TO_POLL
           pro entity, jejichž 30xxx pendant nemá pasivní zrcadlo (KROK 2.5).
        """
        data = {}

        # --- Fáze 1: input registry (30xxx) ---
        for sensor in SENSOR_DEFINITIONS:
            if sensor.key not in supported_keys:
                continue
            count = 2 if sensor.dint else 1
            result = await client.read_input_registers(sensor.address, count=count)
            if result is None:
                continue
            if sensor.dint:
                # 32bit hodnota přes dva registry (big endian)
                raw = (result[0] << 16) | result[1]
            else:
                raw = result[0]
                if sensor.signed and raw > 32767:
                    raw -= 65536
            data[sensor.key] = round(raw * sensor.scale, 2)

        # --- Fáze 2: holding registry (40xxx) přes FC3 ---
        # Self-mirror pattern: hodnota se ukládá pod klíčem zápisové entity,
        # takže Number/Switch/Select entity ji najdou přes WRITE_KEY_TO_MIRROR_KEY.
        for address, key, scale, signed in HOLDING_REGISTERS_TO_POLL:
            raw = await client.read_holding_register(address)
            if raw is None:
                # Starší firmware nebo přechodná chyba – nezahazujeme předchozí
                # hodnotu z coordinator.data (DataUpdateCoordinator si ji drží),
                # jen tento cyklus key chybí. Modbus klient logoval na DEBUG.
                continue
            if signed and raw > 32767:
                raw -= 65536
            data[key] = round(raw * scale, 2)

        if not data:
            raise UpdateFailed("Acond: žádná data ze žádného registru")
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="acond_coordinator",
        update_method=async_update_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    # První načtení – pokud selže, integrace nastartuje a zkusí znovu při pollingu
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        _LOGGER.warning("Acond: první refresh selhal, zkusím znovu při pollingu")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "supported_keys": supported_keys,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Zaregistruj Lovelace dashboard jako postranní panel
    await async_register_dashboard(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Acond integration."""
    await async_unregister_dashboard(hass)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].disconnect()
        # Pokud je to poslední config entry, odpoj i log collector
        if not hass.data[DOMAIN]:
            uninstall_log_collector()
        _LOGGER.info("Acond: integrace odstraněna")
    return unload_ok
