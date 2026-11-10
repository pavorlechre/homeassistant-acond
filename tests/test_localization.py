"""Localization and public-interface regression tests; no pump is required."""

import inspect
import json
import logging
import re
from copy import deepcopy
from pathlib import Path
from string import Formatter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from homeassistant.helpers.template import Template
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.acond import (
    ai_context,
    binary_sensor,
    button,
    number,
    select,
    sensor,
    switch,
)
from custom_components.acond.const import (
    BUTTON_DEFINITIONS,
    DRIVER_ERROR_CODES,
    ERROR_CODES,
    HP_MODES,
    NUMBER_DEFINITIONS,
    REG_TYPES,
    SELECT_DEFINITIONS,
    SENSOR_DEFINITIONS,
    SWITCH_DEFINITIONS,
    THERMAL_POWER,
)
from custom_components.acond.frontend_readability import async_register_readability
from custom_components.acond.localization import (
    async_load_localization,
    localize_dashboard,
    localized_state,
    text,
)
from custom_components.acond.lovelace_dashboard import (
    ADDONS,
    _compose_dashboard,
    _teaser_view,
)

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "acond"


def walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def make_entities(hass, series):
    coordinator_options = (
        {"config_entry": None}
        if "config_entry" in inspect.signature(DataUpdateCoordinator).parameters
        else {}
    )
    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), name="offline", **coordinator_options
    )
    coordinator.data = {definition.key: 0 for definition in SENSOR_DEFINITIONS}
    coordinator.async_request_refresh = AsyncMock()
    client = SimpleNamespace(write_register=AsyncMock(return_value=True))
    args = {"entry_id": "unchanged-entry", "hp_series": series, "host": "192.0.2.1"}
    result = []
    for domain, definitions, cls, parameter in (
        ("sensor", SENSOR_DEFINITIONS, sensor.AcondSensor, "sensor_def"),
        ("number", NUMBER_DEFINITIONS, number.AcondNumber, "number_def"),
        ("switch", SWITCH_DEFINITIONS, switch.AcondSwitch, "switch_def"),
        ("select", SELECT_DEFINITIONS, select.AcondSelect, "select_def"),
        ("button", BUTTON_DEFINITIONS, button.AcondButton, "button_def"),
    ):
        for definition in definitions:
            kwargs = dict(args)
            if domain != "button":
                kwargs["coordinator"] = coordinator
            if domain != "sensor":
                kwargs["client"] = client
            kwargs[parameter] = definition
            entity = cls(**kwargs)
            result.append((domain, entity, definition))
    for register, source, names, prefix in (
        (30007, "tc_status", binary_sensor._TC_STATUS_NAMES, "tc_status_bit_"),
        (
            30045,
            "hp_component_status",
            binary_sensor._HP_COMPONENT_NAMES,
            "hp_comp_bit_",
        ),
    ):
        for bit, name in names.items():
            entity = binary_sensor.AcondBitSensor(
                coordinator=coordinator,
                register_address=register,
                register_key=source,
                bit=bit,
                key=f"{prefix}{bit}",
                name=name,
                device_class=None,
                **args,
            )
            result.append(
                (
                    "binary_sensor",
                    entity,
                    SimpleNamespace(address=register, key=f"{prefix}{bit}"),
                )
            )
    for mode in ("acond", "full"):
        entity = button.AcondAIContextButton(hass=hass, mode=mode, **args)
        result.append(
            ("button", entity, SimpleNamespace(address=None, key=f"ai_context_{mode}"))
        )
    return coordinator, client, result


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["pl", "en", "cs"])
@pytest.mark.parametrize("series", ["Grandis / Economis", "PRO"])
async def test_all_entities_keep_ids_and_have_native_ha_names(hass, language, series):
    hass.config.language = language
    await async_load_localization(hass)
    translations = await async_get_translations(hass, language, "entity", {"acond"})
    _, client, entities = make_entities(hass, series)
    assert len(entities) == 117
    assert len({entity.entity_id for _, entity, _ in entities}) == 117
    for domain, entity, definition in entities:
        entity.hass = hass
        entity.platform = SimpleNamespace(
            platform_name="acond",
            domain=domain,
            platform_translations=translations,
            component_translations={},
        )
        if hasattr(entity, "platform_data"):
            entity.platform_data = entity.platform
        suffix = (
            f"{definition.address}_{definition.key}"
            if definition.address
            else definition.key
        )
        assert entity.unique_id == f"acond_{suffix}"
        assert entity.entity_id == f"{domain}.acond_{suffix}"
        assert entity.has_entity_name
        expected = translations[
            f"component.acond.entity.{domain}.{entity.translation_key}.name"
        ]
        assert entity.name == expected
        if series == "PRO" and definition.key in {
            "comp_rpm_max",
            "comp_rpm_actual",
            "comp_capacity_max_set",
        }:
            assert entity.translation_key.endswith("_power")
            assert entity.native_unit_of_measurement == "W"
    client.write_register.assert_not_called()


@pytest.mark.asyncio
async def test_states_and_select_options_preserve_legacy_api(hass):
    await async_load_localization(hass)
    coordinator, client, entities = make_entities(hass, "Grandis / Economis")
    groups = {
        "hp_mode": HP_MODES,
        "regulation_type": REG_TYPES,
        "err_number": ERROR_CODES,
        "err_number_driver": DRIVER_ERROR_CODES,
        "thermal_power": THERMAL_POWER,
    }
    pl = json.loads((ROOT / "translations/pl.json").read_text())
    for domain, entity, definition in entities:
        entity.hass = hass
        if domain == "sensor" and definition.key in groups:
            for code, legacy_state in groups[definition.key].items():
                coordinator.data[definition.key] = code
                assert entity.native_value == legacy_state
                attrs = entity.extra_state_attributes
                assert attrs["raw_value"] == code
                assert (
                    attrs["localized_state"]
                    == pl["common"][f"state_{definition.key}_{code}"]
                )
    selector = next(entity for domain, entity, _ in entities if domain == "select")
    assert selector.options == ["AcondTherm", "Ekvitermní", "Standard"]
    for code, legacy_state in REG_TYPES.items():
        coordinator.data["regulation_type"] = code
        assert selector.current_option == legacy_state
        assert selector.extra_state_attributes["raw_value"] == code
    assert (
        localized_state(hass, "regulation_type", 999, "Neznámá regulace 999")
        == "Nieznany typ regulacji 999"
    )
    client.write_register.assert_not_called()


@pytest.mark.asyncio
async def test_select_and_number_writes_keep_original_encoding(hass):
    await async_load_localization(hass)
    _coordinator, client, entities = make_entities(hass, "Grandis / Economis")
    selector = next(entity for domain, entity, _ in entities if domain == "select")
    selector.async_write_ha_state = lambda: None
    for option, raw in [("AcondTherm", 0), ("Ekvitermní", 1), ("Standard", 2)]:
        await selector.async_select_option(option)
        client.write_register.assert_awaited_with(40007, raw)
    room = next(
        entity
        for domain, entity, definition in entities
        if domain == "number" and definition.address == 40001
    )
    room.async_write_ha_state = lambda: None
    await room.async_set_native_value(22.2)
    client.write_register.assert_awaited_with(40001, 222)
    assert room.native_value == 22.2


def test_catalog_keys_placeholders_and_safe_state_keys():
    def leaves(value, prefix=""):
        if isinstance(value, dict):
            return {
                key: item
                for k, v in value.items()
                for key, item in leaves(v, prefix + "." + k).items()
            }
        assert isinstance(value, str)
        return {prefix: value}

    catalogs = {
        lang: json.loads((ROOT / "translations" / f"{lang}.json").read_text())
        for lang in ("en", "cs", "pl")
    }
    reference = leaves(catalogs["en"])
    for language, catalog in catalogs.items():
        flat = leaves(catalog)
        assert flat.keys() == reference.keys(), language
        for key, value in flat.items():
            assert value.strip(), (language, key)
            assert {name for _, name, _, _ in Formatter().parse(value) if name} == {
                name for _, name, _, _ in Formatter().parse(reference[key]) if name
            }
        assert all(re.fullmatch(r"[a-z0-9_]+", key) for key in catalog["common"])
    assert json.loads((ROOT / "strings.json").read_text()) == catalogs["en"]


@pytest.mark.asyncio
async def test_dashboard_translation_preserves_existing_actions_ids_and_conditions(
    hass,
):
    await async_load_localization(hass)
    original = yaml.safe_load((ROOT / "lovelace/acond_dashboard.yaml").read_text())
    snapshot = deepcopy(original)
    translated = localize_dashboard(hass, original)
    assert original == snapshot
    assert translated["title"] == "Pompa ciepła Acond"
    for key in (
        "path",
        "navigation_path",
        "url_path",
        "conditions",
        "visibility",
        "entity_id",
    ):
        before = [
            node[key]
            for node in walk(original)
            if isinstance(node, dict) and key in node
        ]
        after = [
            node[key]
            for node in walk(translated)
            if isinstance(node, dict) and key in node
        ]
        if key == "entity_id":
            after = [
                item
                for item in after
                if item != "select.acond_40007_sel_regulation_type"
            ]
        assert after == before, key
    for key in ("tap_action", "hold_action"):
        before = [
            node[key]
            for node in walk(original)
            if isinstance(node, dict) and key in node
        ]
        after = [
            node[key]
            for node in walk(translated)
            if isinstance(node, dict) and key in node
        ]

        def without_confirmation(action):
            return {k: v for k, v in action.items() if k != "confirmation"}

        after = [
            without_confirmation(action)
            for action in after
            if action.get("perform_action") != "select.select_option"
        ]
        assert after == [without_confirmation(action) for action in before], key
    regulation_actions = [
        node
        for node in walk(translated)
        if isinstance(node, dict)
        and node.get("perform_action") == "select.select_option"
    ]
    assert [action["data"]["option"] for action in regulation_actions] == [
        "AcondTherm",
        "Ekvitermní",
        "Standard",
    ]
    regulation_rows = [
        node
        for node in walk(translated)
        if isinstance(node, dict)
        and node.get("type") == "buttons"
        and any(
            item.get("entity") == "select.acond_40007_sel_regulation_type"
            for item in node.get("entities", [])
            if isinstance(item, dict)
        )
    ]
    assert [len(row["entities"]) for row in regulation_rows] == [2, 1]
    # The help examples are documentation, but their executable content must
    # also remain unchanged by localization.
    before_examples = [
        part
        for node in walk(original)
        if isinstance(node, dict)
        for value in [node.get("content", "")]
        for part in value.split("```")[1::2]
    ]
    after_examples = [
        part
        for node in walk(translated)
        if isinstance(node, dict)
        for value in [node.get("content", "")]
        for part in value.split("```")[1::2]
    ]

    def executable_example(value):
        # Comments and the example's human-readable alias are presentation.
        value = re.sub(r"(?m)^\s*#.*$", "", value)
        return re.sub(r"(?m)^(\s*-?\s*alias:).*$", r"\1 LABEL", value)

    assert [executable_example(v) for v in after_examples] == [
        executable_example(v) for v in before_examples
    ]


def test_polish_dashboard_has_no_czech_prose_including_code_comments():
    catalog = json.loads((ROOT / "lovelace/translations/pl.json").read_text())
    for value in catalog.values():
        # Native API values inside non-rendered Jinja conditions are deliberate.
        display = re.sub(r"{%[\s\S]*?%}|{{[\s\S]*?}}", "", value)
        assert not re.search(
            r"[áéěíúůýčďňřšťž]|\b(?:TČ|TUV|FVE|bivalence)\b", display
        ), display


@pytest.mark.asyncio
async def test_glance_text_states_use_native_attribute_rows(hass):
    await async_load_localization(hass)
    source = {
        "type": "glance",
        "columns": 3,
        "entities": [{"entity": "sensor.acond_30014_hp_mode", "name": "Režim"}],
    }
    result = localize_dashboard(hass, source)
    assert result["type"] == "entities"
    assert result["entities"][0]["attribute"] == "localized_state"
    assert result["entities"][0]["entity"] == source["entities"][0]["entity"]
    assert source["type"] == "glance"


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["pl", "en"])
async def test_readability_registers_a_bundled_module_once_only_for_polish(language):
    from homeassistant.components import frontend

    modules = set()
    instance = SimpleNamespace(
        config=SimpleNamespace(language=language),
        data={frontend.DATA_EXTRA_MODULE_URL: modules},
        http=SimpleNamespace(async_register_static_paths=AsyncMock()),
        async_add_executor_job=AsyncMock(side_effect=lambda func, path: func(path)),
    )
    await async_register_readability(instance)
    await async_register_readability(instance)
    if language == "pl":
        instance.http.async_register_static_paths.assert_awaited_once()
        paths = instance.http.async_register_static_paths.call_args.args[0]
        assert paths[0].url_path == "/acond-localization/readability.js"
        assert Path(paths[0].path).is_file()
        assert len(modules) == 1
        assert next(iter(modules)).startswith("/acond-localization/readability.js?v=")
    else:
        instance.http.async_register_static_paths.assert_not_awaited()
        assert not modules


@pytest.mark.asyncio
async def test_readability_failure_does_not_stop_integration_setup():
    from homeassistant.components import frontend

    instance = SimpleNamespace(
        config=SimpleNamespace(language="pl"),
        data={frontend.DATA_EXTRA_MODULE_URL: set()},
        http=SimpleNamespace(
            async_register_static_paths=AsyncMock(side_effect=OSError)
        ),
        async_add_executor_job=AsyncMock(side_effect=lambda func, path: func(path)),
    )
    await async_register_readability(instance)
    assert not instance.data[frontend.DATA_EXTRA_MODULE_URL]


@pytest.mark.asyncio
async def test_dashboard_catalog_covers_every_upstream_display_string(hass):
    await async_load_localization(hass)
    source = yaml.safe_load((ROOT / "lovelace/acond_dashboard.yaml").read_text())
    catalog = json.loads((ROOT / "lovelace/translations/pl.json").read_text())
    for node in walk(source):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {
                    "title",
                    "name",
                    "heading",
                    "content",
                    "text",
                    "label",
                } and isinstance(value, str):
                    assert value in catalog, (key, value)
    assert _teaser_view(ADDONS[0])["cards"][0]["content"] in catalog


@pytest.mark.asyncio
async def test_dashboard_row_labels_are_translated_without_touching_service_data(hass):
    await async_load_localization(hass)
    source = {
        "type": "entities",
        "entities": [{"type": "section", "label": "Aktuální stav v TČ"}],
        "tap_action": {
            "action": "perform-action",
            "data": {"label": "Aktuální stav v TČ"},
        },
    }
    result = localize_dashboard(hass, source)
    assert result["entities"][0]["label"] == "Bieżący stan w pompie ciepła"
    assert result["tap_action"] == source["tap_action"]
    assert source["entities"][0]["label"] == "Aktuální stav v TČ"


@pytest.mark.asyncio
async def test_dashboard_mode_header_translates_unavailable_and_unknown(hass):
    await async_load_localization(hass)
    source = yaml.safe_load((ROOT / "lovelace/acond_dashboard.yaml").read_text())
    translated = localize_dashboard(hass, source)
    header = next(
        node["content"]
        for node in walk(translated)
        if isinstance(node, dict)
        and "state_attr('sensor.acond_30014_hp_mode', 'localized_state')"
        in node.get("content", "")
    )
    for raw, display in (("unavailable", "NIEDOSTĘPNY"), ("unknown", "NIEZNANY")):
        hass.states.async_set("sensor.acond_30014_hp_mode", raw)
        assert display in Template(header, hass).async_render()
        assert hass.states.get("sensor.acond_30014_hp_mode").state == raw


@pytest.mark.asyncio
async def test_unsupported_language_falls_back_without_rewriting_dashboard(hass):
    hass.config.language = "de"
    await async_load_localization(hass)
    original = {
        "title": "Pohled",
        "cards": [{"type": "entity", "entity": "sensor.acond_30015_regulation_type"}],
    }
    assert localize_dashboard(hass, original) is original
    assert text(hass, "export_download", "Stáhnout export") == "Download export"


@pytest.mark.asyncio
async def test_missing_message_or_bad_placeholder_has_safe_fallback(hass):
    await async_load_localization(hass)
    assert text(hass, "not_present", "fallback {code}", code=7) == "fallback 7"
    hass.data["acond_localization"]["messages"]["component.acond.common.test"] = (
        "bad {missing}"
    )
    assert text(hass, "test", "fallback {code}", code=7) == "fallback 7"


@pytest.mark.asyncio
async def test_presentation_words_inside_service_data_are_never_translated(hass):
    await async_load_localization(hass)
    config = {
        "name": "Pohled",
        "tap_action": {
            "action": "perform-action",
            "perform_action": "script.example",
            "data": {"name": "Pohled", "text": "Vypnuto"},
            "target": {"entity_id": "script.example"},
            "confirmation": {"text": "Přepnout na automatický režim?"},
        },
    }
    translated = localize_dashboard(hass, config)
    assert translated["name"] == "Podgląd"
    assert translated["tap_action"]["data"] == config["tap_action"]["data"]
    assert translated["tap_action"]["target"] == config["tap_action"]["target"]
    assert (
        translated["tap_action"]["confirmation"]["text"]
        == "Przełączyć na tryb automatyczny?"
    )


@pytest.mark.asyncio
async def test_corrupt_dashboard_catalog_keeps_standard_messages_and_base(hass):
    with patch(
        "custom_components.acond.localization._read_dashboard_catalog",
        side_effect=ValueError("bad catalog"),
    ):
        await async_load_localization(hass)
    original = {"title": "Acond TČ"}
    assert localize_dashboard(hass, original) is original
    assert text(hass, "export_download", "fallback") == "Pobierz eksport"


@pytest.mark.asyncio
async def test_compose_translates_base_without_translating_addon_slots(hass, tmp_path):
    await async_load_localization(hass)
    base = tmp_path / "base.yaml"
    output = tmp_path / "generated.yaml"
    base.write_text(
        yaml.safe_dump(
            {
                "title": "Acond TČ",
                "views": [
                    {
                        "title": "Pohled",
                        "path": "pohled",
                        "sections": [
                            {
                                "type": "grid",
                                "cards": [
                                    {
                                        "type": "markdown",
                                        "acond_slot": "pohled_stav",
                                        "content": "base",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
    )
    contribution = [
        {
            "type": "grid",
            "cards": [{"type": "markdown", "content": "MaR content stays upstream"}],
        }
    ]
    with (
        patch(
            "custom_components.acond.lovelace_dashboard._addon_views",
            AsyncMock(return_value=[{"title": "MaR native", "path": "mar"}]),
        ),
        patch(
            "custom_components.acond.lovelace_dashboard._addon_slots",
            AsyncMock(return_value={"pohled_stav": contribution}),
        ),
    ):
        assert await _compose_dashboard(hass, base, output) == output
    result = yaml.safe_load(output.read_text())
    assert result["title"] == "Pompa ciepła Acond"
    assert result["views"][0]["title"] == "Podgląd"
    assert result["views"][1]["title"] == "MaR native"
    assert (
        result["views"][0]["sections"][0]["cards"][0]["content"]
        == "MaR content stays upstream"
    )
    assert "acond_slot" not in output.read_text()


@pytest.mark.asyncio
async def test_export_notification_is_polish_without_changing_download_or_id(hass):
    await async_load_localization(hass)
    with (
        patch.object(
            ai_context,
            "download_url",
            return_value="https://example.invalid/local/acond_ai_context/test.md",
        ),
        patch(
            "homeassistant.components.persistent_notification.async_create"
        ) as notify,
    ):
        ai_context._async_send_notification(hass, "acond", "test.md", 1024)
    assert notify.call_args.kwargs["title"] == "🤖 Kontekst AI Acond — encje Acond"
    assert notify.call_args.kwargs["notification_id"] == "acond_ai_context_acond"
    message = notify.call_args.kwargs["message"]
    assert "Pobierz eksport" in message
    assert "https://example.invalid/local/acond_ai_context/test.md" in message
    assert "test.md" in message


@pytest.mark.asyncio
async def test_export_failure_notification_is_polish(hass):
    await async_load_localization(hass)
    entity = button.AcondAIContextButton(
        hass, "unchanged-entry", "Grandis / Economis", "192.0.2.1", "full"
    )
    with (
        patch.object(
            ai_context,
            "async_export",
            AsyncMock(side_effect=RuntimeError("offline test")),
        ),
        patch(
            "homeassistant.components.persistent_notification.async_create"
        ) as notify,
    ):
        await entity.async_press()
    assert notify.call_args.kwargs["title"] == "❌ Kontekst AI Acond — błąd"
    assert "offline test" in notify.call_args.kwargs["message"]
    assert notify.call_args.kwargs["notification_id"] == "acond_ai_context_error_full"


@pytest.mark.asyncio
async def test_silent_mode_display_preserves_native_minutes_and_flags(hass):
    await async_load_localization(hass)
    coordinator, _client, entities = make_entities(hass, "Grandis / Economis")
    sensors = {
        definition.key: entity
        for domain, entity, definition in entities
        if domain == "sensor"
    }
    for key, value, expected in (
        ("silent_mode_start", 1320, "22:00"),
        ("silent_mode_stop", 360, "06:00"),
        ("silent_mode_start", 2200, "Poza zakresem integracji: 2200 min"),
        ("silent_mode", 0, "Wyłączony"),
        ("silent_mode", 1, "Włączony"),
    ):
        coordinator.data[key] = value
        entity = sensors[key]
        entity.hass = hass
        assert entity.native_value == value
        assert entity.extra_state_attributes["localized_state"] == expected
    # The original diagnostic attribute remains unchanged, including its wrap.
    assert sensors["silent_mode_start"].extra_state_attributes["time"] == "12:40"


@pytest.mark.asyncio
async def test_silent_mode_dashboard_uses_readable_attributes(hass):
    await async_load_localization(hass)
    source = {
        "type": "entities",
        "entities": [
            {
                "entity": "sensor.acond_30032_silent_mode",
                "name": "Tichý provoz aktivní",
            },
            {
                "entity": "sensor.acond_30033_silent_mode_start",
                "name": "Začátek (min od 00:00)",
            },
            {
                "entity": "sensor.acond_30034_silent_mode_stop",
                "name": "Konec (min od 00:00)",
            },
        ],
    }
    translated = localize_dashboard(hass, source)
    assert [row["entity"] for row in translated["entities"]] == [
        row["entity"] for row in source["entities"]
    ]
    assert all(row["attribute"] == "localized_state" for row in translated["entities"])
    assert [row["name"] for row in translated["entities"]] == [
        "Stan trybu cichego",
        "Godzina rozpoczęcia",
        "Godzina zakończenia",
    ]


@pytest.mark.asyncio
async def test_silent_mode_control_keeps_minute_range_and_encoding(hass):
    await async_load_localization(hass)
    coordinator, client, entities = make_entities(hass, "Grandis / Economis")
    clock = next(
        entity
        for domain, entity, definition in entities
        if domain == "number" and definition.address == 40019
    )
    coordinator.data["silent_mode_start"] = 1320
    assert clock.native_value == 1320
    assert (clock.native_min_value, clock.native_max_value, clock.native_step) == (
        0,
        1440,
        15,
    )
    assert clock.native_unit_of_measurement == "min"
    clock.async_write_ha_state = lambda: None
    await clock.async_set_native_value(1335)
    client.write_register.assert_awaited_with(40019, 1335)
