# ROADMAP – integrace Acond

Nápady a plánované změny pro další verze integrace `acond`.

**Postup:** položka žije zde, dokud není hotová. Po realizaci se odsud
odstraní — *proč a jak* se zapíše do `DECISIONS.md`, *co se mění pro
uživatele* do `CHANGELOG.md`.

Založeno 27. 5. 2026.

---

## Verze 0.2.0

### 1. Oprava tlačítek v kartě „Servisní akce"
Tři tlačítka (Potvrzení poruchy, Přepnout léto / zima, Reset PLC) po stisku
neposkytují žádnou vizuální zpětnou vazbu — uživatel neví, zda akce
proběhla. Navíc „Přepnout léto / zima" nezobrazuje aktuální stav (léto /
zima), takže tlačítko působí jako přepínač bez polohy.

Oprava zahrnuje:
- zobrazení aktuálního stavu léto/zima vedle tlačítka (z TC_status)
- vizuální potvrzení provedené akce u všech tří tlačítek
- pro Reset PLC: potvrzovací dialog před provedením

**Stav:** oprava bugu — priorita.

### 2. Zvýšený limit TUV (46 → 60 °C)
Registr 40005 je v protokolu omezen na 46 °C, ale 60 °C je dostupných po
servisním odemčení. Volitelná konfigurace (options flow), default 46 °C;
uživatel se servisně odemčenou TČ si může povolit 60 °C.
**Stav:** rozpracováno.

### 3. Konfigurovatelný rozsah slideru výkonu
Uživatelsky nastavitelné meze slideru 40014 v options flow:
- PRO série → P_min / P_max ve Wattech
- otáčkové série → Rpm_min / Rpm_max v otáčkách

Uživatel si rozsah upraví podle své TČ. Lze zúžit i rozšířit, oběma směry,
v rámci platného rozsahu protokolového registru — bez bezpečnostního
varování (40014 je strop/požadavek, meze hlídá TČ sama). Default = jmenovitý
rozsah; rozšíření dolů klidně až k ~1000 rpm.
**Stav:** nápad.

### 4. Podmíněné zobrazení chyby na hlavní stránce
Na view „Pohled" karta s popisem chyby (30021 / 30023) a tlačítkem reset
(potvrzení poruchy, 40006 bit 5). Zobrazí se **jen když je chyba aktivní**,
a to nahoře, aby ji uživatel nepřehlédl. Conditional card.
**Stav:** nápad.

### 5. Debounce zápisu do Modbusu (slider + tlačítka)
Při změně number entity (slider i tlačítka +/−) neposílat zápis okamžitě,
ale s 2s prodlevou. Každá další změna odpočet resetuje; skutečný zápis
proběhne až po 2 s klidu. PendingValue zajistí okamžitou vizuální odezvu.
Výsledek: rychlé úpravy (opakované klikání, třesoucí ruka) → jeden čistý
zápis místo spršky. Generické pro všechny `AcondNumber`.
Technicky: `async_call_later`, cancel + reschedule při každé změně.
**Stav:** nápad (technické řešení promyšleno).

### 6. Readout 30020 a 30024 u slideru výkonu
Vedle slideru 40014 zobrazit registr 30020 (strop přijatý dispatcherem)
a 30024 (skutečné otáčky/výkon). Trojice 40014 → 30020 → 30024 =
„žádám / přijato / děje se". Odhalí out-of-range zápis (40014 vs 30020)
i sezónní modulační podlahu (30020 vs 30024). Realizace přes built-in
`history-graph` se třemi entitami.
Volitelně k tomu krátká kvalitativní nápověda u slideru (`<details>`):
minimální dosažitelný výkon je v létě vyšší než v zimě.
**Stav:** nápad.

### 7. Oprava: carry-forward při timeoutu čtení registru
Při timeoutu čtení registru staví `async_update_data` nový prázdný
`data = {}` → klíč zmizí → entita blikne na „unknown" → poškodí součty
`utility_meter` (potvrzeno u energetických senzorů 30035 / 30039).
Oprava: při přechodném selhání čtení přenést předchozí hodnotu ze
`self.data`. Potvrzeno diagnostikou z debug logu (24. 5. 2026).
**Stav:** oprava bugu — priorita.

---

## Později (mimo 0.2.0)

Sem patří položky pro pozdější verze. Větší celky (např. samostatná
integrace `acond_regulation`) se vedou mimo tento soubor.
