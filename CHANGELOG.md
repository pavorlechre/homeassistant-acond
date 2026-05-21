# Changelog

Všechny podstatné změny integrace Acond Heat Pump jsou zaznamenány v tomto souboru.
All notable changes to the Acond Heat Pump integration are documented in this file.

Formát vychází z [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
a projekt dodržuje [sémantické verzování](https://semver.org/spec/v2.0.0.html).
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-21

První veřejné vydání (beta). — First public beta release.

### Přidáno / Added

🇨🇿 **Česky**

- Připojení k tepelným čerpadlům Acond přes Modbus TCP bez jakékoli YAML konfigurace
- 115+ entit napříč šesti platformami (`sensor`, `binary_sensor`, `number`, `switch`, `select`, `button`)
- Automaticky generovaný Lovelace dashboard využívající pouze vestavěné karty Home Assistant
- Obousměrné ovládání: provozní režimy, setpointy, tichý provoz, bivalence
- Podpora dvou sérií čerpadel: Grandis / Economis a PRO
- Dvojjazyčné uživatelské rozhraní (čeština a angličtina)
- Export AI kontextu pro diagnostiku a generování YAML s pomocí AI asistenta
- Vestavěné dekódování chybových kódů
- Průvodce migrací z ručně psané YAML Modbus konfigurace
- Místní brand obrázky (ikona a logo)

🇬🇧 **English**

- Modbus TCP connection to Acond heat pumps with zero YAML configuration
- 115+ entities across six platforms (`sensor`, `binary_sensor`, `number`, `switch`, `select`, `button`)
- Automatically generated Lovelace dashboard using only built-in Home Assistant cards
- Bidirectional control: operating modes, setpoints, silent mode, bivalence
- Support for two heat pump series: Grandis / Economis and PRO
- Bilingual user interface (English and Czech)
- AI Context export for AI-assisted diagnostics and YAML generation
- Built-in error code decoding
- Migration guide for moving from a manual YAML Modbus configuration
- Local brand images (icon and logo)

[0.1.0]: https://github.com/pavorlechre/homeassistant-acond/releases/tag/v0.1.0
