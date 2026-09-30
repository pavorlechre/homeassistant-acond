# Changelog

Všechny podstatné změny integrace Acond Heat Pump jsou zaznamenány v tomto souboru.
All notable changes to the Acond Heat Pump integration are documented in this file.

Formát vychází z [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
a projekt dodržuje [sémantické verzování](https://semver.org/spec/v2.0.0.html).
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Nevydáno / Unreleased]

### Přidáno / Added

🇨🇿 **Česky**

- **Skládací dashboard.** Dashboard Acond TČ se při startu skládá ze základu a z oken doplňků. Když je nainstalovaný doplněk Acond Regulator (MaR), jeho okna se přidají na konec; když není, zobrazí se na konci okno s odkazem na něj. Složený výsledek je v `acond_dashboard.generated.yaml`, základ `acond_dashboard.yaml` se jen čte. Změny se projeví po **restartu HA**, ne po reloadu integrace.
- **Nová lišta dashboardu: Pohled, Entity, Servis.** Přehled, Ovládání a Energie jsou podokna okna Entity; Grafy, Diagnostika, Aplikace Acond a Nápověda podokna okna Servis (otevírají se tlačítkem, šipka zpět vlevo nahoře). Adresy oken se nemění, záložky fungují dál.
- **Vsuvka doplňku do Pohledu.** S nainstalovaným MaR se karta „Režim TČ & Stav“ nahradí schématem soustavy; tlačítka režimů zůstávají. Bez MaR je Pohled beze změny a v liště je okno MaR s odkazem.

🇬🇧 **English**

- **Composable dashboard.** At startup the Acond TČ dashboard is assembled from the base file and add-on views. With Acond Regulator (MaR) installed, its views are appended at the end; without it, a final view links to it. The result is written to `acond_dashboard.generated.yaml`; the base `acond_dashboard.yaml` is only read. Changes take effect after an **HA restart**, not an integration reload.
- **New dashboard bar: Pohled, Entity, Servis.** Přehled, Ovládání and Energie are subviews of Entity; Grafy, Diagnostika, Aplikace Acond and Nápověda subviews of Servis (opened by buttons, back arrow top left). View URLs are unchanged, bookmarks keep working.
- **Add-on insert into Pohled.** With MaR installed, the "Režim TČ & Stav" card is replaced by the system schematic; mode buttons stay. Without MaR, Pohled is unchanged and a MaR view with a link sits in the bar.

### Opraveno / Fixed

🇨🇿 **Česky**

- **Integrace se sama vzpamatuje, když bylo TČ při startu HA vypnuté.** Zjištění registrů (probe) se opakuje s rostoucím odstupem (1 min → max. 30 min), dokud neuspěje. Dřív zůstala integrace bez hodnot až do ručního reloadu.
- **Tišší log při výpadku TČ.** První neúspěšné připojení se zapíše jako chyba, další pokusy jen do ladicího logu a obnovení spojení jako informace. Při výpadku se už nepokouší o ~60 připojení každých 15 s.
- Tlačítka exportu AI kontextu v okně Diagnostika používají novou syntaxi `perform-action`.

🇬🇧 **English**

- **The integration recovers on its own when the heat pump was off at HA startup.** Register probing is retried with growing backoff (1 min → max 30 min) until it succeeds. Previously it stayed empty until a manual reload.
- **Quieter log during heat pump outages.** The first failed connection is logged as an error, further attempts at debug level, and recovery as info. No more ~60 connection attempts every 15 s during an outage.
- AI context export buttons in the Diagnostika view use the current `perform-action` syntax.

## [0.2.0] - 2026-06-01

Velký funkční update – Options flow, opravy tlačítek a několik bugfixů v jádře.
Major functional update – Options flow, button fixes and several core bugfixes.

### Přidáno / Added

🇨🇿 **Česky**

- **Options flow s rozšířenými nastaveními** (*Nastavení → Integrace → Acond → Konfigurovat*):
  - Maximální teplota TUV (50–60 °C, default 50). Hodnoty 51–60 vyžadují servisně odemčenou TČ.
  - Min/Max rozsah slideru kompresoru (40014): Grandis / Economis 1000–6000 rpm, PRO 2000–20000 W.
  - IP adresa TČ (zachováno z předchozí verze).
  - Po uložení se integrace automaticky reloadne, nové meze jsou platné okamžitě.
- **Podmíněná karta aktivní chyby** v Pohled view (pod sekcí „Režim TČ"). Zobrazí se jen když TČ hlásí chybu (sensor 30021). Obsahuje popis chyby a tlačítko Potvrdit s confirmation dialogem.
- **Readout aktuálního stropu kompresoru** (sensor 30020) pod sliderem 40014 v Pohled view. Spolu s 30024 v glance kartě dotváří trojici žádám / přijato / děje se – odhalí out-of-range zápisy i 3,5h ramp-up TČ.

🇬🇧 **English**

- **Options flow with extended settings** (*Settings → Integrations → Acond → Configure*):
  - Maximum DHW temperature (50–60 °C, default 50). Values 51–60 require a service-unlocked heat pump.
  - Min/Max range of the compressor slider (40014): Grandis / Economis 1000–6000 rpm, PRO 2000–20000 W.
  - Heat pump IP address (preserved from previous version).
  - After saving, the integration reloads automatically and new limits take effect immediately.
- **Conditional active fault card** in the Pohled view (below the "Heat pump mode" section). Shown only when the heat pump reports an error (sensor 30021). Includes a fault description and a Confirm button with a confirmation dialog.
- **Compressor cap readout** (sensor 30020) below the 40014 slider in the Pohled view. Together with 30024 in the glance card, this completes the trio requested / accepted / actual – exposes out-of-range writes and the 3.5h ramp-up of the heat pump.

### Změněno / Changed

🇨🇿 **Česky**

- **Default max teplota TUV: 46 → 50 °C.** Acond v praxi přijme 50 bez jakéhokoli servisního zásahu. Před tím integrace zbytečně blokovala zápis hodnot 47–50, které TČ akceptovala (viz GitHub issue #3).
- **Servisní akce v Ovládání view přepracovány.** Z `entities` karty (kde bylo aktivní jen „Stisknout" vpravo, ne celý řádek) na 3× `tile` karty ve `vertical-stack`. Celá karta je nyní klikací, jednotlivé akce drží pohromadě i v masonry layoutu (PC i mobil).

🇬🇧 **English**

- **Default max DHW temperature: 46 → 50 °C.** In practice Acond accepts 50 without any service intervention. Previously the integration needlessly blocked writes of 47–50 that the heat pump actually accepted (see GitHub issue #3).
- **Service actions in the Ovládání view reworked.** From an `entities` card (where only the "Press" link on the right was active, not the whole row) to 3 `tile` cards in a `vertical-stack`. The entire card is now clickable and the actions stay grouped even in the masonry layout (PC and mobile).

### Opraveno / Fixed

🇨🇿 **Česky**

- **Tlačítka Přepnout léto/zima a Potvrzení poruchy** v Servisní akce nyní spolehlivě fungují. Předchozí implementace nastavila bit pouze v jednom směru (set), TČ ale očekává náběžnou hranu (přechod 0→1) – zaseknutý bit po předchozím stisku znemožnil další akce. Nový pulzní zápis (clear → set → wait → clear) garantuje čistý přechod při každém stisku.
- **Falešné spotřební skoky v utility_meter.** Při timeoutu čtení registru se klíč v `coordinator.data` zachová s předchozí hodnotou místo zmizení (carry-forward). Energetické senzory (30035 / 30039) nyní nepadají na „unknown" při krátkých výpadcích Modbus spojení a utility_meter neeviduje falešné spotřební skoky.
- **Stale ring buffer v exportu AI kontextu.** Při HA restartu se logy integrace v exportu nyní obsahují čerstvé záznamy z aktuálního běhu, ne stará data z předchozích spuštění. Logger collector je nyní idempotentní a vždy startuje s prázdným bufferem.
- **Logger úroveň INFO.** Záznamy o startu integrace (`Acond: nastavuji integraci…`, probe výsledky, počty entit) se nyní zachytí do AI kontextu (předtím chybělo, protože default `logger.level` byl WARNING).

🇬🇧 **English**

- **Switch summer/winter and Confirm fault buttons** in Service actions now work reliably. The previous implementation set the bit in one direction only (set), but the heat pump expects a rising edge (0→1 transition) – a stuck bit from a previous press blocked further actions. The new pulse write (clear → set → wait → clear) guarantees a clean transition on every press.
- **False consumption spikes in utility_meter.** On register read timeout, the key in `coordinator.data` is preserved with the previous value instead of disappearing (carry-forward). Energy sensors (30035 / 30039) no longer fall to "unknown" on short Modbus outages and utility_meter no longer records phantom consumption jumps.
- **Stale ring buffer in AI context export.** After a Home Assistant restart, integration logs in the export now contain fresh records from the current run, not stale data from previous runs. The logger collector is now idempotent and always starts with an empty buffer.
- **Logger level INFO.** Integration startup records (`Acond: setting up integration…`, probe results, entity counts) are now captured in AI context (previously missing because the default `logger.level` was WARNING).

### Poznámka pro uživatele s vlastní kopií dashboardu / Note for users with a custom dashboard copy

🇨🇿 Změny dashboardu (v0.25 → v0.27) jsou popsané v changelog hlavičce souboru `acond_dashboard.yaml`. Pokud máš upravenou kopii, najdi v hlavičce sekce „Změny oproti v0.26" a „v0.27" a aplikuj odpovídající úpravy v Editoru kódu nastavení své kopie.

🇬🇧 Dashboard changes (v0.25 → v0.27) are documented in the changelog header of `acond_dashboard.yaml`. If you have a customized copy, find the "Changes from v0.26" and "v0.27" sections in the header and apply the corresponding edits in your copy's code editor.

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

[0.2.0]: https://github.com/pavorlechre/homeassistant-acond/releases/tag/v0.2.0
[0.1.0]: https://github.com/pavorlechre/homeassistant-acond/releases/tag/v0.1.0
