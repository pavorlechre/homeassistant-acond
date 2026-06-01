# ROADMAP – integrace Acond

Nápady a plánované změny pro další verze integrace `acond`.

**Postup:** položka žije zde, dokud není hotová. Po realizaci se odsud
odstraní — *proč a jak* se zapíše do `DECISIONS.md`, *co se mění pro
uživatele* do `CHANGELOG.md`.

Založeno 27. 5. 2026, naposledy aktualizováno 1. 6. 2026 po vydání v0.2.0.

---

## Verze 0.3.0

### 1. Debounce zápisu do Modbusu (slider + tlačítka)
Při změně number entity (slider i tlačítka +/−) neposílat zápis okamžitě,
ale s 2s prodlevou. Každá další změna odpočet resetuje; skutečný zápis
proběhne až po 2 s klidu. PendingValue zajistí okamžitou vizuální odezvu.
Výsledek: rychlé úpravy (opakované klikání, třesoucí ruka) → jeden čistý
zápis místo spršky. Generické pro všechny `AcondNumber`.
Technicky: `async_call_later`, cancel + reschedule při každé změně.
**Stav:** odloženo z v0.2.0 – nejdříve sbíráme reálná data od uživatelů
(pokud někdo nahlásí problém s burstem zápisů, prioritizovat).

### 2. Read-back verifikace po `write_register`
Aktuálně spoléháme pouze na `response.isError()` z pymodbusu. Doplnit
post-write read confirmation, alespoň u kritických registrů (40006 TC_set,
40014 comp_capacity, 40005 t_set_tuv). Při neshodě logovat warning.
**Stav:** nápad.

### 3. Per-entry suffix pro AI context tlačítka (multi-TČ)
Pokud uživatel přidá druhou config entry (druhá TČ), současný flag
`_ai_context_buttons_added` v `hass.data[DOMAIN]` zabrání vytvoření
tlačítek pro druhou entry. Řešení: každá entry vytvoří vlastní AI context
tlačítka s entry-suffixem v entity_id.
**Stav:** nápad (zatím nikdo nemá více TČ, ale architektonicky čisté).

---

## Pozorování (bez akce)

### Bug B: AI context tlačítka zmizí při restartu s offline TČ
Symptom: po HA restartu s nedostupným TČ se v entity registry objeví
`button.acond_ai_context_acond` jako „missing or not currently available".
Po dalším restartu kdy TČ je dostupné se vrátí. Reprodukováno jednou
(30. 5. 2026), od té doby se neobjevilo. Možný vztah s nedostupností
připojení v early-startup fázi async_setup_entry.
**Stav:** pozorování – pokud se vrátí, prioritizovat. Jinak ne.

---

## Později (mimo aktuální release)

Sem patří položky pro pozdější verze. Větší celky (např. samostatná
integrace `acond_regulation`) se vedou mimo tento soubor.

### Extended Modbus protokol – 4-point ekvitermická křivka
Registry 30102–30125 / 40102–40125, `T_act_air_average` 30081/40026,
bitfield `TC_system_parameters1` 30100/40100 (pravděpodobně SG Ready flags).
Čekáme na plnou německou verzi protokolu od Acond technical support
před bezpečnou implementací mappingu.

### Config flow opt-in 60 °C TUV unlock přes Legionella cyklus
Aktuálně options flow umožní 50–60 °C, ale uživatel musí mít servisně
odemčenou TČ. Alternativní cesta: jeden Legionella cyklus v Acond app
odemkne 60 °C dočasně. Zvážit, zda to nějak signalizovat v UI.
**Stav:** zatím není v plánu – komplikuje UX bez zjevné výhody.
