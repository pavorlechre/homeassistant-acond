"""Acond AI Context exporter.

Sbírá strukturovaný snapshot stavu Home Assistant a produkuje markdown
soubor vhodný pro vložení do kontextu AI asistenta (ChatGPT, Claude…).

Dva režimy:
    - "acond"  – jen entity, automatizace, skripty, scény a pomocníci
                 související s integrací Acond (prefix entity_id acond_
                 + tranzitivně objekty, které je referencují)
    - "full"   – kompletní snapshot HA

Výstupní soubor leží v /config/www/acond_ai_context/, stahuje se přes
URL /local/acond_ai_context/<filename> (statický asset bez autorizace).

POZOR: Výstup může obsahovat citlivá data (tokeny, API klíče z automatizací).
Před redakcí se maskují hodnoty polí jako password, token, secret, webhook…
Úplnou ochranu ale nezaručíme – uživatel musí soubor před odesláním do AI
zkontrolovat. Varování je součástí vygenerovaného markdownu.
"""
from __future__ import annotations

import logging
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

# Výstupní složka pod /config/www → HA serveruje jako /local/acond_ai_context/
# bez autorizace (jako statický asset). Plná URL k souboru přes /local/...
# nezachytí frontend jako SPA route a nevyžaduje session cookie, takže klik
# v persistent_notification spolehlivě stáhne soubor v každém prohlížeči.
_OUTPUT_SUBDIR = "www/acond_ai_context"
_PUBLIC_URL_PREFIX = "/local/acond_ai_context"

# Prefix pro identifikaci Acond entit
_ACOND_PREFIX = "acond_"

# Kolik řádků logu integrace připojit
_LOG_TAIL_LINES = 30

# Kolik řádků globálního WARNING+ERROR logu připojit (větší buffer – errory
# bývají rozptýlené v čase, potřebujeme delší retrospektivu)
_GLOBAL_ERROR_LINES = 100

# Soft cap na jeden YAML config v automation/script/scene – ať soubor neexploduje
# Pokud má někdo 200kB automatizaci, oříznu ji a poznamenám původní velikost.
_MAX_YAML_BLOCK_BYTES = 4000

# Klíče, jejichž hodnoty se v datech maskují (case-insensitive substring match)
_SECRET_KEY_PATTERNS = (
    "password", "passwd",
    "api_key", "apikey",
    "token", "access_token", "refresh_token",
    "secret", "client_secret",
    "webhook_url", "webhook",
    "bearer", "authorization", "auth",
    "private_key",
)
_REDACTED = "***REDACTED***"

# Domény, jejichž objekty potenciálně obsahují reference na acond entity
# a chceme je v acond-only režimu skenovat
_REFERENCING_DOMAINS = ("automation", "script", "scene")

# Domény pomocníků (input helpers)
_HELPER_DOMAINS = (
    "input_boolean", "input_number", "input_select",
    "input_text", "input_datetime", "input_button",
    "counter", "timer",
)


# ===========================================================================
# RING BUFFERY PRO LOGY
# ===========================================================================
# HA nemá API pro "dej mi posledních N řádků logu". Řešíme dvěma vlastními
# handlery:
#   1) _AcondLogCollector – sbírá logy custom_components.acond (pro debug
#      naší integrace)
#   2) _GlobalErrorCollector – sbírá WARNING+ERROR ze všech zdrojů
#      (pro diagnostiku problémů v jiných integracích, které mohou souviset
#      s tím, proč acond automatizace nefunguje)

class _AcondLogCollector(logging.Handler):
    """Drží v paměti ring buffer posledních N zpráv z loggeru acond."""

    def __init__(self, capacity: int = _LOG_TAIL_LINES):
        super().__init__(level=logging.DEBUG)
        self._buffer: deque[str] = deque(maxlen=capacity)
        self.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.append(self.format(record))
        except Exception:  # logger handlery nesmí nikdy hodit
            pass

    def tail(self) -> list[str]:
        return list(self._buffer)


class _GlobalErrorCollector(logging.Handler):
    """Ring buffer WARNING+ERROR zpráv napříč všemi loggery HA.

    Záměrně držíme jen WARNING+ – DEBUG/INFO by buffer rychle přepsalo
    a pro diagnostiku obvykle nepotřebujeme. Buffer větší než acond log,
    protože errory bývají rozptýlené v čase.
    """

    def __init__(self, capacity: int = _GLOBAL_ERROR_LINES):
        super().__init__(level=logging.WARNING)
        self._buffer: deque[str] = deque(maxlen=capacity)
        self.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.append(self.format(record))
        except Exception:
            pass

    def tail(self) -> list[str]:
        return list(self._buffer)


_log_collector: _AcondLogCollector | None = None
_global_error_collector: _GlobalErrorCollector | None = None


def install_log_collector() -> None:
    """Zavěs oba ring buffery. Volat jednou při setupu integrace."""
    global _log_collector, _global_error_collector

    if _log_collector is None:
        _log_collector = _AcondLogCollector()
        logging.getLogger(f"custom_components.{DOMAIN}").addHandler(_log_collector)

    if _global_error_collector is None:
        _global_error_collector = _GlobalErrorCollector()
        # Root logger – zachytí všechno z HA
        logging.getLogger().addHandler(_global_error_collector)


def uninstall_log_collector() -> None:
    """Odpoj oba ring buffery. Volat při unloadu integrace."""
    global _log_collector, _global_error_collector

    if _log_collector is not None:
        logging.getLogger(f"custom_components.{DOMAIN}").removeHandler(_log_collector)
        _log_collector = None

    if _global_error_collector is not None:
        logging.getLogger().removeHandler(_global_error_collector)
        _global_error_collector = None


# ===========================================================================
# SCANNER – sbírá raw data z HA do dict struktury
# ===========================================================================

async def _scan_versions(hass: HomeAssistant) -> dict:
    """Verze HA core, integrace, pymodbus."""
    from homeassistant.const import __version__ as ha_version

    try:
        import pymodbus
        pymodbus_version = getattr(pymodbus, "__version__", "unknown")
    except ImportError:
        pymodbus_version = "not installed"

    return {
        "home_assistant": ha_version,
        "acond_integration": VERSION,
        "pymodbus": pymodbus_version,
    }


async def _scan_config_entries(hass: HomeAssistant) -> list[dict]:
    """Config entries integrace acond (IP, série)."""
    entries = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        entries.append({
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": dict(entry.data),          # bude redigováno později
            "options": dict(entry.options),
            "state": str(entry.state),
        })
    return entries


async def _scan_areas(hass: HomeAssistant) -> list[dict]:
    """Všechny areas v HA."""
    registry = ar.async_get(hass)
    return [
        {"area_id": a.id, "name": a.name, "icon": a.icon}
        for a in registry.async_list_areas()
    ]


async def _scan_devices(hass: HomeAssistant) -> list[dict]:
    """Všechna zařízení v HA."""
    registry = dr.async_get(hass)
    devices = []
    for d in registry.devices.values():
        devices.append({
            "device_id": d.id,
            "name": d.name_by_user or d.name,
            "manufacturer": d.manufacturer,
            "model": d.model,
            "sw_version": d.sw_version,
            "area_id": d.area_id,
            "config_entries": list(d.config_entries),
            "identifiers": [list(i) for i in d.identifiers],
            "disabled": d.disabled_by is not None,
        })
    return devices


async def _scan_entities(hass: HomeAssistant) -> list[dict]:
    """Všechny entity s aktuálním stavem a attributy.

    Sleduje DVA zdroje:
      1) entity_registry – integrace, jejichž entity mají unique_id
      2) hass.states – legacy YAML senzory definované v configuration.yaml
         (`sensor: - platform: rest`, `sensor: - platform: template`,
         `rest:` blok, `utility_meter:` v některých variantách atd.),
         které unique_id nemají a do entity_registry se nikdy nedostanou

    Zdroj entity je v poli ``source``: "registry" nebo "yaml". Pro YAML
    entity je ``platform`` vyplněna jako "yaml" (nemáme přesný platform
    jako u registry – tu informaci by šlo dohledat jen čtením YAML
    souborů, což je křehké napříč instalacemi).
    """
    registry = er.async_get(hass)
    entities: list[dict] = []
    seen: set[str] = set()

    # 1) Entity z entity_registry (integrace s unique_id)
    for e in registry.entities.values():
        state_obj = hass.states.get(e.entity_id)
        entities.append({
            "entity_id": e.entity_id,
            "unique_id": e.unique_id,
            "platform": e.platform,
            "domain": e.domain,
            "device_id": e.device_id,
            "area_id": e.area_id,
            "name": e.name or (state_obj.attributes.get("friendly_name") if state_obj else None),
            "disabled": e.disabled_by is not None,
            "hidden": e.hidden_by is not None,
            "state": state_obj.state if state_obj else None,
            "attributes": dict(state_obj.attributes) if state_obj else {},
            "source": "registry",
        })
        seen.add(e.entity_id)

    # 2) YAML legacy entity – v hass.states ale ne v entity_registry
    #    Patří sem: sensor: platform: rest/template/command_line/...,
    #    rest: bez unique_id, utility_meter: definovaný v YAML, atd.
    for state in hass.states.async_all():
        if state.entity_id in seen:
            continue
        domain = state.entity_id.split(".", 1)[0] if "." in state.entity_id else None
        entities.append({
            "entity_id": state.entity_id,
            "unique_id": None,
            "platform": "yaml",
            "domain": domain,
            "device_id": None,
            "area_id": None,
            "name": state.attributes.get("friendly_name"),
            "disabled": False,
            "hidden": False,
            "state": state.state,
            "attributes": dict(state.attributes),
            "source": "yaml",
        })

    return entities


async def _scan_yaml_domain(hass: HomeAssistant, domain: str) -> list[dict]:
    """Načti YAML objekty z domény (automation, script, scene, input_*).

    HA drží tyto objekty ve dvou možných místech:
    - UI editor: .storage/<domain>
    - YAML: config/<domain>s.yaml nebo configuration.yaml klíč

    Místo pokusů číst zdrojové soubory (cesty se liší, kódování, escape…)
    bereme živé objekty z hass.data. To nám dá aktuální stav tak, jak ho HA
    sám drží v paměti – včetně UI editorů i YAML definic.
    """
    # Pro automation, script, scene, input_* komponenty má HA Component
    # objekt v hass.data. Jeho entities nám dají přístup k aktuální config.
    component_data = hass.data.get(domain)
    if component_data is None:
        return []

    items = []

    # EntityComponent ukládá entities v .entities dict (entity_id -> Entity)
    entities_dict = getattr(component_data, "entities", None)
    if entities_dict is None and hasattr(component_data, "_entities"):
        entities_dict = component_data._entities

    if entities_dict is not None:
        try:
            iterable = entities_dict.values() if hasattr(entities_dict, "values") else entities_dict
            for entity in iterable:
                item = _entity_to_yaml_dict(entity)
                if item:
                    items.append(item)
        except Exception as err:  # HA verze se liší, tolerujeme
            _LOGGER.debug("Acond ai_context: nelze iterovat %s: %s", domain, err)

    return items


def _entity_to_yaml_dict(entity: Any) -> dict | None:
    """Vytáhni z Entity objektu jeho YAML konfiguraci (pokud je dostupná)."""
    entity_id = getattr(entity, "entity_id", None)
    if not entity_id:
        return None

    result: dict = {"entity_id": entity_id, "name": getattr(entity, "name", None)}

    # Automatizace a skripty mají atribut raw_config / config / _config
    for attr in ("raw_config", "config", "_config", "_raw_config"):
        cfg = getattr(entity, attr, None)
        if cfg is not None:
            result["config"] = cfg
            break

    # Pro scény
    scene_cfg = getattr(entity, "scene_config", None)
    if scene_cfg is not None:
        result["config"] = {
            "name": getattr(scene_cfg, "name", None),
            "entities": dict(getattr(scene_cfg, "states", {})),
        }

    # Pro input_* helpery – jejich stav + definice
    for attr in ("_config", "_attr_initial"):
        cfg = getattr(entity, attr, None)
        if cfg is not None and "config" not in result:
            result["config"] = cfg
            break

    # Současný stav
    result["state"] = getattr(entity, "state", None)

    return result


async def _scan_automations(hass: HomeAssistant) -> list[dict]:
    return await _scan_yaml_domain(hass, "automation")


async def _scan_scripts(hass: HomeAssistant) -> list[dict]:
    return await _scan_yaml_domain(hass, "script")


async def _scan_scenes(hass: HomeAssistant) -> list[dict]:
    return await _scan_yaml_domain(hass, "scene")


async def _scan_helpers(hass: HomeAssistant) -> dict[str, list[dict]]:
    """Všichni input_* pomocníci + counter + timer."""
    result = {}
    for domain in _HELPER_DOMAINS:
        items = await _scan_yaml_domain(hass, domain)
        if items:
            result[domain] = items
    return result


async def _scan_integration_log() -> list[str]:
    """Posledních N řádků logu integrace."""
    if _log_collector is None:
        return ["(log collector není aktivní – integrace pravděpodobně právě nabíhá)"]
    return _log_collector.tail()


async def _scan_recent_errors() -> list[str]:
    """Posledních N WARNING+ERROR ze všech zdrojů HA.

    Klíčové pro diagnostiku: když automatizace nefunguje, problém často není
    v acondu, ale v jiné integraci, kterou automatizace volá. Tyhle errory
    AI nasměrují správným směrem.
    """
    if _global_error_collector is None:
        return ["(global error collector není aktivní)"]
    return _global_error_collector.tail()


async def _scan_repairs_issues(hass: HomeAssistant) -> list[dict]:
    """HA Repairs registry – aktivní problémy, které HA detekoval.

    Od HA 2022.11 mají integrace API pro reportování problémů (deprecated
    config, chybějící device, atd.). Toto je první místo, kam by AI měla
    koukat při diagnostice.
    """
    issues = []
    try:
        from homeassistant.helpers import issue_registry as ir
        registry = ir.async_get(hass)
        for issue in registry.issues.values():
            issues.append({
                "issue_id": issue.issue_id,
                "domain": issue.domain,
                "severity": str(issue.severity),
                "is_fixable": issue.is_fixable,
                "active": issue.active,
                "translation_key": issue.translation_key,
                "translation_placeholders": dict(issue.translation_placeholders or {}),
                "created_at": issue.created.isoformat() if issue.created else None,
                "dismissed_version": issue.dismissed_version,
                "learn_more_url": issue.learn_more_url,
            })
    except ImportError:
        # Velmi staré HA bez issue registry – ignoruj
        return [{"_note": "issue_registry není dostupný v této verzi HA"}]
    except Exception as err:
        _LOGGER.debug("Acond ai_context: nelze načíst issue registry: %s", err)
        return [{"_error": f"Chyba při čtení issue registry: {err}"}]
    return issues


async def _scan_config_entries_health(hass: HomeAssistant) -> list[dict]:
    """Stav VŠECH config entries v HA, ne jen acond.

    Důležité pro diagnostiku: pokud jiná integrace selhala při setupu
    (state == 'setup_error'), může to vysvětlit, proč acond automatizace
    referencující její entity nefunguje.

    Acond config entries jsou v sekci 'config_entries' (s plnými daty).
    Tady jen zdravotní přehled napříč všemi integracemi.
    """
    health = []
    for entry in hass.config_entries.async_entries():
        item = {
            "entry_id": entry.entry_id,
            "domain": entry.domain,
            "title": entry.title,
            "state": str(entry.state),
            "disabled_by": str(entry.disabled_by) if entry.disabled_by else None,
            "source": entry.source,
        }
        # Pokud entry selhalo, přidej důvod
        reason = getattr(entry, "reason", None)
        if reason:
            item["reason"] = reason
        # Pokud je entry v error stavu, je to klíčová info
        if "error" in str(entry.state).lower() or "failed" in str(entry.state).lower():
            item["_problem"] = True
        health.append(item)
    return health


async def _scan_system_info(hass: HomeAssistant) -> dict:
    """Základní info o HA instalaci – architektura, deployment, paměť.

    Pomáhá AI rozhodnout, jestli problém může souviset s prostředím
    (např. ARM64 nepodporuje některé wheels, omezená paměť ovlivňuje
    velké šablony, supervisor vs. core install má jiné možnosti).
    """
    info: dict = {}

    # Konfigurace HA – časová zóna, jednotky, jazyk
    try:
        cfg = hass.config
        info["time_zone"] = str(cfg.time_zone)
        info["units"] = type(cfg.units).__name__
        info["language"] = cfg.language
        info["country"] = cfg.country
        info["external_url"] = cfg.external_url
        info["internal_url"] = cfg.internal_url
        info["config_dir"] = cfg.config_dir
    except Exception as err:
        info["_config_error"] = str(err)

    # System info (architektura, OS) – HA má helper, ale liší se mezi verzemi
    try:
        from homeassistant.helpers.system_info import async_get_system_info
        sys_info = await async_get_system_info(hass)
        # Zfiltruj jen klíčové údaje, celý dict může být velký
        for key in (
            "version", "installation_type", "dev", "hassio",
            "docker", "container", "user", "virtualenv",
            "python_version", "os_name", "os_version", "arch",
            "timezone", "supervisor", "host_os",
        ):
            if key in sys_info:
                info[key] = sys_info[key]
    except Exception as err:
        info["_system_info_error"] = str(err)

    # Supervisor info – jen když běžíme pod HA OS / Supervised
    try:
        if "hassio" in hass.config.components:
            from homeassistant.components.hassio import get_host_info, get_supervisor_info
            host = get_host_info(hass)
            sup = get_supervisor_info(hass)
            if host:
                info["hassos_version"] = host.get("operating_system")
                info["hassos_kernel"] = host.get("kernel")
            if sup:
                info["supervisor_version"] = sup.get("version")
    except Exception:
        # Supervisor info není dostupné – běží jako Core nebo Container
        pass

    return info


async def scan_home_assistant(hass: HomeAssistant) -> dict:
    """Hlavní scanner – vrátí kompletní dict snapshot HA.

    Data jsou RAW, neredigovaná. Redakci volá volající před filtrováním.
    """
    _LOGGER.debug("Acond ai_context: spouštím scan HA")

    snapshot = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "versions": await _scan_versions(hass),
        "system_info": await _scan_system_info(hass),
        "config_entries": await _scan_config_entries(hass),
        "config_entries_health": await _scan_config_entries_health(hass),
        "repairs_issues": await _scan_repairs_issues(hass),
        "areas": await _scan_areas(hass),
        "devices": await _scan_devices(hass),
        "entities": await _scan_entities(hass),
        "automations": await _scan_automations(hass),
        "scripts": await _scan_scripts(hass),
        "scenes": await _scan_scenes(hass),
        "helpers": await _scan_helpers(hass),
        "integration_log": await _scan_integration_log(),
        "recent_errors": await _scan_recent_errors(),
    }

    _LOGGER.debug(
        "Acond ai_context: scan hotov – %s entit, %s zařízení, %s automatizací, "
        "%s issues, %s recent errors",
        len(snapshot["entities"]),
        len(snapshot["devices"]),
        len(snapshot["automations"]),
        len(snapshot["repairs_issues"]),
        len(snapshot["recent_errors"]),
    )
    return snapshot


# ===========================================================================
# REDAKTOR – maskování citlivých hodnot
# ===========================================================================

def _is_secret_key(key: Any) -> bool:
    """True pokud klíč (podle názvu) pravděpodobně obsahuje citlivou hodnotu."""
    if not isinstance(key, str):
        return False
    low = key.lower()
    return any(p in low for p in _SECRET_KEY_PATTERNS)


def redact_secrets(data: Any) -> Any:
    """Rekurzivně nahradí hodnoty citlivých polí za ***REDACTED***.

    Pracuje na dictech, listech, tuplech a skalárech. Vrací novou strukturu,
    vstup nemění.
    """
    if isinstance(data, dict):
        return {
            k: (_REDACTED if _is_secret_key(k) and v else redact_secrets(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_secrets(item) for item in data]
    if isinstance(data, tuple):
        return tuple(redact_secrets(item) for item in data)
    return data


# ===========================================================================
# FILTR – acond-only režim
# ===========================================================================

def _contains_acond_reference(obj: Any) -> bool:
    """Full-text match: obsahuje serializovaná reprezentace objektu 'acond_'?

    Pokrývá entity_id, templates, service targets i komentáře. False positives
    akceptujeme – mít v kontextu navíc nesouvisející automatizaci je menší
    problém než chybějící související automatizaci.
    """
    try:
        text = repr(obj)
    except Exception:
        return False
    return _ACOND_PREFIX in text


def _collect_acond_entity_ids(entities: list[dict]) -> set[str]:
    """Množina entity_id všech entit integrace acond."""
    ids = set()
    for e in entities:
        eid = e.get("entity_id", "")
        # Shoda podle platformy (jistější) nebo podle prefixu v entity_id
        if e.get("platform") == DOMAIN:
            ids.add(eid)
            continue
        # Fallback – entity_id obsahuje acond_ kdekoli (pokrývá případy,
        # kdy uživatel entitu přejmenoval, ale ponechal prefix)
        if _ACOND_PREFIX in eid:
            ids.add(eid)
    return ids


def _filter_referencing_items(
    items: list[dict],
    must_contain: str = _ACOND_PREFIX,
) -> list[dict]:
    """Vybere z listu items ty, jejichž config obsahuje must_contain."""
    result = []
    for item in items:
        cfg = item.get("config")
        # Full-text search přes celý item (config i metadata)
        if cfg is not None and _ACOND_PREFIX in repr(cfg):
            result.append(item)
            continue
        if must_contain in repr(item):
            result.append(item)
    return result


def _collect_helper_references(items: list[dict]) -> set[str]:
    """Vrátí množinu entity_id pomocníků (input_*, counter, timer) referencovaných
    v daných itemech (typicky automatizace, skripty, scény).
    """
    helper_ids = set()
    helper_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(d) for d in _HELPER_DOMAINS) + r")\.[a-zA-Z0-9_]+"
    )
    for item in items:
        text = repr(item)
        for match in helper_pattern.finditer(text):
            helper_ids.add(match.group(0))
    return helper_ids


def _select_yaml_in_acond_scope(
    snapshot: dict,
    acond_entities: list[dict],
    filtered_automations: list[dict],
    filtered_scripts: list[dict],
    filtered_scenes: list[dict],
) -> list[dict]:
    """Vybere YAML legacy entity, které patří do acond rozsahu.

    Pravidla (oboustranná tranzitivní reference – stačí splnit jedno):
      a) Některý objekt v acond rozsahu (acond entita, automatizace,
         skript nebo scéna) na tuto YAML entitu odkazuje – typicky
         template senzor použitý jako vstup v automatizaci.
      b) Tato YAML entita sama odkazuje na acond entitu – typicky
         ``utility_meter`` se ``source: sensor.acond_*`` (HA u utility
         meteru drží hodnotu source v state.attributes, takže to
         najde ``_contains_acond_reference``).

    YAML entity, které neprojdou ani jedním pravidlem, do acond módu
    nepatří – objeví se jen ve full exportu.
    """
    all_yaml = [
        e for e in snapshot.get("entities", []) if e.get("source") == "yaml"
    ]
    if not all_yaml:
        return []

    # Sjednocený text všech acond-relevantních objektů – v tom hledáme
    # entity_id YAML entit (případ a)
    acond_scope_text = (
        repr(acond_entities)
        + repr(filtered_automations)
        + repr(filtered_scripts)
        + repr(filtered_scenes)
    )

    selected = []
    for ye in all_yaml:
        eid = ye.get("entity_id", "")
        if not eid:
            continue
        # (a) odkaz Z acond rozsahu NA tuto YAML entitu
        if eid in acond_scope_text:
            selected.append(ye)
            continue
        # (b) odkaz Z této YAML entity NA acond (utility_meter source ap.)
        if _contains_acond_reference(ye):
            selected.append(ye)
    return selected


def filter_acond_only(snapshot: dict) -> dict:
    """Z kompletního snapshotu vytvoří podmnožinu související s integrací Acond.

    Pravidla:
    - entity: platform == 'acond' NEBO entity_id obsahuje 'acond_'
    - YAML legacy entity (sensor: platform: rest/template, rest: blok,
      utility_meter v YAML…): zahrnuto tehdy, kdy se tranzitivně dotýká
      acond rozsahu (viz `_select_yaml_in_acond_scope`)
    - automation/script/scene: repr(config) obsahuje 'acond_'
    - helpers: jen ty, na které odkazuje některá z filtrovaných automatizací
      (tranzitivně přes jeden krok – neřešíme helper odkazující na helper)
    - devices: jen ty, které mají alespoň jednu acond entitu
    - areas: jen ty, na které odkazuje alespoň jedno z filtrovaných zařízení
      nebo filtrovaných entit
    - config_entries: všechny pro doménu acond (už jsou filtrované ze scanu)
    - versions, integration_log: zachovat beze změny
    """
    acond_entities = [
        e for e in snapshot.get("entities", [])
        if e.get("platform") == DOMAIN or _ACOND_PREFIX in e.get("entity_id", "")
    ]
    acond_entity_ids = {e["entity_id"] for e in acond_entities}

    filtered_automations = _filter_referencing_items(snapshot.get("automations", []))
    filtered_scripts = _filter_referencing_items(snapshot.get("scripts", []))
    filtered_scenes = _filter_referencing_items(snapshot.get("scenes", []))

    # YAML legacy entity – tranzitivní výběr přes acond rozsah
    yaml_in_scope = _select_yaml_in_acond_scope(
        snapshot,
        acond_entities,
        filtered_automations,
        filtered_scripts,
        filtered_scenes,
    )
    yaml_total = sum(
        1 for e in snapshot.get("entities", []) if e.get("source") == "yaml"
    )
    # Zařadíme za acond entity – ať je v markdownu vidět, že navazují
    acond_entities_with_yaml = acond_entities + yaml_in_scope

    # Tranzitivní reference na pomocníky z filtrovaných automatizací/skriptů/scén
    referenced_helper_ids = _collect_helper_references(
        filtered_automations + filtered_scripts + filtered_scenes
    )

    filtered_helpers: dict[str, list[dict]] = {}
    for domain, items in snapshot.get("helpers", {}).items():
        kept = [h for h in items if h.get("entity_id") in referenced_helper_ids]
        if kept:
            filtered_helpers[domain] = kept

    # Devices – ty, co obsahují alespoň jednu acond entitu (ne YAML – ty
    # nemají device_id)
    device_ids_with_acond = {e.get("device_id") for e in acond_entities if e.get("device_id")}
    filtered_devices = [
        d for d in snapshot.get("devices", [])
        if d.get("device_id") in device_ids_with_acond
    ]

    # Areas – z acond entit + acond devices
    area_ids = {e.get("area_id") for e in acond_entities if e.get("area_id")}
    area_ids.update(d.get("area_id") for d in filtered_devices if d.get("area_id"))
    filtered_areas = [
        a for a in snapshot.get("areas", []) if a.get("area_id") in area_ids
    ]

    return {
        "generated_at": snapshot.get("generated_at"),
        "mode": "acond",
        "versions": snapshot.get("versions", {}),
        "system_info": snapshot.get("system_info", {}),
        "config_entries": snapshot.get("config_entries", []),  # už je pro doménu acond
        "config_entries_health": snapshot.get("config_entries_health", []),
        "repairs_issues": snapshot.get("repairs_issues", []),
        "areas": filtered_areas,
        "devices": filtered_devices,
        "entities": acond_entities_with_yaml,
        "automations": filtered_automations,
        "scripts": filtered_scripts,
        "scenes": filtered_scenes,
        "helpers": filtered_helpers,
        "integration_log": snapshot.get("integration_log", []),
        "recent_errors": snapshot.get("recent_errors", []),
        "stats": {
            "total_entities_in_ha": len(snapshot.get("entities", [])),
            "acond_entities": len(acond_entities),
            "yaml_legacy_in_scope": len(yaml_in_scope),
            "yaml_legacy_total": yaml_total,
            "filtered_automations": len(filtered_automations),
            "filtered_scripts": len(filtered_scripts),
            "filtered_scenes": len(filtered_scenes),
            "referenced_helpers": sum(len(v) for v in filtered_helpers.values()),
            "active_issues": len(snapshot.get("repairs_issues", [])),
            "recent_errors_count": len(snapshot.get("recent_errors", [])),
        },
    }


def mark_as_full(snapshot: dict) -> dict:
    """Přidá do snapshotu metadata pro full export. Neprovádí žádný filtr."""
    full = dict(snapshot)
    full["mode"] = "full"
    full["stats"] = {
        "entities": len(snapshot.get("entities", [])),
        "devices": len(snapshot.get("devices", [])),
        "automations": len(snapshot.get("automations", [])),
        "scripts": len(snapshot.get("scripts", [])),
        "scenes": len(snapshot.get("scenes", [])),
        "helpers": sum(len(v) for v in snapshot.get("helpers", {}).values()),
        "active_issues": len(snapshot.get("repairs_issues", [])),
        "recent_errors_count": len(snapshot.get("recent_errors", [])),
        "config_entries_total": len(snapshot.get("config_entries_health", [])),
    }
    return full


# ===========================================================================
# HLAVNÍ API – buduje dict snapshot
# ===========================================================================

async def build_context(hass: HomeAssistant, mode: str) -> dict:
    """Vytvoří redigovaný, filtrovaný snapshot připravený pro serializaci.

    mode: "acond" nebo "full"
    """
    if mode not in ("acond", "full"):
        raise ValueError(f"Neznámý mode: {mode!r}, očekávám 'acond' nebo 'full'")

    raw = await scan_home_assistant(hass)
    redacted = redact_secrets(raw)

    if mode == "acond":
        return filter_acond_only(redacted)
    return mark_as_full(redacted)


def output_dir(hass: HomeAssistant) -> Path:
    """Cesta k výstupní složce, vytvoří ji pokud neexistuje."""
    path = Path(hass.config.path(_OUTPUT_SUBDIR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_filename(mode: str) -> str:
    """Název výstupního souboru: acond_only_YYYYMMDD_HHMMSS.md nebo full_."""
    prefix = "acond_only" if mode == "acond" else "full"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.md"


# ===========================================================================
# DÁVKA B – FORMÁTOVAČ MARKDOWN
# ===========================================================================

def format_as_markdown(snapshot: dict) -> str:
    """Převede snapshot z `build_context()` na čitelný markdown.

    Očekávané klíče (defenzivní – chybějící klíč přeskočí sekci):
    generated_at, mode, versions, system_info, stats, config_entries,
    config_entries_health, repairs_issues, integration_log, recent_errors,
    areas, devices, entities, automations, scripts, scenes, helpers.
    """
    mode = snapshot.get("mode", "?")
    generated_at = snapshot.get("generated_at", "?")
    versions = snapshot.get("versions") or {}
    stats = snapshot.get("stats") or {}

    lines: list[str] = []

    # ----- Hlavička + bezpečnostní varování -----
    if mode == "acond":
        title = "Acond AI kontext – pouze acond entity"
        scope = "Filtrováno na entity, automatizace, skripty a zařízení integrace Acond."
    elif mode == "full":
        title = "Acond AI kontext – kompletní HA"
        scope = "Kompletní snapshot Home Assistant napříč všemi integracemi."
    else:
        title = f"Acond AI kontext (režim {mode!r})"
        scope = ""

    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Vygenerováno:** {generated_at}")
    lines.append(f"**Režim:** `{mode}` – {scope}")
    if versions:
        lines.append(
            f"**Verze:** HA `{versions.get('home_assistant', '?')}` · "
            f"acond `{versions.get('acond_integration', '?')}` · "
            f"pymodbus `{versions.get('pymodbus', '?')}`"
        )
    lines.append("")

    lines.append("> ⚠️ **Před odesláním do AI / na fórum si soubor projděte.**")
    lines.append(">")
    lines.append("> Automatická redakce nahrazuje hodnoty u klíčů obsahujících:")
    lines.append("> `password`, `token`, `api_key`, `secret`, `webhook`, "
                 "`bearer`, `authorization`, `private_key`.")
    lines.append("> Není 100% spolehlivá – zkontrolujte zejména: IP adresy, "
                 "MAC adresy, e-maily, telefony, GPS souřadnice, jména osob, "
                 "názvy sítí, URL webhooků.")
    lines.append("")

    # ----- Souhrn (stats) -----
    if stats:
        lines.append("## Souhrn")
        lines.append("")
        for k, v in stats.items():
            lines.append(f"- **{k}:** {v}")
        lines.append("")

    # ----- Systémové informace -----
    sys_info = snapshot.get("system_info") or {}
    if sys_info:
        lines.append("## Systémové informace")
        lines.append("")
        for k, v in sys_info.items():
            lines.append(f"- **{k}:** `{v}`")
        lines.append("")

    # ----- Acond config entries -----
    entries = snapshot.get("config_entries") or []
    if entries:
        lines.append(f"## Acond config entries ({len(entries)})")
        lines.append("")
        for e in entries:
            eid = (e.get("entry_id") or "?")[:8]
            lines.append(f"### `{eid}…` – {_md_escape(str(e.get('title', '?')))}")
            lines.append(f"- state: `{e.get('state')}`")
            data = e.get("data") or {}
            if data:
                lines.append("- data:")
                for dk, dv in data.items():
                    lines.append(f"  - `{dk}`: `{dv}`")
            opts = e.get("options") or {}
            if opts:
                lines.append("- options:")
                for ok, ov in opts.items():
                    lines.append(f"  - `{ok}`: `{ov}`")
            lines.append("")

    # ----- Stav všech config entries (zdravotní přehled) -----
    health = snapshot.get("config_entries_health") or []
    if health:
        lines.append(f"## Stav všech integrací ({len(health)})")
        lines.append("")

        # Zvýrazni problémové integrace nahoře
        problems = [
            h for h in health
            if h.get("_problem")
            or "error" in str(h.get("state", "")).lower()
            or "failed" in str(h.get("state", "")).lower()
        ]
        if problems:
            lines.append(f"### ⚠️ Integrace v chybovém stavu ({len(problems)})")
            lines.append("")
            for h in problems:
                domain = h.get("domain", "?")
                title_ = _md_escape(str(h.get("title", "?")))
                state = h.get("state", "?")
                reason = _md_escape(str(h.get("reason") or ""))
                lines.append(
                    f"- **`{domain}`** ({title_}): `{state}`"
                    + (f" – {reason}" if reason else "")
                )
            lines.append("")

        lines.append("### Všechny integrace")
        lines.append("")
        lines.append("| Doména | Title | Stav | Disabled by | Source |")
        lines.append("|--------|-------|------|-------------|--------|")
        for h in health:
            domain = h.get("domain", "?")
            title_ = _md_escape(str(h.get("title", "?")))
            state = h.get("state", "?")
            disabled = h.get("disabled_by") or "—"
            source = h.get("source", "?")
            lines.append(
                f"| `{domain}` | {title_} | `{state}` | {disabled} | `{source}` |"
            )
        lines.append("")

    # ----- Repairs / Issues -----
    repairs = snapshot.get("repairs_issues") or []
    lines.append(f"## Repairs & Issues ({len(repairs)})")
    lines.append("")
    if repairs:
        for issue in repairs:
            if "_note" in issue:
                lines.append(f"_{issue['_note']}_")
                lines.append("")
                continue
            if "_error" in issue:
                lines.append(f"_Chyba: {issue['_error']}_")
                lines.append("")
                continue
            domain = issue.get("domain", "?")
            issue_id = issue.get("issue_id", "?")
            severity = issue.get("severity", "?")
            active = issue.get("active", True)
            tag = "**[active]**" if active else "_[ignored]_"
            lines.append(f"### `{domain}` / `{issue_id}` – {severity} {tag}")
            tk = issue.get("translation_key")
            if tk:
                lines.append(f"- translation_key: `{tk}`")
            placeholders = issue.get("translation_placeholders") or {}
            if placeholders:
                lines.append(f"- placeholders: `{placeholders}`")
            learn_more = issue.get("learn_more_url")
            if learn_more:
                lines.append(f"- learn more: <{learn_more}>")
            lines.append("")
    else:
        lines.append("_Žádné aktivní repair issues._")
        lines.append("")

    # ----- Logy -----
    integration_log = snapshot.get("integration_log") or []
    recent_errors = snapshot.get("recent_errors") or []

    lines.append("## Logy")
    lines.append("")

    lines.append(f"### Integration log – Acond (posledních {len(integration_log)} řádků)")
    lines.append("")
    if integration_log:
        lines.append("```")
        for line in integration_log:
            lines.append(str(line).rstrip())
        lines.append("```")
    else:
        lines.append("_Prázdný._")
    lines.append("")

    lines.append(f"### Globální WARNING + ERROR (posledních {len(recent_errors)} řádků)")
    lines.append("")
    if recent_errors:
        lines.append("```")
        for line in recent_errors:
            lines.append(str(line).rstrip())
        lines.append("```")
    else:
        lines.append("_Žádné WARNING/ERROR zprávy v paměti._")
    lines.append("")

    # ----- Areas -----
    areas = snapshot.get("areas") or []
    if areas:
        lines.append(f"## Oblasti / areas ({len(areas)})")
        lines.append("")
        for a in areas:
            aid = a.get("area_id", "?")
            name = _md_escape(str(a.get("name", "?")))
            icon = a.get("icon")
            icon_str = f" `{icon}`" if icon else ""
            lines.append(f"- `{aid}` – {name}{icon_str}")
        lines.append("")

    # ----- Devices -----
    devices = snapshot.get("devices") or []
    if devices:
        lines.append(f"## Zařízení ({len(devices)})")
        lines.append("")
        lines.append("| ID | Název | Výrobce | Model | SW | Area | Disabled |")
        lines.append("|----|-------|---------|-------|----|------|----------|")
        for d in devices:
            did = (d.get("device_id") or "?")[:8]
            name = _md_escape(str(d.get("name") or "?"))
            mfr = _md_escape(str(d.get("manufacturer") or "—"))
            model = _md_escape(str(d.get("model") or "—"))
            sw = _md_escape(str(d.get("sw_version") or "—"))
            area = d.get("area_id") or "—"
            dis = "ano" if d.get("disabled") else ""
            lines.append(
                f"| `{did}…` | {name} | {mfr} | {model} | {sw} | `{area}` | {dis} |"
            )
        lines.append("")

    # ----- Entities -----
    entities = snapshot.get("entities") or []
    if entities:
        yaml_count = sum(1 for e in entities if e.get("source") == "yaml")
        if yaml_count:
            lines.append(
                f"## Entity ({len(entities)} – z toho {yaml_count} legacy YAML)"
            )
        else:
            lines.append(f"## Entity ({len(entities)})")
        lines.append("")
        lines.append(
            "| Entity ID | Stav | Friendly name | Source | Platforma | Disabled | Hidden | Area |"
        )
        lines.append(
            "|-----------|------|---------------|--------|-----------|----------|--------|------|"
        )
        for e in entities:
            eid = e.get("entity_id", "?")
            state = _truncate(str(e.get("state") if e.get("state") is not None else "—"), 24)
            name = _md_escape(str(e.get("name") or ""))
            source = e.get("source") or "registry"
            platform = e.get("platform", "?")
            dis = "ano" if e.get("disabled") else ""
            hid = "ano" if e.get("hidden") else ""
            area = e.get("area_id") or "—"
            lines.append(
                f"| `{eid}` | `{state}` | {name} | `{source}` | `{platform}` | {dis} | {hid} | `{area}` |"
            )
        lines.append("")

    # ----- Automations / Scripts / Scenes -----
    for section_key, section_title in (
        ("automations", "Automatizace"),
        ("scripts", "Skripty"),
        ("scenes", "Scény"),
    ):
        items = snapshot.get(section_key) or []
        if not items:
            continue
        lines.append(f"## {section_title} ({len(items)})")
        lines.append("")
        for item in items:
            ident = item.get("entity_id") or "?"
            label = _md_escape(str(item.get("name") or ident))
            lines.append(f"### `{ident}` – {label}")
            state = item.get("state")
            if state is not None:
                lines.append(f"- state: `{state}`")
            lines.append("")
            cfg = item.get("config")
            if cfg is not None:
                yaml_text = _safe_yaml_dump(cfg)
                if len(yaml_text) > _MAX_YAML_BLOCK_BYTES:
                    original_len = len(yaml_text)
                    yaml_text = (
                        yaml_text[:_MAX_YAML_BLOCK_BYTES]
                        + f"\n# ... [zkráceno – původní délka {original_len} B]"
                    )
                lines.append("```yaml")
                lines.append(yaml_text.rstrip())
                lines.append("```")
                lines.append("")
            else:
                lines.append("_Config nedostupný._")
                lines.append("")

    # ----- Helpers (dict podle domény) -----
    helpers = snapshot.get("helpers") or {}
    if helpers:
        total = sum(len(v) for v in helpers.values())
        lines.append(f"## Pomocné entity – helpers ({total})")
        lines.append("")
        for domain, items in helpers.items():
            lines.append(f"### `{domain}` ({len(items)})")
            lines.append("")
            lines.append("| Entity ID | Stav | Friendly name |")
            lines.append("|-----------|------|---------------|")
            for h in items:
                eid = h.get("entity_id", "?")
                state = _truncate(
                    str(h.get("state") if h.get("state") is not None else "—"), 24
                )
                name = _md_escape(str(h.get("name") or ""))
                lines.append(f"| `{eid}` | `{state}` | {name} |")
            lines.append("")

    # ----- Patička -----
    lines.append("---")
    lines.append("")
    lines.append("_Vygenerováno integrací **Acond Heat Pump** pro účely diagnostiky "
                 "ve spolupráci s AI asistentem (Claude / ChatGPT)._")
    lines.append("")

    return "\n".join(lines)


def _md_escape(text: str) -> str:
    """Escape pipe a newline ve string hodnotách – kvůli markdown tabulkám."""
    return text.replace("|", "\\|").replace("\n", " ")


def _truncate(text: str, max_len: int) -> str:
    """Zkrátí dlouhé hodnoty s elipsou."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _safe_yaml_dump(obj: Any) -> str:
    """Pokus o YAML dump, fallback na repr() pokud yaml není k dispozici."""
    try:
        import yaml as yaml_mod
        return yaml_mod.safe_dump(
            obj,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    except Exception:  # noqa: BLE001 – chceme tolerantní fallback
        return repr(obj)


# ===========================================================================
# DÁVKA B – ORCHESTRÁTOR PRO BUTTON ENTITY
# ===========================================================================

async def async_export(hass: HomeAssistant, mode: str) -> str:
    """Hlavní entry point pro AI kontext export tlačítka v UI.

    Workflow:
        1) build_context(hass, mode) – scan + redact + filter
        2) format_as_markdown(snapshot) – text souboru
        3) zápis do souboru přes executor
        4) persistent_notification s download linkem

    Args:
        hass: HomeAssistant instance.
        mode: "acond" (jen acond entity) nebo "full" (celé HA).

    Returns:
        Absolutní cesta k vytvořenému souboru.

    Raises:
        ValueError: pokud mode není "acond" / "full".
    """
    if mode not in ("acond", "full"):
        raise ValueError(f"Neznámý mode: {mode!r}, očekávám 'acond' nebo 'full'")

    _LOGGER.info("Acond ai_context: spouštím export (mode=%s)", mode)

    # 1) scan + redact + filter
    snapshot = await build_context(hass, mode)

    # 2) format
    md_text = format_as_markdown(snapshot)

    # 3) write – s BOM, aby prohlížeče detekovaly UTF-8 i bez charset
    #    hlavičky (HA serveruje /local/ obsah s MIME `text/markdown` bez
    #    charsetu, takže Chrome/Firefox by jinak zobrazil rozsypanou češtinu).
    #    BOM = `\ufeff` na začátku UTF-8 souboru. Při kopírování do AI
    #    AI ho ignoruje (je to neviditelný řídicí znak).
    filename = build_filename(mode)
    md_with_bom = "\ufeff" + md_text

    def _write_sync() -> Path:
        out_dir = output_dir(hass)
        target = out_dir / filename
        target.write_text(md_with_bom, encoding="utf-8")
        return target

    filepath = await hass.async_add_executor_job(_write_sync)
    size_bytes = len(md_with_bom.encode("utf-8"))
    _LOGGER.info(
        "Acond ai_context: vytvořen %s (%d B, %d řádků)",
        filepath,
        size_bytes,
        md_text.count("\n"),
    )

    # 4) notification
    _async_send_notification(hass, mode, filename, size_bytes)

    return str(filepath)


def _async_send_notification(
    hass: HomeAssistant, mode: str, filename: str, size_bytes: int
) -> None:
    """Pošle persistent_notification s odkazem na stažení exportu.

    HTTP view AcondAIContextDownloadView je registrovaná v __init__.py
    a vrací soubor s `Content-Disposition: attachment`, takže kliknutí
    nabídne stažení (ne zobrazení v prohlížeči).
    """
    from homeassistant.components import persistent_notification

    url = download_url(hass, filename)
    size_kb = size_bytes / 1024

    if mode == "acond":
        title = "🤖 Acond AI kontext – jen acond entity"
        scope_note = "Pouze entity, automatizace a zařízení integrace Acond."
    else:
        title = "🤖 Acond AI kontext – kompletní HA"
        scope_note = "Celá HA konfigurace (acond + všechny ostatní integrace)."

    # HTML <a target="_blank"> místo markdown linku –
    # 1) Markdown link `[text](url)` zachytává frontend HA a v některých
    #    klientech (HA Companion app) vůbec nereaguje.
    # 2) HTML link s target="_blank" otevře externí prohlížeč i v app
    #    webview a v desktop prohlížeči se chová stejně.
    # 3) Druhý prostý URL pod ním je fallback pro klienty, kde sanitizér
    #    HTML stripuje – uživatel ho může zkopírovat ručně.
    message = (
        f"**Soubor vytvořen:** `{filename}` ({size_kb:.1f} kB)\n\n"
        f'### <a href="{url}" target="_blank" rel="noopener">📥 Stáhnout export</a>\n\n'
        f"_Pokud klik nereaguje (např. v mobilní HA aplikaci), zkopíruj URL "
        f"a otevři ji v prohlížeči:_\n\n"
        f"`{url}`\n\n"
        f"_{scope_note}_\n\n"
        f"⚠️ **Před odesláním do AI nebo na fórum zkontroluj obsah** – "
        f"automatická redakce zachytí běžné secrets, ale není 100% spolehlivá. "
        f"Pozor zejména na IP adresy, e-maily, GPS, jména a názvy sítí."
    )

    persistent_notification.async_create(
        hass,
        message=message,
        title=title,
        notification_id=f"acond_ai_context_{mode}",
    )


# ===========================================================================
# Stažení souboru – přes /local/ (HA serveruje /config/www bez autorizace).
# HTTP view zde není – staticky obsluhuje frontend HA. Není třeba registrovat
# v __init__.py.
# ===========================================================================


def download_url(hass: HomeAssistant, filename: str) -> str:
    """Plná URL pro download odkaz v persistent_notification.

    Použití plné URL (s protokolem) je důležité – HA frontend
    interpretuje relativní markdown linky jako interní Lovelace
    navigaci, takže klik nepustí na backend a místo toho přepne
    do výchozího dashboardu (Přehled).

    Endpoint `/local/...` (= obsah složky `/config/www/`) je
    serverován bez autorizace, takže klik v notifikaci spolehlivě
    stáhne soubor i v novém tabu / mobilní app, kde session cookie
    nemusí být dostupná.

    `get_url()` vrátí best-effort URL: zkusí internal_url,
    external_url, a pokud žádný není nastavený, odvodí URL
    z aktivního HA requestu (hostname + port).
    """
    from homeassistant.helpers.network import (
        NoURLAvailableError,
        get_url,
    )

    try:
        base = get_url(hass, prefer_external=False, allow_internal=True)
    except NoURLAvailableError:
        # Fallback – relativní URL (frontend ji nejspíš zachytí jako
        # SPA navigaci, ale aspoň URL existuje a uživatel ji může
        # ručně otevřít v jiném tabu).
        return f"{_PUBLIC_URL_PREFIX}/{filename}"

    return f"{base.rstrip('/')}{_PUBLIC_URL_PREFIX}/{filename}"
