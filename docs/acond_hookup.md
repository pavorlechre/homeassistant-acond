# Acond ↔ MaR — dashboard hookup (kontrakt + jak to funguje)

**Hookup = napojení.** Acond integrace si na konec svého dashboardu přilepí okno
„Regulace" z balíčku MaR (`acond_regulator`). Když MaR není, vloží místo něj teaser
s odkazem na repozitář. Stav 0.1.0.

---

## Acond strana (generátor `lovelace_dashboard.py`)

- Při startu přečte **ručně udržovaný `acond_dashboard.yaml`** (ZÁKLAD — zůstává nedotčený).
- Na konec `views` přilepí příspěvek MaR (nebo teaser, když MaR není).
- Zapíše `acond_dashboard.generated.yaml` a ten **zaregistruje**.
- `__init__.py` se nemění — volá pořád `async_register_dashboard(hass)`, jen ta funkce teď nejdřív složí dashboard.
- **Detekce přes existenci souboru** → nezávisí na pořadí setupu; změna se projeví po restartu.
- **Fail-safe:** když cokoli selže, zaregistruje se čistý základ a integrace běží dál (skládání je jen nadstavba).

## Kontrakt (MaR strana)

- MaR ukládá příspěvek na **`custom_components/acond_regulator/dashboard/views.yaml`**.
- Obsah = **seznam view dictů** (1–2 okna; preferováno). Akceptuje se i jediný view dict — Acond ho normalizuje.
- Karta vyžaduje HACS **`custom:apexcharts-card`** (jinak se graf nevykreslí).

## Pojmenování (ať se to neplete)

- **`acond_regulator` = doména i složka** integrace MaR → tahle cesta je v kontraktu a v Acond kódu natvrdo (jedno místo v `ADDONS` / `contribution_files`).
- **`MaR` = jen název zařízení** → entity mají `sensor.mar_*`, `number.mar_*`. Je to UI, ne cesta. Žádný konflikt s doménou.
- Kdyby se složka jmenovala jinak (`acond_regulation`), stačí změnit dvě cesty v `contribution_files`.

## Teaser (když MaR není)

Markdown karta s nápisem „funguje až po instalaci Acond Regulator (MaR)" + odkaz:
`https://github.com/pavorlechre/acond_regulator`.

## DŮLEŽITÉ — odebrat ruční okno ze základu

Pokud je v `acond_dashboard.yaml` (základ) ještě **ručně přidané okno „Regulace"**
(to, co jsme vkládali dřív), **smaž ho** — generátor ho teď přidává sám, jinak by se
zdvojilo.

## Nasazení (ritual)

1. Smaž `__pycache__`.
2. Nahraj soubory.
3. **Plný restart HA** (ne reload).

Bez MaR uvidíš vzadu okno „Regulace" s teaserem; po nakopírování MaR souborů a
restartu se rozsvítí obsah.

## Otevřené

- ~~Potvrdit GitHub handle a název repo~~ — potvrzeno: `pavorlechre/acond_regulator`.
- Zápis do `DECISIONS.md` / `CHANGELOG.md` (skládací dashboard, kontrakt add-onů, detekce přes soubor) — až po ověření na železe.
