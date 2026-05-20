# Migrace z YAML Modbus konfigurace na integraci Acond

[![English version](https://img.shields.io/badge/English-EN-blue.svg)](MIGRATION.en.md)

Tento dokument popisuje, jak přejít z **ručně psané YAML modbus** konfigurace v `configuration.yaml` na **integraci Acond Heat Pump**. Postup s pomocí AI asistenta zvládneš za cca **30–60 minut** podle množství automatizací a šablon.

---

## Pro koho je tento dokument

Pokud máš v `configuration.yaml` blok `modbus:` pro Acond tepelné čerpadlo a chceš:

- ✅ Zbavit se ručního YAML hokejování
- ✅ Získat **automaticky vytvořený Lovelace dashboard**
- ✅ Dostat **117+ entit** místo svých 10–20 ručně psaných
- ✅ Integrované funkce: dekódování chyb, COP, statistiky, Options Flow
- ✅ Multijazyčné UI (čeština + angličtina)

…tak jsi tady správně.

---

## Než začneš

### Co budeš potřebovat

- Home Assistant **2024.11.0** nebo novější
- Nainstalovaný **HACS**
- Přístup k **panelu tvého tepelného čerpadla** (na chvíli vypneš/zapneš Modbus komunikaci)
- AI asistent — **doporučujeme Claude** (Anthropic), kvalitu testoval autor integrace na své vlastní migraci. Alternativy: ChatGPT, Gemini.
- Cca **30–60 minut soustředěné práce** (ne uprostřed vaření)

### ⚠️ Důležitá upozornění

> **Acond TČ přijímá pouze JEDNOHO Modbus klienta současně.** Pokud máš v `configuration.yaml` blok `modbus:` aktivní a zároveň nainstaluješ Acond integraci, **integrace se nepřipojí** (komunikační slot je zabraný).
>
> Proto musíme YAML modbus **odstranit DŘÍVE**, než nainstalujeme novou integraci.

> **Staré YAML modbus a novou integraci NELZE provozovat současně**, ani je nelze nějak "překlenout". Postup je `staré pryč → restart → nová instalace`.

> **Některé staré entity přestanou existovat.** Tvoje automatizace, skripty, šablony a dashboardy, které je používají, **přestanou fungovat**. Z toho důvodu **musíš mít v záloze**:
> - Plný HA backup (krok 1)
> - Kopii původního `configuration.yaml` (krok 2)

---

## Stručná osnova

Než se pustíš do detailů, tady je celý postup ve zkratce:

1. **Zazálohuj celý HA** — plný backup, návrat k původnímu stavu, kdyby cokoli selhalo.
2. **Ulož si kopii `configuration.yaml`** — textovou kopii stranou; AI ji bude později potřebovat k mapování entit.
3. **Nech AI vyčistit `configuration.yaml`** — odstranění bloku `modbus:` a souvisejících template entit. Starý Modbus nelze zachovat — nejde to.
4. **Restartuj HA s očištěným configem** — Modbus komunikace se vypne, staré entity zmizí.
5. **Vypni a zapni Modbus na panelu TČ** — uvolní komunikační slot, nastav timeout na 4:30.
6. **Nainstaluj integraci Acond** — zadej IP čerpadla a sérii, nová integrace začne pracovat.
7. **Zkontroluj nový dashboard a entity** — ověř, že se vytvořil ovládací panel a entity mají stavy.
8. **Vygeneruj AI kontext (Full HA)** — export aktuálního stavu HA pro AI asistenta.
9. **Pošli AI tři věci** — původní `configuration.yaml`, AI kontext a připravený prompt; AI vytvoří mapping a patche.
10. **Aplikuj patche z AI** — oprav postižené automatizace, skripty, šablony a dashboardy podle návrhu AI.
11. **Vyčisti zbytečné funkcionality** — požádej AI o seznam redundantních template entit a smaž schválené.

📖 **Podrobný postup ke každému kroku je níže.**

---

## Podrobný postup

### 1. Zazálohuj celý HA

Než cokoli změníš, vyrob **plný backup** Home Assistantu — to je tvoje záchranná síť pro návrat k původnímu stavu.

1. **Settings → Backups → Create backup**
2. Zvol **Full backup**
3. Počkej, než se backup dokončí (podle velikosti instalace 1–5 minut)

Kdyby cokoli během migrace selhalo, z tohoto backupu obnovíš HA do stavu před migrací.

### 2. Ulož si kopii `configuration.yaml`

Tohle **není HA backup** (ten jsi udělal v kroku 1). Tady potřebuješ **samostatnou textovou kopii** souboru `configuration.yaml`, protože **AI ji bude v kroku 9 potřebovat** — uvidí z ní, jak se původní entity jmenovaly a které Modbus registry obsluhovaly.

Otevři **File Editor** (nebo Studio Code Server, nebo SSH) v HA a vyrob kopii `/config/configuration.yaml`:

- File Editor: pravý klik → Duplicate → přejmenuj na `configuration.yaml.backup_pred_acond`
- Nebo přes terminál: `cp /config/configuration.yaml /config/configuration.yaml.backup_pred_acond`

**Bez této kopie AI nebude moct mapovat staré entity na nové.**

### 3. Nech AI vyčistit `configuration.yaml`

> 💡 **Tip:** Tohle můžeš nechat na AI, ne dělat ručně. AI udělá menší chybu než tvůj copy-paste.

**Postup:**

1. Otevři chat s AI (Claude / ChatGPT / Gemini)
2. Vlož celý obsah svého `configuration.yaml`
3. Napiš tento prompt:

```
Jsem v procesu migrace z ručního YAML Modbus na novou HA 
integraci Acond. Potřebuji od tebe upravený configuration.yaml 
bez Modbus věcí.

Konkrétně odstraň:
1. Celý blok modbus: (sensors, climates, switches, vše uvnitř)
2. Všechny template senzory, které se odkazují na sensor.ACOND_*
3. Všechny template binary_sensory, které čtou bity ACOND_TC_status
4. Všechny template switche, které volají modbus.write_register.
   POZOR: pokud měl můj modbus: blok jméno (např. name: Acond_EVI),
   odstraň i template switche, které se na toto jméno odkazují
   přes parametr "hub:". Pokud by takový switch zůstal, HA při 
   restartu nahlásí chybu.

Co naopak ZACHOVEJ:
- automation: !include, script: !include, scene: !include
- default_config:, frontend:, themes:
- utility_meter:, statistics:, rest: (které nemají s Acondem nic)
- Vlastní template senzory, které nesouvisí s Acondem
- Cokoli ostatní, co se Acondem nesouvisí

Pošli mi výsledný configuration.yaml.
```

4. Zkopíruj výsledný `configuration.yaml`, který ti AI pošle
5. **Vlož ho zpět do HA** (přes File Editor)
6. **Ulož soubor**, ale **NERESTARTUJ ZATÍM HA** — restart je až další krok

> ⚠️ **Starý Modbus nelze zachovat.** Není možné mít YAML modbus a integraci současně (TČ přijímá jen jednoho klienta). Postup je jednosměrný: staré pryč → nová integrace.

### 4. Restartuj HA s očištěným configem

1. **Settings → System → Restart** (restart Core stačí)
2. Počkej na restart (cca 1–2 minuty)

**Co se právě stalo:**
- ✅ Staré Modbus entity zmizely z HA
- ✅ Modbus slot na TČ se uvolnil
- ❌ Tvoje automatizace, skripty a dashboardy s odkazy na staré entity jsou **rozbité** (entity neexistují)
- ✅ YAML kód automatizací zůstal v souborech (`automations.yaml`, atd.) — AI ho v kroku 9 uvidí

### 5. Vypni a zapni Modbus na panelu TČ

> 🔑 **Tento krok zachrání 30 minut frustrace.**

Acond TČ má v paměti, že **byl Modbus klient připojený**. I když HA restartoval, **panel TČ to nevidí**. Pokud bys teď rovnou pokračoval k instalaci, integrace by se možná **nepřipojila** (slot stále "obsazen" z TČ perspektivy).

**Postup:**

1. Otevři **webové rozhraní tepelného čerpadla** (`http://<ip_tc>` — typicky `10.10.x.x` nebo `192.168.x.x`)
2. Najdi nastavení **Modbus TCP**
3. **Vypni Modbus TCP komunikaci** (typicky checkbox nebo přepínač)
4. Ulož nastavení
5. Počkej **5 vteřin**
6. **Zapni Modbus TCP komunikaci** znovu
7. **Nastav timeout na 4:30 (4 minuty 30 sekund) nebo víc** — bez toho ti integrace bude občas vypadávat
8. Ulož nastavení

Tímto je slot **opravdu volný** a TČ je připraveno přijmout nového klienta.

### 6. Instalace integrace Acond

1. V HA otevři **HACS**
2. **Integrace** → **⋮ menu** → **Vlastní repozitáře**
3. Přidej URL: `https://github.com/pavorlechre/homeassistant-acond`
4. Kategorie: **Integrace**
5. Klikni **Přidat**
6. Najdi **Acond Heat Pump** v seznamu HACS integrací
7. Klikni **Stáhnout**
8. Restartuj HA (Settings → System → Restart)
9. Po restartu: **Settings → Devices & Services → Add Integration**
10. Vyhledej **Acond Heat Pump**
11. Vyplň:
    - **IP adresa** tvého TČ (např. `192.168.1.100`)
    - **Série** — `Grandis / Economis` nebo `PRO`
12. Klikni **Submit**

### 7. Kontrola nového dashboardu a entit

1. V bočním menu HA hledej **"Acond"** — nový dashboard se měl vytvořit automaticky
2. **Otevři ho** — měl bys vidět:
   - Pohled (overview) — teploty, výkon, COP
   - Ovládání — setpointy, mode přepínače
3. **Settings → Devices & Services → Acond Heat Pump** — měl bys vidět:
   - Verze: 0.1.0
   - 1 zařízení "Acond"
   - 117 entit
   - Žádné chyby

**Pokud něco selhalo:**
- ❌ "Nelze se připojit na TČ" → zkontroluj, že IP je správná a TČ má aktivní Modbus TCP (kroky 4)
- ❌ Entity všechny `unavailable` → stejný problém s připojením, nebo TČ má timeout pod 4:30
- ❌ Dashboard chybí → otevři `Settings → Dashboards`, "Acond" by tam měl být

### 8. Vygeneruj AI kontext

Teď je správný čas exportovat **stav HA** pro AI.

1. **Settings → Devices & Services → Acond Heat Pump → Acond** (zařízení)
2. V seznamu entit najdi tlačítko **Generate AI Context (Full HA)**
3. Klikni na něj
4. Počkej **3–10 sekund**
5. **V notifikacích** se objeví zpráva se **stahovacím odkazem**
6. Klikni → soubor `full_<datum>.md` se stáhne

> ⚠️ **Před odesláním AI si soubor otevři** v textovém editoru. Integrace **automaticky redaktuje** hesla, tokeny atd., ale **prohlédni si ho rychle** — pokud máš někde citlivý údaj (např. IP tvého routeru, MAC adresa, který nechceš sdílet), můžeš ho ručně z textu odstranit.

### 9. Pošli AI tři věci současně

Otevři nový chat s AI a pošli **najednou**:

1. ✅ **Zálohovaný původní `configuration.yaml`** (z kroku 1)
2. ✅ **Vygenerovaný `full_*.md` AI kontext** (z kroku 8)
3. ✅ **Tento prompt:**

```
Migruji z YAML Modbus Acond na HA integraci Acond Heat Pump.

Posílám ti:
1. Můj PŮVODNÍ configuration.yaml (před migrací) — pomocí něj 
   poznáš, jak se původní entity jmenovaly a které Modbus 
   registry obsluhovaly
2. Vygenerovaný AI kontext po migraci — zobrazuje aktuální 
   stav HA: nové Acond entity, automatizace, skripty, šablony, 
   scény, lovelace dashboardy

Tvůj úkol:

A) Vytvoř mapping mezi STARÝMI a NOVÝMI entitami:
   - Stará: sensor.ACOND_T_act_TUV  (z YAML modbus)
   - Nová:  sensor.acond_30005_t_act_tuv  (z integrace)
   - Mapování dělej podle Modbus adresy registru, ne podle 
     názvu entity. Adresa je v entity_id nové entity (např. 
     30005) a v `address:` poli původního YAML.

B) Vygeneruj YAML patche pro VŠECHNY automatizace, skripty, 
   scény, šablony, lovelace karty, které používají staré entity:
   - Pro každou postiženou položku napiš:
     * Co se mění (název položky, ID)
     * Kompletní opravený YAML kód (k vložení do automations.yaml 
       nebo přes UI editor)
     * Krátké vysvětlení změny

C) Označ funkcionality, které jsou nyní s integrací 
   REDUNDANTNÍ a doporuč k odstranění:
   - Pokud jsem si v configuration.yaml ručně psal template 
     binary_sensor pro rozkládání bit_0 až bit_12 ACOND_TC_status, 
     integrace to už dělá sama → doporuč odstranit
   - Pokud jsem si počítal COP přes template senzor, integrace 
     má vlastní → upozorni, že je redundantní (já si rozhodnu, 
     zda zachovat nebo smazat)
   - Atd.

Formátuj odpověď jako:
1. Nejdřív tabulka mappingu (1-2 strany)
2. Pak sekce "Patche pro automatizace" 
3. Pak "Patche pro skripty/scény"
4. Pak "Patche pro šablony"
5. Pak "Patche pro Lovelace dashboardy"
6. Pak "Redundantní funkcionality"

Buď konzervativní — pokud si nejsi jistý, raději mapping NEdělej 
a označ jako "ručně ověřit".
```

### 10. Aplikuj patche z AI

AI ti pošle **strukturovanou odpověď** s opravami. Postup:

**Pro každou položku z AI odpovědi:**

1. **Otevři příslušnou položku v HA** (Settings → Automations → konkrétní automatizace)
2. Klikni **⋮ → Edit in YAML**
3. **Smaž starý YAML** a vlož **opravený** od AI
4. **Save**
5. **Otestuj** ručně — spusť automatizaci a zkontroluj, jestli funguje

> 💡 **Tip:** Začni s **jednou nebo dvěma jednoduchými automatizacemi**. Když fungují, přejdi na složitější. Nikdy nedělej "Apply all" naráz — kontroluj postupně.

> 💡 **Pokud má AI nejistotu:** Někdy AI napíše *"Mapping této entity je nejistý — ručně ověř"*. To znamená, že **musíš sám rozhodnout**. Typicky pomůže se podívat na **friendly_name** staré entity v původním YAML a najít to nejvíc odpovídající v nové integraci.

### 11. Vyčisti zbytečné funkcionality

Po aplikaci patchů máš v HA stále jeden zbytek — **template senzory a binary_sensory**, které jsi ručně psal v `configuration.yaml`. Některé z nich integrace teď dělá nativně (např. rozkládání bitů, COP), takže jsou **redundantní**.

**Postup:**

1. V tom samém chatu s AI napiš:

```
Děkuji za patche. Teď: 

Pošli mi seznam template senzorů, binary_sensorů a 
input_helperů (input_boolean, input_number, atd.), které 
podle tvého původního configuration.yaml byly POMOCNÉ pro 
Modbus integraci, ale nyní jsou REDUNDANTNÍ — integrace 
Acond je dělá nativně.

U každého napiš:
- Název položky v configuration.yaml
- Nahrazena kterou novou entitou
- Doporučení: smazat / zachovat (proč)

Buď opatrný — pokud si nejsi jistý, doporuč zachování.
```

2. AI ti odpoví seznamem.
3. **Vyhodnoť si sám** každou položku:
   - ✅ Smaž jen ty, kde si jistý
   - ❌ Necháš na pokoji ty, kde jsi v pochybnostech (lepší pár zbytečných entit než ztracená funkcionalita)
4. **Smaž** schválené z `configuration.yaml` (nebo `templates.yaml`, kdekoli máš)
5. **Restart HA** po cleanupu

### Hotovo 🎉

Tvoje HA má teď:
- ✅ Acond integrace s 117 entit
- ✅ Auto-generovaný dashboard
- ✅ Funkční automatizace, skripty, scény (s opravenými entity_id)
- ✅ Vyčištěný `configuration.yaml`
- ✅ Zálohu (kdyby něco)

**Dalo to práci, ale věřím, že budeš spokojený(á).** 🙌

Pokud bys měl s migrací jakýkoli problém — neváhej **hlásit issue** na [GitHubu](https://github.com/pavorlechre/homeassistant-acond/issues).

---

## Po migraci — drobnosti

### Backup `configuration.yaml.backup_pred_acond`

**Necháš si ho?** Doporučuji ano, alespoň 30 dní. Dává ti to plnou jistotu, kdybys nakonec chtěl migraci vzít zpátky (nepravděpodobné, ale zdravé).

Po 30 dnech, když je vše stabilní, smaž.

### Adresa TČ

Pokud změníš router a TČ dostane jinou IP, **neinstaluj integraci znovu**. Místo toho:

1. **Settings → Devices & Services → Acond Heat Pump**
2. Klikni **⋮ tři tečky** vedle "Acond (xx.xx.xx.xx)"
3. **Konfigurovat**
4. Změň IP → Submit
5. Integrace se reloadne automaticky

### Modbus timeout

Toto je nastavení **na panelu TČ**, ne v HA. Pokud bys časem **omylem snížil** Modbus timeout pod 4:30, integrace začne vypadávat (entity → `unavailable` občas). Vrať na 4:30+.

---

## Co když to nefunguje

### Entity všechny `unavailable`

1. Settings → System → Logs → filtruj `acond`
2. Hledej **WARNING** nebo **ERROR**
3. Typicky:
   - "Cannot connect to host" → špatná IP / TČ Modbus vypnutý
   - "Connection timeout" → TČ timeout pod 4:30

### Některé entity `unavailable`, jiné OK

To je v pořádku. Starší firmware TČ nemusí podporovat všechny registry. Affected entity se **automaticky aktivují**, když Acond vydá update firmware.

### AI mapping je nesprávný

To se občas stává, zejména u **kreativně pojmenovaných** entit. Postup:

1. **Najdi v původním `configuration.yaml`** Modbus adresu (např. `address: 6`)
2. Acond integrace má entity ve tvaru `<platform>.acond_<address>_<key>` — adresa **30006** odpovídá Modbus `address: 6` (registry 30000–39999 jsou input registers, 40000–49999 jsou holding registers — adresa 6 v input = 30006, v holding = 40006)
3. **Najdi novou entitu** se shodným číslem registru

### Něco kompletně rozbité

1. **Settings → Backups** → restore z plného HA backup před migrací
2. **Hlásit issue** na GitHubu (s logem)
3. **Možná zkusit znovu** za pár dní, integrace dostává update

---

## Otázky a odpovědi

**Q: Mohu starý YAML Modbus a integraci zkusit současně?**  
A: **Ne.** Acond TČ přijímá pouze 1 Modbus klienta. Integrace ani YAML by neměli k dispozici.

**Q: Kolik času migrace zabere?**  
A: Cca **30–60 minut** podle množství automatizací. Kroky 1–7 zaberou max 15 minut. Kroky 8–11 závisí na velikosti HA.

**Q: Co když nemám záložní `configuration.yaml`?**  
A: AI mapování bude **mnohem horší** (musí hádat z friendly_name a kontextu). Doporučuji **HA snapshot restore** zpět, vyrobit zálohu, znovu zkusit.

**Q: Mohu některé entity z nové integrace přejmenovat?**  
A: Jen v UI (Friendly Name), ne entity_id. Entity_id je závazný formát `<platform>.acond_<register>_<key>`. Pokud bys ho měnil, AI při budoucí migraci na novější verzi by ti nezvládala mapping.

**Q: Co když najdu chybu v integraci během migrace?**  
A: Hlas issue na [GitHubu](https://github.com/pavorlechre/homeassistant-acond/issues) **s přiloženým AI kontextem** — autor uvidí, co máš, a dovede pomoci.

---

## Příklad — reálná migrace

Konkrétní příklad migrace z reálného `configuration.yaml` (Pavle Vorlech, autor integrace, 2026):

**Před:**
- 5 modbus climates (TUV, T_zpatecka, atd.)
- 9 modbus sensors
- 2 modbus switches
- 8 template binary_sensorů pro bity TC_status
- 1 template switch pro PWM control
- 1 template sensor pro regulation_mode

**Po:**
- 0 modbus záznamů v `configuration.yaml`
- 117 entit z Acond integrace
- Vyčištěn binary_sensor a switch template
- Zachovány: rest senzor `Active power Lipany`, utility_meter, REST forecast (nesouvisí s Acondem)

**Časová investice:** 45 minut soustředěné práce s AI asistentem.

**Výsledek:** Funkční integrace s automaticky generovaným dashboardem + zachované původní automatizace.

---

## Děkujeme za vyzkoušení! 🙌

Pokud ti tato dokumentace pomohla, [hvězdička na GitHubu](https://github.com/pavorlechre/homeassistant-acond) je velmi vítaná.

Pokud máš jakékoli otázky, hlas je v [Issues](https://github.com/pavorlechre/homeassistant-acond/issues) — autor i AI asistent jsou připraveni pomoct.
