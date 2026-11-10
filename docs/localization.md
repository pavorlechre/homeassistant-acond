# Localization

Entity names, setup/options forms and presentation messages use the standard
Home Assistant catalogs in `translations/en.json`, `cs.json` and `pl.json`.
`strings.json` describes the same complete English schema. Entity classes use
`translation_key` and `has_entity_name`; the existing explicit `entity_id` and
`unique_id` assignments are retained, including the PRO-specific power labels.

## Public API compatibility

The existing native sensor states and select options are public API. In
particular, MaR compares the regulation state to the literal `Standard`.
Localization never changes these strings, the Modbus tables, units, ranges,
scaling, or write methods.

Text sensors and the regulation selector additionally expose `localized_state`.
The Polish dashboard displays that attribute and offers translated regulation
buttons calling `select.select_option` with the original options. Native HA
more-info dialogs, Developer Tools, history and external dashboards that show
the raw state/options can therefore still display the original Czech/English
values. There is deliberately no migration of those values in this change.

Diagnostic log messages and the contents of the AI diagnostic Markdown export
remain in their original language. The export notifications are localized.
The existing fault-code tables are translated as provided, without correcting
or reinterpreting the manufacturer's model-dependent mappings.

## Generated dashboard

The base YAML is unchanged. `lovelace/translations/pl.json` is a separate
string-to-string catalog for titles, labels, Markdown, help and confirmations.
Only presentation fields are translated; entity references, navigation paths,
conditions, actions and service payloads retain their original values.
Instructions in the help examples retain their original code. Comments and the
example automation's descriptive alias are translated; identifiers and values
remain unchanged.

The bundled `frontend/readability.js` module wraps card headings, row labels,
button captions and chart legends. Long horizontal stacks and glance cards use
responsive columns. It is registered using HA's standard extra-module API only
for Polish, and its CSS is scoped to `/acond-dashboard`. Navigating elsewhere
removes its styles and observers. No card-mod, custom card, external package,
state substitution or service call is introduced by this module. The asset URL
contains a content hash to refresh cached copies after an update.

Text-valued glance cards are presented as ordinary entities cards because glance
ignores attribute rows. This keeps `localized_state` visible without changing the
native entity. Tiles use automatically sized rows so wrapped names fit.

Localization runs before the compositor appends MaR views or inserts its slots.
Those contributions belong to MaR and are intentionally not translated by Acond.
The Acond-owned MaR introduction is translated when the add-on is absent.
No custom frontend card or external translation service is required.

Quiet-mode controls retain the author's minute units and 0–1440 bounds. The
dashboard readback uses display-only labels for the 0/1 flag and HH:MM for valid
times (1320 min → 22:00, 360 min → 06:00). Values outside the integration's range
are shown as such instead of wrapping into an apparently valid clock time.
Native numeric states, the existing `time` attribute and write encoding remain
unchanged. The earlier 2200-minute example was invalid synthetic test data.

Markdown resets its shadow-root HTML while rendering. Its wrapping rules use an
adopted stylesheet so table layout survives rerenders. Table bounds, all columns
and unchanged cell contents are checked separately at four viewport sizes;
the stylesheet is removed when leaving the Acond dashboard.

The dashboard/messages follow the **Home Assistant system language** selected
under Settings → System → General. Restart Home Assistant after changing it so
the generated dashboard and its presentation cache use the new language.
Changing only the language in a user profile does not regenerate this dashboard.
User-assigned entity names are still controlled by Home Assistant's entity
registry and are not forcibly overwritten.

Unsupported dashboard languages and missing/new strings fall back to the
upstream dashboard. Standard entity/message catalogs fall back to English.
Missing/corrupt presentation files must not prevent heat-pump setup.
Do not edit `acond_dashboard.generated.yaml`; it is regenerated at startup.

## Maintaining translations

1. Add entity/message keys to English, Czech and Polish catalogs together.
2. Keep placeholders identical and use normal HA translation keys. The `common`
   section holds runtime presentation messages and code-based display labels.
3. For a new dashboard label, add an exact source-to-translation entry to its
   catalog. The coverage test identifies newly added source labels.
4. Keep legacy state strings, identifiers and service values unchanged.
5. Run `python -m pytest -q` after installing `requirements-test.txt` into a
   separate Python 3.12 virtual environment.

Tests instantiate real Home Assistant entities without starting a server or
setting up the Acond connection. Socket connections are prohibited in tests;
write encoding is verified only against an in-memory fake client.

Compatibility was also checked on Home Assistant 2026.10.1 / Python 3.14.2:
28 offline tests passed on both HA versions. An isolated HA 2026.10.1 server
with frontend 20260930.3 loaded all 117 entities and nine dashboard views.
Browser checks covered all nine views at widths 1440, 390 and 320 pixels,
including content below the first screen, Czech prose and clipped text checks,
setup/options validation and
the regulation/room-setpoint controls against an in-memory transport. Outgoing
connections from that server were restricted to loopback; no real pump or
production Home Assistant was accessed. These tests do not establish hardware
compatibility or validate the original model-specific fault mappings.

When HA changes its frontend DOM/CSS, repeat the readability checks. The module
is presentation-only and a missing selector cannot change pump control. Refresh
the browser after installing a new integration version to load its new module.
