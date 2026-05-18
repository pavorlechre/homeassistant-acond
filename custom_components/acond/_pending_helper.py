"""Pending value helper – sdílená logika pro number/switch/select entity.

Po user write nastavujeme pending value pro okamžitý vizuální feedback
("kliknul jsem, něco se děje"). Po krátké době pending hodnota vyprší
a entita zobrazuje pravdu z TČ přes coordinator data ze zrcadla 30xxx.

Single source of truth: TČ je držitel pravdy. Pending je jen optimistický
override pro UX, ne nezávislý zdroj.

Použití:
    self._pending = PendingValue(timeout=10.0)

    # Při zápisu z UI:
    self._pending.set(new_value)
    self.async_write_ha_state()
    # plus: self.coordinator.async_request_refresh() pro rychlou synchronizaci

    # Při čtení (v native_value / is_on / current_option):
    pending = self._pending.get()
    if pending is not None:
        return pending
    return self.coordinator.data.get(mirror_key)
"""
from __future__ import annotations

import time
from typing import Any


class PendingValue:
    """Optimistický override hodnoty po user write s časovým limitem.

    Není thread-safe, ale HA běží v single-threaded asyncio loopu, takže
    všechny .set() / .get() volání jsou serializovaná v event loopu.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout
        self._value: Any = None
        self._set_at: float = 0.0  # 0.0 = žádný pending nastaven

    def set(self, value: Any) -> None:
        """Ulož pending hodnotu s aktuálním časovým razítkem."""
        self._value = value
        self._set_at = time.monotonic()

    def get(self) -> Any:
        """Vrať pending hodnotu pokud nevypršela, jinak None.

        Self-cleaning: při vypršení automaticky resetuje vnitřní stav,
        takže opakované volání get() po timeoutu vždy vrátí None.
        """
        if self._set_at == 0.0:
            return None
        if time.monotonic() - self._set_at > self._timeout:
            self._value = None
            self._set_at = 0.0
            return None
        return self._value

    def clear(self) -> None:
        """Smaž pending hodnotu (např. po explicitní synchronizaci)."""
        self._value = None
        self._set_at = 0.0
