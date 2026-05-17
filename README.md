# Acond Heat Pump – Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/HA-2024.11%2B-blue.svg)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/pavorlechre/homeassistant-acond/releases)

> 🇨🇿 **Tato dokumentace je dostupná i v češtině:** [README.cs.md](README.cs.md)

---

## ⚠️ Beta Release

This integration is currently in beta (v0.1.0). It has been developed and tested on real hardware but has not yet been validated by a wider user base. **Expect occasional bugs and breaking changes** until v1.0.0. Please report issues on the [Issues page](https://github.com/pavorlechre/homeassistant-acond/issues).

---

## Disclaimer

This is an unofficial community integration. It is not affiliated with, endorsed by, or supported by Acond a.s. The "Acond" name and logo are used solely to identify the heat pumps this integration communicates with.

---

## What it does

A Home Assistant custom integration for **Acond heat pumps** communicating over **Modbus TCP**. The integration exposes the heat pump's sensors and controls as native Home Assistant entities, automatically creates a Lovelace dashboard, and works without any YAML configuration.

## Features

- **Zero YAML configuration** – just enter the heat pump's IP address
- **115+ entities** – read-only sensors and control entities for writing (change heat pump behavior)
- **Bidirectional control** – mode selection, setpoints, silent mode, bivalence
- **Auto-generated Lovelace dashboard** – installed and ready immediately after setup
- **Multilingual UI** – English and Czech (config flow + entity names)
- **Series support** – Grandis / Economis and PRO
- **AI Context** – generate a markdown snapshot of your HA for AI assistants with one click (fault diagnosis, YAML generation)
- **Disciplined Modbus master** – persistent TCP connection, 15-second polling
- **Built-in error decoding** – numeric error codes translated to human-readable text
- **No external frontend dependencies** – uses only built-in Home Assistant cards

---

## Requirements

- Home Assistant **2024.11.0** or newer
- HACS installed
- Acond heat pump with **Modbus TCP enabled** (port 502)
- **No other Modbus TCP client connected** – Acond accepts only one master at a time. If you have a `modbus:` block in your `configuration.yaml`, **remove it before installation**. Similarly, external systems connected via Modbus TCP (e.g. Loxone) must be disconnected.

---

## Installation

### Via HACS (recommended)

1. In HACS, open **Integrations** → **⋮ menu** → **Custom repositories**
2. Add the repository URL: `https://github.com/pavorlechre/homeassistant-acond`
3. Category: **Integration**
4. Click **Add**
5. Find **Acond Heat Pump** in the HACS integrations list and click **Download**
6. Restart Home Assistant

### Manual installation

1. Download the contents of the `custom_components/acond/` folder from this repository
2. Copy it to `<config>/custom_components/acond/` in your Home Assistant configuration
3. Restart Home Assistant

---

## Configuration

After installation:

1. Go to **Settings** → **Devices & services** → **Add integration**
2. Search for **Acond Heat Pump**
3. Fill in:
   - **IP address** – the heat pump's IP on your network (e.g. `192.168.1.100`)
   - **Heat pump series** – `Grandis / Economis` or `PRO`
4. Click **Submit**

The integration connects to the heat pump, creates all entities, and registers a new dashboard panel ("Acond") in the HA sidebar.

### Modbus timeout setting

Acond's internal Modbus timeout must be set to **at least 4 minutes 30 seconds** so the integration's 15-second polling interval is not interrupted. Configure this on the heat pump's own panel.

---

## Provided entities

The integration creates approximately **115+ entities** across six platforms. They are split into **read-only** entities (showing the heat pump's state) and **control** entities (writing to 400xx registers, changing the heat pump's behavior).

### Read-only entities

| Platform | Count | Purpose |
|---|---|---|
| `sensor` | ~64 | Temperatures, power, COP, energy, runtime, status |
| `binary_sensor` | 17 | Heat pump state bits and component running indicators |

### Control entities (writing to 400xx)

| Platform | Count | Purpose |
|---|---|---|
| `number` | ~15 | Setpoints (DHW, return water, bivalence threshold, capacity, external sensor corrections) |
| `switch` | ~10 | Mode flags (heating only, cooling, solar, pool, bivalence, silent mode) |
| `select` | 1 | Regulation type |
| `button` | ~8 | Acknowledge error, season toggle, PLC reset, AI context generator |

All entities are grouped under a single device named *Acond* and the Modbus register number is included in `entity_id` for easy identification (e.g. `sensor.acond_30006_t_act_tuv`).

---

## AI Context – helper for AI assistants

The integration can generate a **structured markdown file** with the current state of your Home Assistant instance, which you simply attach to a chat with an AI assistant (Claude, ChatGPT, ...) – the AI then immediately knows what you have configured. Useful for:

- **Fault diagnosis** – the AI sees entities, their states, the last few lines of the integration's log, and global errors
- **YAML help** – the AI knows your entities, automations, areas, scripts, and generates YAML that fits precisely to your environment

### Two modes (available as buttons in the Acond device)

| Button | What it exports |
|---|---|
| **Generate AI Context (Acond)** | Only Acond entities + automations/scripts/scenes that reference them |
| **Generate AI Context (Full HA)** | The entire Home Assistant – all integrations, entities, automations |

After clicking, a markdown file is generated in `/config/www/acond_ai_context/`, accessible via a download link in the HA notification. You then simply attach the file to your AI chat.

### Safety

Before saving the file, the integration **automatically redacts** values whose keys contain `password`, `token`, `api_key`, `secret`, `webhook`, and similar. **Always check the file yourself before sending it to an AI** – automatic redaction does not catch everything (e.g. tokens in comments or fields with non-standard naming).

### Use case example: migrating from YAML Modbus configuration

If you are migrating from an existing hand-written YAML modbus configuration to this integration, the AI context together with your original `configuration.yaml` form a strong tandem for automatic mapping of old entities to new ones and generating YAML patches for affected automations, scripts, templates, and Lovelace cards. The detailed procedure is described in a separate document [MIGRATION.md](MIGRATION.md).

---

## Limitations

- **No SG (Smart Grid) features** – The integration covers only registers listed in the official Acond Modbus protocol (AC781150/52). Some newer features (notably SG ready, dynamic tariffs, external blocking) are available in some heat pumps, but **Acond has not released official Modbus documentation for them**. As a matter of principle, we do not reverse-engineer – if Acond extends the protocol, the integration will follow.

---

## Troubleshooting

### Heat pump doesn't connect

- Verify the IP address and that port 502 is reachable (`ping` and `telnet <ip> 502`)
- Check that no other Modbus TCP master is connected (YAML modbus in `configuration.yaml`, Loxone, etc.)
- Increase the heat pump's Modbus timeout to at least 4:30

### Entities are `unavailable`

- Older heat pump firmware may not support all registers – this is normal
- Affected entities will reactivate automatically after a firmware update on the heat pump

### Log shows probe errors

- Probe errors during startup are intentionally logged at `DEBUG` level – they will not appear in the standard log
- If you see them at `ERROR` level, increase the heat pump's Modbus timeout

---

## Reporting bugs

Please report bugs and feature requests via the [Issues page](https://github.com/pavorlechre/homeassistant-acond/issues). Use the provided issue templates and include:

- Home Assistant version
- Integration version
- Heat pump model and firmware version
- Relevant Home Assistant log excerpts (ideally a generated AI context)

---

## License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **Claude (Anthropic), Opus 4.7 model** – AI assistant without which this integration would not exist. Helped with architecture design, code, documentation, and long discussions about Modbus protocols, Home Assistant paradigms, and UX
- The Home Assistant team and the wider community
- The [pymodbus](https://github.com/pymodbus-dev/pymodbus) library
- Friends and early testers who provided feedback on real hardware

---

## Author

**Pavel Vorlech** – [@pavorlechre](https://github.com/pavorlechre)
