"""Automatická registrace Acond Lovelace dashboardu.

Dashboard se zobrazí jako postranní panel HA po instalaci integrace.
Odpojení integrace panel opět odstraní.

SKLÁDÁNÍ (v0.3.0):
Acond je „skladač" dashboardu. Při startu vezme ručně udržovaný základ
(`acond_dashboard.yaml` – jen vestavěné Lovelace karty, čistý pro HACS),
na konec přilepí okna add-onů (Regulace/MaR, později FVE…) a zapíše
výsledek do `acond_dashboard.generated.yaml`, který pak zaregistruje.

- Když je add-on přítomen (soubor jeho příspěvku existuje) → natáhne jeho
  view(s) a vloží je jako poslední záložky. Add-on smí přispět jedním nebo
  více okny – Acond vezme seznam tak, jak přijde.
- Když add-on chybí → zobrazí teaser (markdown s odkazem na repozitář).
  To je zároveň „reklama" na MaR; Acond o add-onu zná jen jméno a odkaz,
  ne jeho obsah.

Detekce je založená čistě na EXISTENCI SOUBORU (ne na `hass.config.components`),
takže je odolná na pořadí setupu. Změna v add-onu se projeví po restartu HA
(dashboard se generuje při každém startu) – ne živě.

Skládání je best-effort: když cokoli selže (nečitelný základ, nezapsatelný
výstup…), zaregistruje se čistý základ a integrace běží dál normálně.

Implementace používá `LovelaceYAML` z interního Lovelace API – pokud by se
v budoucí verzi HA změnilo, registrace selže a uživatel dostane do logu
instrukce pro ruční přidání (integrace samotná funguje dál normálně).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "acond-dashboard"
DASHBOARD_TITLE = "Acond TČ"
DASHBOARD_ICON = "mdi:heat-pump"

# Ručně udržovaný základ (ships v repu, jen vestavěné karty) a runtime výstup.
BASE_YAML_FILENAME = "acond_dashboard.yaml"
GENERATED_YAML_FILENAME = "acond_dashboard.generated.yaml"

# --- Registr oficiálních add-onů -------------------------------------------
# Acond zná jen jméno, ikonu a odkaz (čistý markdown teaser). Obsah okna
# dodává add-on sám přes svůj soubor příspěvku. Nový add-on (FVE…) = nová
# položka zde, žádná další změna v Acondu.
#
# `contribution_files`: cesty relativně ke konfiguraci HA (/config/...).
# Zkouší se v pořadí; první existující a čitelný vyhraje. Akceptujeme:
#   - seznam view dictů        (preferováno: views.yaml)
#   - {"views": [...]}         (celý dashboard dict)
#   - jeden view dict          (legacy: view.yaml)
ADDONS: list[dict] = [
    {
        "key": "regulator",
        "title": "Regulace",
        "path": "regulace",
        "icon": "mdi:chart-bell-curve-cumulative",
        # TODO: doplnit reálnou URL repozitáře MaR
        "repo_url": "https://github.com/pavorlechre/acond_regulator",
        "teaser": (
            "Toto okno ožije po instalaci integrace **Acond Regulator (MaR)** – "
            "ekvitermní regulace, předpovědi počasí a grafy. Bez ní Acond běží "
            "normálně dál."
        ),
        "contribution_files": [
            "custom_components/acond_regulator/dashboard/views.yaml",
            "custom_components/acond_regulator/dashboard/view.yaml",
        ],
    },
]

# Jak by si měl uživatel dashboard přidat ručně, kdyby automatická
# registrace selhala
_MANUAL_INSTRUCTIONS = (
    "Dashboard můžete přidat ručně: Nastavení → Dashboardy → "
    "Přidat (+) → 'Z YAML souboru', cesta: "
    "custom_components/acond/lovelace/acond_dashboard.yaml"
)


def _normalize_views(data) -> list[dict]:
    """Z příspěvku add-onu udělej seznam view dictů.

    Akceptuje seznam view dictů, dashboard dict s klíčem `views`,
    nebo jeden samostatný view dict.
    """
    if isinstance(data, list):
        return [v for v in data if isinstance(v, dict)]
    if isinstance(data, dict):
        views = data.get("views")
        if isinstance(views, list):
            return [v for v in views if isinstance(v, dict)]
        # jeden view dict (má aspoň cards/path/title)
        if any(k in data for k in ("cards", "path", "title")):
            return [data]
    return []


def _teaser_view(addon: dict) -> dict:
    """Náhradní okno (reklama) pro nenainstalovaný add-on – čistý markdown."""
    return {
        "title": addon["title"],
        "path": addon["path"],
        "icon": addon["icon"],
        "cards": [
            {
                "type": "markdown",
                "content": (
                    f"## {addon['title']}\n\n"
                    f"{addon['teaser']}\n\n"
                    f"Repozitář: [{addon['repo_url']}]({addon['repo_url']})"
                ),
            }
        ],
    }


async def _addon_views(hass: HomeAssistant, addon: dict) -> list[dict]:
    """Vrať okna add-onu (jeho příspěvek), nebo teaser, když není přítomen."""
    from homeassistant.util.yaml import load_yaml

    for rel in addon["contribution_files"]:
        path = hass.config.path(rel)
        if not os.path.exists(path):
            continue
        try:
            data = await hass.async_add_executor_job(load_yaml, path)
        except Exception as err:  # nečitelný/rozbitý soubor → teaser
            _LOGGER.warning(
                "Acond: okno '%s' – soubor %s nečitelný (%s), zobrazuji teaser",
                addon["title"],
                path,
                err,
            )
            break
        views = _normalize_views(data)
        if views:
            _LOGGER.info(
                "Acond: okno '%s' načteno z %s (%d view)",
                addon["title"],
                path,
                len(views),
            )
            return views
        _LOGGER.warning(
            "Acond: okno '%s' – soubor %s neobsahuje view, zobrazuji teaser",
            addon["title"],
            path,
        )
        break

    return [_teaser_view(addon)]


def _to_plain(obj):
    """Převeď strukturu z HA YAML loaderu na čisté Python typy.

    `homeassistant.util.yaml.load_yaml` nevrací čisté str/dict/list, ale své
    podtřídy (NodeStrClass, NodeDictClass, NodeListClass) nesoucí info o řádku.
    yaml.safe_dump je neumí serializovat ('cannot represent an object'), proto
    je tu rozbalíme na plain dict/list/str. Vedlejší efekt: rozbití sdílených
    referencí, takže PyYAML negeneruje &anchory/*aliasy.
    """
    if isinstance(obj, dict):
        return {_to_plain(k): _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    if isinstance(obj, bool):          # bool je podtřída int – nejdřív
        return bool(obj)
    if isinstance(obj, str):           # strhne NodeStrClass na čistý str
        return str(obj)
    if obj is None or isinstance(obj, (int, float)):
        return obj
    # cokoli exotického (Secret, Input…) → string fallback
    return str(obj)


def _write_yaml(path: Path, data: dict) -> None:
    """Zapiš dict jako YAML (blokující I/O – volat přes executor)."""
    import yaml

    text = yaml.safe_dump(
        _to_plain(data),          # rozbal HA Node* typy na plain Python
        allow_unicode=True,       # zachovej českou diakritiku a emoji
        sort_keys=False,          # zachovej pořadí (title, views, …)
        default_flow_style=False,
    )
    Path(path).write_text(text, encoding="utf-8")


async def _compose_dashboard(
    hass: HomeAssistant, base_path: Path, generated_path: Path
) -> Path:
    """Slož základ + okna add-onů a zapiš generovaný soubor.

    Vrací cestu k souboru, který se má registrovat. Při jakékoli chybě
    vrací `base_path` (čistá kostra), aby dashboard vždy fungoval.
    """
    from homeassistant.util.yaml import load_yaml

    try:
        config = await hass.async_add_executor_job(load_yaml, str(base_path))
    except Exception as err:
        _LOGGER.warning(
            "Acond: nelze načíst základní dashboard (%s) – skládání přeskočeno",
            err,
        )
        return base_path

    if not isinstance(config, dict):
        _LOGGER.warning(
            "Acond: základní dashboard nemá očekávanou strukturu – "
            "skládání přeskočeno"
        )
        return base_path

    views = config.get("views")
    if not isinstance(views, list):
        views = []
        config["views"] = views

    # Přilep okna add-onů na konec (každý add-on: příspěvek, nebo teaser).
    for addon in ADDONS:
        try:
            views.extend(await _addon_views(hass, addon))
        except Exception as err:  # jeden rozbitý add-on neshodí zbytek
            _LOGGER.warning(
                "Acond: okno add-onu '%s' selhalo (%s) – vynecháno",
                addon.get("title", addon.get("key", "?")),
                err,
            )

    try:
        await hass.async_add_executor_job(_write_yaml, generated_path, config)
    except Exception as err:
        _LOGGER.warning(
            "Acond: nelze zapsat generovaný dashboard (%s) – použiji čistou kostru",
            err,
        )
        return base_path

    _LOGGER.info(
        "Acond: dashboard složen do %s (%d view celkem)",
        generated_path.name,
        len(views),
    )
    return generated_path


async def async_register_dashboard(hass: HomeAssistant) -> None:
    """Registruj Acond dashboard jako postranní panel."""
    lovelace_dir = Path(__file__).parent / "lovelace"
    base_path = lovelace_dir / BASE_YAML_FILENAME

    if not base_path.is_file():
        _LOGGER.warning(
            "Acond: dashboard YAML nenalezen na %s – dashboard nebude registrován",
            base_path,
        )
        return

    # Slož základ + okna add-onů. Když cokoli selže, vrátí se base_path.
    generated_path = lovelace_dir / GENERATED_YAML_FILENAME
    dashboard_path = await _compose_dashboard(hass, base_path, generated_path)

    # 1) Přidej dashboard do Lovelace storage (pokud tam ještě není).
    #    Import je uvnitř funkce – v případě změny interního API jen selže
    #    registrace, integrace samotná poběží dál.
    try:
        from homeassistant.components.lovelace.dashboard import LovelaceYAML
    except ImportError as err:
        _LOGGER.warning(
            "Acond: nepodporovaná verze Lovelace API (%s). %s",
            err,
            _MANUAL_INSTRUCTIONS,
        )
        return

    lovelace_data = hass.data.get("lovelace")
    if lovelace_data is None:
        _LOGGER.warning(
            "Acond: Lovelace není inicializován. %s", _MANUAL_INSTRUCTIONS
        )
        return

    # `lovelace_data.dashboards` je dict url_path → LovelaceConfig v novějších HA,
    # ve starších verzích atribut `dashboards` na objektu LovelaceData.
    dashboards = getattr(lovelace_data, "dashboards", None)
    if dashboards is None and isinstance(lovelace_data, dict):
        dashboards = lovelace_data.get("dashboards")

    if dashboards is None:
        _LOGGER.warning(
            "Acond: nelze najít Lovelace dashboards kolekci. %s",
            _MANUAL_INSTRUCTIONS,
        )
        return

    if DASHBOARD_URL_PATH in dashboards:
        _LOGGER.debug("Acond: dashboard %s už je registrován", DASHBOARD_URL_PATH)
        return

    dashboard_config = {
        "mode": "yaml",
        "filename": str(dashboard_path),
        "title": DASHBOARD_TITLE,
        "icon": DASHBOARD_ICON,
        "show_in_sidebar": True,
        "require_admin": False,
    }

    try:
        dashboards[DASHBOARD_URL_PATH] = LovelaceYAML(
            hass, DASHBOARD_URL_PATH, dashboard_config
        )
    except Exception as err:  # širší catch – API se může měnit
        _LOGGER.warning(
            "Acond: nelze vytvořit Lovelace dashboard (%s). %s",
            err,
            _MANUAL_INSTRUCTIONS,
        )
        return

    # 2) Zaregistruj postranní panel – bez toho by dashboard v HA menu nebyl.
    try:
        frontend.async_register_built_in_panel(
            hass,
            component_name="lovelace",
            sidebar_title=DASHBOARD_TITLE,
            sidebar_icon=DASHBOARD_ICON,
            frontend_url_path=DASHBOARD_URL_PATH,
            config={"mode": "yaml"},
            require_admin=False,
            update=False,
        )
        _LOGGER.info(
            "Acond: dashboard registrován jako postranní panel '%s' (URL /%s)",
            DASHBOARD_TITLE,
            DASHBOARD_URL_PATH,
        )
    except ValueError:
        # Panel se stejným URL už existuje – není třeba řešit
        _LOGGER.debug("Acond: panel %s už existuje", DASHBOARD_URL_PATH)
    except Exception as err:
        _LOGGER.error(
            "Acond: nelze zaregistrovat panel (%s). %s", err, _MANUAL_INSTRUCTIONS
        )


async def async_unregister_dashboard(hass: HomeAssistant) -> None:
    """Odstraň Acond dashboard z postranního panelu i z Lovelace."""
    # Odeber postranní panel
    try:
        frontend.async_remove_panel(hass, DASHBOARD_URL_PATH)
    except Exception as err:  # panel nemusí existovat – nevadí
        _LOGGER.debug("Acond: odebrání panelu selhalo: %s", err)

    # Odeber dashboard z Lovelace kolekce
    lovelace_data = hass.data.get("lovelace")
    if lovelace_data is not None:
        dashboards = getattr(lovelace_data, "dashboards", None)
        if dashboards is None and isinstance(lovelace_data, dict):
            dashboards = lovelace_data.get("dashboards")

        if dashboards is not None and DASHBOARD_URL_PATH in dashboards:
            dashboards.pop(DASHBOARD_URL_PATH, None)
            _LOGGER.info("Acond: dashboard %s odstraněn", DASHBOARD_URL_PATH)

    # Úklid generovaného souboru (best-effort – při dalším startu se vytvoří znovu)
    generated_path = Path(__file__).parent / "lovelace" / GENERATED_YAML_FILENAME
    try:
        if generated_path.exists():
            await hass.async_add_executor_job(os.remove, str(generated_path))
    except Exception as err:
        _LOGGER.debug("Acond: úklid generovaného dashboardu selhal: %s", err)
