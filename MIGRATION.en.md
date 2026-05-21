# Migrating from a YAML Modbus configuration to the Acond integration

[![Česká verze](https://img.shields.io/badge/Čeština-CS-blue.svg)](MIGRATION.md)

This document describes how to move from a **hand-written YAML modbus** configuration in `configuration.yaml` to the **Acond Heat Pump integration**. With the help of an AI assistant, the process takes roughly **30–60 minutes** depending on how many automations and templates you have.

---

## Who this document is for

If you have a `modbus:` block in your `configuration.yaml` for an Acond heat pump and you want to:

- ✅ Get rid of hand-juggling YAML
- ✅ Get an **automatically created Lovelace dashboard**
- ✅ Get **117+ entities** instead of your 10–20 hand-written ones
- ✅ Built-in features: error decoding, COP, statistics, Options Flow
- ✅ A multilingual UI (Czech + English)

…then you're in the right place.

---

## Before you start

### What you'll need

- Home Assistant **2024.11.0** or newer
- **HACS** installed
- Access to your **heat pump's panel** (you'll briefly turn Modbus communication off and on)
- An AI assistant — **we recommend Claude** (Anthropic); the integration's author tested the quality on his own migration. Alternatives: ChatGPT, Gemini.
- About **30–60 minutes of focused work** (not in the middle of cooking)

### ⚠️ Important warnings

> **The Acond heat pump accepts only ONE Modbus client at a time.** If you have an active `modbus:` block in `configuration.yaml` and install the Acond integration at the same time, **the integration won't connect** (the communication slot is taken).
>
> That is why we have to remove the YAML modbus **BEFORE** installing the new integration.

> **The old YAML modbus and the new integration CANNOT run at the same time**, nor can they be "bridged" in any way. The process is `old removed → restart → new install`.

> **Some old entities will stop existing.** Your automations, scripts, templates and dashboards that use them **will stop working**. For that reason you **must have backups of**:
> - A full HA backup (step 1)
> - A copy of your original `configuration.yaml` (step 2)

---

## Quick outline

Before diving into the details, here is the whole process in brief:

1. **Back up your whole HA** — a full backup, so you can return to the original state if anything fails.
2. **Save a copy of `configuration.yaml`** — a text copy on the side; the AI will need it later to map entities.
3. **Let the AI clean up `configuration.yaml`** — removing the `modbus:` block and related template entities. The old Modbus cannot be kept — it is not possible.
4. **Restart HA with the cleaned config** — Modbus communication turns off, the old entities disappear.
5. **Turn Modbus off and on at the heat pump panel** — frees the communication slot; set the timeout to 4:30.
6. **Install the Acond integration** — enter the pump's IP and series; the new integration starts working.
7. **Check the new dashboard and entities** — verify the control panel was created and the entities have states.
8. **Generate the AI context (Full HA)** — export the current state of HA for the AI assistant.
9. **Send the AI three things** — the original `configuration.yaml`, the AI context, and the prepared prompt; the AI creates the mapping and patches.
10. **Apply the patches from the AI** — fix the affected automations, scripts, templates and dashboards according to the AI's suggestions.
11. **Clean up unnecessary functionality** — ask the AI for a list of redundant template entities and delete the approved ones.

📖 **A detailed procedure for each step is below.**

---

## Detailed procedure

### 1. Back up your whole HA

Before you change anything, create a **full backup** of Home Assistant — that is your safety net for returning to the original state.

1. **Settings → Backups → Create backup**
2. Choose **Full backup**
3. Wait for the backup to finish (1–5 minutes depending on installation size)

If anything fails during the migration, you can restore HA from this backup to its pre-migration state.

### 2. Save a copy of `configuration.yaml`

This is **not an HA backup** (you did that in step 1). Here you need a **separate text copy** of the `configuration.yaml` file, because **the AI will need it in step 9** — it will see from it what the original entities were named and which Modbus registers they served.

Open **File Editor** (or Studio Code Server, or SSH) in HA and make a copy of `/config/configuration.yaml`:

- File Editor: right-click → Duplicate → rename to `configuration.yaml.backup_before_acond`
- Or via terminal: `cp /config/configuration.yaml /config/configuration.yaml.backup_before_acond`

**Without this copy, the AI will not be able to map old entities to new ones.**

### 3. Let the AI clean up `configuration.yaml`

> 💡 **Tip:** You can leave this to the AI rather than doing it by hand. The AI will make fewer mistakes than your copy-paste.

**Procedure:**

1. Open a chat with the AI (Claude / ChatGPT / Gemini)
2. Paste the entire contents of your `configuration.yaml`
3. Write this prompt:

```
I'm migrating from a manual YAML Modbus setup to the new HA
Acond integration. I need an edited configuration.yaml from you
without the Modbus parts.

Specifically, remove:
1. The entire modbus: block (sensors, climates, switches,
   everything inside)
2. All template sensors that reference sensor.ACOND_*
3. All template binary_sensors that read bits of ACOND_TC_status
4. All template switches that call modbus.write_register.
   NOTE: if my modbus: block had a name (e.g. name: Acond_EVI),
   also remove the template switches that reference this name
   via the "hub:" parameter. If such a switch remained, HA
   would report an error on restart.

What to KEEP:
- automation: !include, script: !include, scene: !include
- default_config:, frontend:, themes:
- utility_meter:, statistics:, rest: (those unrelated to Acond)
- Custom template sensors unrelated to Acond
- Anything else unrelated to Acond

Send me the resulting configuration.yaml.
```

4. Copy the resulting `configuration.yaml` the AI sends you
5. **Paste it back into HA** (via File Editor)
6. **Save the file**, but **DO NOT RESTART HA YET** — the restart is the next step

> ⚠️ **The old Modbus cannot be kept.** It is not possible to have YAML modbus and the integration at the same time (the heat pump accepts only one client). The process is one-way: old removed → new integration.

### 4. Restart HA with the cleaned config

1. **Settings → System → Restart** (a Core restart is enough)
2. Wait for the restart (about 1–2 minutes)

**What just happened:**
- ✅ The old Modbus entities disappeared from HA
- ✅ The Modbus slot on the heat pump was freed
- ❌ Your automations, scripts and dashboards with references to old entities are **broken** (the entities no longer exist)
- ✅ The YAML code of the automations stayed in the files (`automations.yaml`, etc.) — the AI will see it in step 9

### 5. Turn Modbus off and on at the heat pump panel

> 🔑 **This step saves 30 minutes of frustration.**

The Acond heat pump remembers that **a Modbus client was connected**. Even though HA restarted, **the heat pump panel does not see that**. If you went straight to installation now, the integration might **fail to connect** (the slot is still "occupied" from the heat pump's perspective).

**Procedure:**

1. Open the **heat pump's web interface** (`http://<hp_ip>` — typically `10.10.x.x` or `192.168.x.x`)
2. Find the **Modbus TCP** settings
3. **Turn off Modbus TCP communication** (typically a checkbox or toggle)
4. Save the settings
5. Wait **5 seconds**
6. **Turn Modbus TCP communication back on**
7. **Set the timeout to 4:30 (4 minutes 30 seconds) or more** — without this the integration will occasionally drop out
8. Save the settings

The slot is now **truly free** and the heat pump is ready to accept a new client.

### 6. Installing the Acond integration

1. In HA, open **HACS**
2. **Integrations** → **⋮ menu** → **Custom repositories**
3. Add the URL: `https://github.com/pavorlechre/homeassistant-acond`
4. Category: **Integration**
5. Click **Add**
6. Find **Acond Heat Pump** in the list of HACS integrations
7. Click **Download**
8. Restart HA (Settings → System → Restart)
9. After the restart: **Settings → Devices & Services → Add Integration**
10. Search for **Acond Heat Pump**
11. Fill in:
    - The **IP address** of your heat pump (e.g. `192.168.1.100`)
    - The **series** — `Grandis / Economis` or `PRO`
12. Click **Submit**

### 7. Checking the new dashboard and entities

1. In the HA sidebar, look for **ACOND TČ** — the new dashboard should have been created automatically
2. **Open it** — you should see:
   - Overview (Pohled) — temperatures, power, COP
   - Control (Ovládání) — setpoints, mode toggles
3. **Settings → Devices & Services → Acond Heat Pump** — you should see:
   - Version: 0.1.0
   - 1 device "Acond"
   - 117 entities
   - No errors

**If something failed:**
- ❌ "Cannot connect to the heat pump" → check that the IP is correct and the heat pump has Modbus TCP active (step 5)
- ❌ All entities `unavailable` → the same connection problem, or the heat pump has a timeout below 4:30
- ❌ Dashboard missing → open `Settings → Dashboards`, **ACOND TČ** should be there

### 8. Generate the AI context

Now is the right time to export the **state of HA** for the AI.

1. **Settings → Devices & Services → Acond Heat Pump → Acond** (device)
2. In the entity list, find the **Generate AI Context (Full HA)** button
3. Click it
4. Wait **3–10 seconds**
5. **A message with a download link** will appear **in the notifications**
6. Click it → the file `full_<date>.md` downloads

> ⚠️ **Open the file in a text editor before sending it to the AI.** The integration **automatically redacts** passwords, tokens, etc., but **give it a quick look** — if there is a sensitive value somewhere (e.g. your router's IP, a MAC address) that you do not want to share, you can remove it from the text manually.

### 9. Send the AI three things at once

Open a new chat with the AI and send **all at once**:

1. ✅ The **backed-up original `configuration.yaml`** (from step 2)
2. ✅ The **generated `full_*.md` AI context** (from step 8)
3. ✅ **This prompt:**

```
I'm migrating from YAML Modbus Acond to the HA Acond Heat Pump
integration.

I'm sending you:
1. My ORIGINAL configuration.yaml (before migration) — use it to
   tell how the original entities were named and which Modbus
   registers they served
2. The generated AI context after migration — it shows the
   current state of HA: new Acond entities, automations, scripts,
   templates, scenes, lovelace dashboards

Your task:

A) Create a mapping between the OLD and NEW entities:
   - Old: sensor.ACOND_T_act_TUV  (from YAML modbus)
   - New: sensor.acond_30005_t_act_tuv  (from the integration)
   - Do the mapping by Modbus register address, not by entity
     name. The address is in the new entity's entity_id (e.g.
     30005) and in the address: field of the original YAML.

B) Generate YAML patches for ALL automations, scripts, scenes,
   templates and lovelace cards that use the old entities:
   - For each affected item, write:
     * What changes (item name, ID)
     * The complete fixed YAML code (to paste into automations.yaml
       or via the UI editor)
     * A short explanation of the change

C) Mark functionality that is now REDUNDANT with the integration
   and recommend it for removal:
   - If I hand-wrote template binary_sensors in configuration.yaml
     to break out bit_0 to bit_12 of ACOND_TC_status, the
     integration already does this itself → recommend removal
   - If I calculated COP via a template sensor, the integration
     has its own → point out that it is redundant (I'll decide
     whether to keep or delete it)
   - Etc.

Format the answer as:
1. First the mapping table (1-2 pages)
2. Then a "Patches for automations" section
3. Then "Patches for scripts/scenes"
4. Then "Patches for templates"
5. Then "Patches for Lovelace dashboards"
6. Then "Redundant functionality"

Be conservative — if you are not sure, do NOT do the mapping and
mark it as "verify manually".
```

### 10. Apply the patches from the AI

The AI will send you a **structured response** with the fixes. Procedure:

**For each item in the AI's response:**

1. **Open the relevant item in HA** (Settings → Automations → the specific automation)
2. Click **⋮ → Edit in YAML**
3. **Delete the old YAML** and paste the **fixed** one from the AI
4. **Save**
5. **Test** it manually — run the automation and check whether it works

> 💡 **Tip:** Start with **one or two simple automations**. Once they work, move on to the more complex ones. Never do "Apply all" at once — check them one by one.

> 💡 **If the AI is uncertain:** Sometimes the AI writes *"The mapping of this entity is uncertain — verify manually"*. That means **you have to decide yourself**. It usually helps to look at the old entity's **friendly_name** in the original YAML and find the closest match in the new integration.

### 11. Clean up unnecessary functionality

After applying the patches you still have one leftover in HA — the **template sensors and binary_sensors** you hand-wrote in `configuration.yaml`. Some of them are now done natively by the integration (e.g. bit breakout, COP), so they are **redundant**.

**Procedure:**

1. In the same chat with the AI, write:

```
Thanks for the patches. Now:

Send me a list of the template sensors, binary_sensors and
input helpers (input_boolean, input_number, etc.) that, according
to my original configuration.yaml, were HELPERS for the Modbus
integration but are now REDUNDANT — the Acond integration does
them natively.

For each one, write:
- The item name in configuration.yaml
- Which new entity replaces it
- Recommendation: delete / keep (why)

Be careful — if you are not sure, recommend keeping it.
```

2. The AI replies with a list.
3. **Evaluate** each item yourself:
   - ✅ Delete only the ones you are sure about
   - ❌ Leave alone the ones you have doubts about (a few unnecessary entities is better than lost functionality)
4. **Delete** the approved ones from `configuration.yaml` (or `templates.yaml`, wherever you have them)
5. **Restart HA** after the cleanup

### Done 🎉

Your HA now has:
- ✅ The Acond integration with 117 entities
- ✅ An auto-generated dashboard
- ✅ Working automations, scripts and scenes (with fixed entity_ids)
- ✅ A cleaned-up `configuration.yaml`
- ✅ A backup (just in case)

**It took some work, but I believe you'll be happy with it.** 🙌

If you have any problem with the migration — don't hesitate to **report an issue** on [GitHub](https://github.com/pavorlechre/homeassistant-acond/issues).

---

## After the migration — small details

### The `configuration.yaml.backup_before_acond` backup

**Should you keep it?** I recommend yes, at least for 30 days. It gives you full peace of mind if you eventually wanted to roll the migration back (unlikely, but healthy).

After 30 days, once everything is stable, delete it.

### The heat pump's address

If you change your router and the heat pump gets a different IP, **do not reinstall the integration**. Instead:

1. **Settings → Devices & Services → Acond Heat Pump**
2. Click the **⋮ three dots** next to "Acond (xx.xx.xx.xx)"
3. **Configure**
4. Change the IP → Submit
5. The integration reloads automatically

### Modbus timeout

This is a setting **on the heat pump panel**, not in HA. If you ever **accidentally lower** the Modbus timeout below 4:30, the integration will start dropping out (entities → `unavailable` occasionally). Set it back to 4:30+.

---

## What if it doesn't work

### All entities `unavailable`

1. Settings → System → Logs → filter for `acond`
2. Look for **WARNING** or **ERROR**
3. Typically:
   - "Cannot connect to host" → wrong IP / heat pump Modbus off
   - "Connection timeout" → heat pump timeout below 4:30

### Some entities `unavailable`, others OK

That is fine. Older heat pump firmware may not support all registers. The affected entities **activate automatically** when Acond releases a firmware update.

### The AI mapping is incorrect

This happens occasionally, especially with **creatively named** entities. Procedure:

1. **Find the Modbus address in the original `configuration.yaml`** (e.g. `address: 6`)
2. The Acond integration has entities in the form `<platform>.acond_<address>_<key>` — address **30006** corresponds to Modbus `address: 6` (registers 30000–39999 are input registers, 40000–49999 are holding registers — address 6 in input = 30006, in holding = 40006)
3. **Find the new entity** with the matching register number

### Something completely broken

1. **Settings → Backups** → restore from the full HA backup made before the migration
2. **Report an issue** on GitHub (with the log)
3. **Maybe try again** in a few days — the integration gets updates

---

## Questions and answers

**Q: Can I try the old YAML Modbus and the integration at the same time?**
A: **No.** The Acond heat pump accepts only 1 Modbus client. Neither the integration nor the YAML would be available.

**Q: How much time does the migration take?**
A: About **30–60 minutes** depending on the number of automations. Steps 1–7 take 15 minutes at most. Steps 8–11 depend on the size of your HA.

**Q: What if I don't have a backup `configuration.yaml`?**
A: The AI mapping will be **much worse** (it has to guess from friendly_name and context). I recommend doing an **HA snapshot restore** back, making the backup, and trying again.

**Q: Can I rename some entities from the new integration?**
A: Only in the UI (Friendly Name), not the entity_id. The entity_id is the mandatory format `<platform>.acond_<register>_<key>`. If you changed it, the AI would not be able to do the mapping during a future migration to a newer version.

**Q: What if I find a bug in the integration during the migration?**
A: Report an issue on [GitHub](https://github.com/pavorlechre/homeassistant-acond/issues) **with the AI context attached** — the author will see what you have and will be able to help.

---

## Example — a real migration

A concrete example of a migration from a real `configuration.yaml` (Pavle Vorlech, the integration's author, 2026):

**Before:**
- 5 modbus climates (DHW, T_return, etc.)
- 9 modbus sensors
- 2 modbus switches
- 8 template binary_sensors for the TC_status bits
- 1 template switch for PWM control
- 1 template sensor for regulation_mode

**After:**
- 0 modbus entries in `configuration.yaml`
- 117 entities from the Acond integration
- The binary_sensor and switch templates cleaned up
- Kept: the rest sensor `Active power Lipany`, utility_meter, the REST forecast (all unrelated to Acond)

**Time investment:** 45 minutes of focused work with the AI assistant.

**Result:** A working integration with an auto-generated dashboard + the original automations preserved.

---

## Thanks for trying it out! 🙌

If this documentation helped you, [a star on GitHub](https://github.com/pavorlechre/homeassistant-acond) is very welcome.

If you have any questions, report them in [Issues](https://github.com/pavorlechre/homeassistant-acond/issues) — both the author and the AI assistant are ready to help.
