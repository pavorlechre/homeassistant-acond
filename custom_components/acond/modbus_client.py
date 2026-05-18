from __future__ import annotations
import logging
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException, ModbusIOException

_LOGGER = logging.getLogger(__name__)


class AcondModbusClient:
    """Persistent Modbus client for Acond heat pump."""

    def __init__(self, host: str):
        self._host = host
        self._port = 502
        self._client = AsyncModbusTcpClient(self._host, port=self._port)

    async def connect(self) -> bool:
        """Connect to Acond. Call once at integration startup."""
        try:
            await self._client.connect()
            if self._client.connected:
                _LOGGER.info("AcondModbusClient: connected to %s:%s", self._host, self._port)
                return True
            _LOGGER.error("AcondModbusClient: connection failed")
            return False
        except Exception as err:
            _LOGGER.error("AcondModbusClient: connect exception: %s", err)
            return False

    async def disconnect(self) -> None:
        """Disconnect. Call on integration unload."""
        self._client.close()
        _LOGGER.info("AcondModbusClient: disconnected")

    async def _ensure_connected(self) -> bool:
        """Reconnect if connection was lost."""
        if self._client.connected:
            return True
        _LOGGER.warning("AcondModbusClient: connection lost, reconnecting...")
        return await self.connect()

    async def read_input_registers(self, address: int, count: int = 1):
        """Read Modbus input registers (3xxxx). Returns list or None.

        Rozlišujeme dva druhy "chyb":
        - Skutečná komunikační chyba (timeout, disconnect, malformed) → ERROR
        - Modbus exception response (Illegal Address na neexistujícím registru,
          což je normální stav u starších firmware) → DEBUG, nezahlcuje log
        """
        offset = address - 30001
        try:
            if not await self._ensure_connected():
                return None

            response = await self._client.read_input_registers(offset, count=count)

            if response is None:
                _LOGGER.error("AcondModbusClient: no response (None) at %s", address)
                return None
            if isinstance(response, (ModbusException, ModbusIOException)):
                _LOGGER.error("AcondModbusClient: Modbus exception at %s: %s", address, response)
                return None
            if response.isError():
                # Modbus exception response – legitimní odpověď "tuhle adresu neznám"
                # nebo "tuto funkci nepodporuji". Není to chyba komunikace,
                # jen starší firmware nemá všechny registry. Logujeme DEBUG.
                _LOGGER.debug(
                    "AcondModbusClient: Modbus exception response at %s: %s "
                    "(pravděpodobně neexistující registr v tomto firmware)",
                    address, response,
                )
                return None
            if not hasattr(response, "registers"):
                _LOGGER.error("AcondModbusClient: missing registers in response at %s: %s", address, response)
                return None

            return response.registers

        except Exception as err:
            _LOGGER.error("AcondModbusClient: read exception at %s: %s", address, err)
            return None

    async def read_holding_register(self, address: int) -> int | None:
        """Read single holding register (4xxxx). Returns int value or None.

        Stejná logika rozlišení chyb jako read_input_registers.
        """
        offset = address - 40001
        try:
            if not await self._ensure_connected():
                return None

            response = await self._client.read_holding_registers(offset, count=1)

            if response is None:
                _LOGGER.error("AcondModbusClient: no response reading holding reg %s", address)
                return None
            if isinstance(response, (ModbusException, ModbusIOException)):
                _LOGGER.error("AcondModbusClient: Modbus exception reading holding reg %s: %s", address, response)
                return None
            if response.isError():
                # Modbus exception response – neznámý registr, debug-level
                _LOGGER.debug(
                    "AcondModbusClient: Modbus exception response holding reg %s: %s "
                    "(pravděpodobně neexistující registr v tomto firmware)",
                    address, response,
                )
                return None
            if not hasattr(response, "registers"):
                _LOGGER.error("AcondModbusClient: missing registers reading holding reg %s", address)
                return None

            return response.registers[0]

        except Exception as err:
            _LOGGER.error("AcondModbusClient: read holding exception at %s: %s", address, err)
            return None

    async def write_register(self, address: int, value: int) -> bool:
        """Write single holding register (4xxxx). Returns True on success."""
        offset = address - 40001
        try:
            if not await self._ensure_connected():
                return False

            response = await self._client.write_register(offset, value)

            if response is None or response.isError():
                _LOGGER.error("AcondModbusClient: write error at %s: %s", address, response)
                return False

            return True

        except Exception as err:
            _LOGGER.error("AcondModbusClient: write exception: %s", err)
            return False