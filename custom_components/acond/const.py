from __future__ import annotations
from dataclasses import dataclass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfPower, UnitOfEnergy, PERCENTAGE

DOMAIN = "acond"
VERSION = "0.0.1"
CONF_HOST = "host"
CONF_MODEL = "model"
CONF_HP_SERIES = "hp_series"       # "PRO" nebo "Grandis / Economis" – volí uživatel při instalaci
DEFAULT_SCAN_INTERVAL = 15         # sekund

# ---------------------------------------------------------------------------
# Chybové kódy – základní (registr 30021)
# ---------------------------------------------------------------------------
ERROR_CODES: dict[int, str] = {
    0: "OK",
    1: "A16 – Low pressure",
    2: "A12 – High pressure",
    3: "A01 – Outlet temperature low",
    4: "A02 – Condensing temperature high",
    5: "A07 – Driver hardware fault",
    6: "A03 – IP address is not valid",
    7: "A05 – Driver system fault",
    9: "A13 – DHW sanitation too long",
    10: "A04 – Return water temperature low",
    11: "A10 – Outlet water temperature high",
    12: "A14 – Return water temperature high",
    13: "A08 – Suction temperature low",
    14: "A09 – Defrosting too long",
    15: "W07 – EEV too open",
    16: "W01 – Superheat low",
    17: "W02 – Driver compressor fault",
    18: "W00 – Defrosting too long",
    19: "W04 – Too many defrosts",
    20: "W05 – Ground collector temp low",
    21: "W12 – Fan running fault",
    22: "W06 – Sensors blocked",
    23: "HW1 – Heating DHW too long",
    24: "W09 – Discharge temperature high",
    25: "SYS – Compressor running fault",
    26: "W11 – Suction temperature high",
    27: "W16 – Flow through heat exchanger low",
    28: "SH1 – Outlet temperature low",
    29: "CMP – Compressor running fault",
    30: "PFC – Driver PFC fault",
    31: "ELC – Driver microelectronics fault",
    35: "W08 – Max number of comp starts",
    36: "W17 – Evaporating temperature low",
    40: "P05 – Domestic hot water sensor",
    41: "P04 – Suction line temp sensor",
    42: "P02 – Return water temp sensor",
    43: "P06 – Evaporator temperature sensor",
    44: "P03 – Room 2 temperature sensor",
    45: "P01 – Solar collector temp sensor",
    46: "P07 – Pool temperature sensor",
    47: "P09 – Room temperature sensor",
    48: "P08 – Outdoor temperature sensor",
    49: "P10 – Outlet water temp sensor",
    50: "PER – Communication with perif lost",
    51: "P11 – Mixing valve temperature sensor",
    52: "P15 – Low pressure sensor",
    53: "P16 – High pressure sensor",
    54: "P13 – Discharge line temp sensor",
    55: "P17 – Domestic hot water sensor 2",
    56: "A19 – Heating DHW too long 2",
    60: "A18 – Suction temp or LP during defrost low",
    61: "A11 – ERR communication with driver",
    62: "A15 – IGBT overheat (driver)",
    63: "P99 – Blocked – unpaid",
    64: "W00 – OK",
    90: "W10 – Low flow during defrost/cooling",
    91: "W14 – Big difference return and DHW temperature",
    92: "W13 – Too many restarts of PLC",
    93: "W15 – SD card fault",
    94: "A17 – Temperature of storage tank low",
    95: "ST1 – Soft fault in the engine room",
    96: "ST2 – Serious fault in the engine room",
}

# ---------------------------------------------------------------------------
# Chybové kódy – driver (registr 30023)
# ---------------------------------------------------------------------------
DRIVER_ERROR_CODES: dict[int, str] = {
    0: "OK",
    1: "Stuck relay",
    2: "DLT temperature sensor fault",
    3: "Communication lost",
    4: "EEPROM",
    5: "AC overcurrent",
    6: "AC overvoltage",
    7: "Comp U current sensor fault",
    8: "Comp V current sensor fault",
    9: "Comp W current sensor fault",
    10: "PFC current sensor fault",
    11: "IPM temperature sensor fault",
    12: "PFC temperature sensor fault",
    13: "IPM overheat",
    14: "IGBT overheat",
    15: "Compressor code fault",
    16: "Compressor HW overcurrent",
    17: "AC undervoltage",
    18: "DC overvoltage",
    19: "DC undervoltage",
    20: "HP/LP switch",
    21: "Input loss of phase fault",
    22: "Compressor U phase overcurrent",
    23: "Compressor overload",
    24: "Compressor DLT over temperature",
    25: "Compressor IPM desat protection",
    26: "Compressor V phase overcurrent",
    27: "Compressor W phase overcurrent",
    28: "Compressor loss of phase",
    29: "Compressor lost rotor",
    30: "Compressor startup failure",
    31: "A AD fault",
    32: "A wrong addressing",
    33: "Modbus VSS communication fault",
    34: "Compressor lost rotor 2",
    35: "Compressor lost rotor 3",
    36: "PFC HW overcurrent",
    37: "PFC SW overcurrent",
    38: "PFC overvoltage",
    39: "n/a",
}

# ---------------------------------------------------------------------------
# Režimy TČ (registr 30014)
# ---------------------------------------------------------------------------
HP_MODES: dict[int, str] = {
    0: "Automatický",
    1: "Pouze TČ",
    3: "Pouze bivalence",   # dříve "Pouze aux. topení", sjednoceno s názvem switche bit 2
    4: "Vypnuto",
    5: "Manuální",
    6: "Chlazení",
}

# ---------------------------------------------------------------------------
# Typy regulace (registr 30015)
# ---------------------------------------------------------------------------
REG_TYPES: dict[int, str] = {
    0: "AcondTherm",
    1: "Ekvitermní",
    2: "Standard",          # dle Acond názvosloví – zobrazeno na panelu TČ jako Standard
}

# ---------------------------------------------------------------------------
# Mapa: switch bit (40006) → číselná hodnota v sensoru 30014 hp_mode
# ---------------------------------------------------------------------------
# Použito v switch.py pro single source of truth: is_on čte ze zrcadla
# (30014 hp_mode) místo udržování in-memory stavu. Bity 0-4 jsou exclusive
# (vždy jen jeden režim aktivní).
#
# DŮLEŽITÉ: coordinator.data["hp_mode"] drží SUROVÉ ČÍSLO (0, 1, 3, 4, 6),
# nikoli text. Text z HP_MODES se aplikuje až na úrovni sensor entity při
# displayování. Tato mapa proto vrací číslo, které switch.is_on porovnává
# přímo s coordinator data. Klíče (bity) musí korespondovat s indexy v
# HP_MODES – jen že pozor, bit ≠ index (např. bit 2 → HP_MODES[3]).
MODE_BY_BIT: dict[int, int] = {
    0: 0,   # bit 0 → hp_mode 0 = Automatický
    1: 1,   # bit 1 → hp_mode 1 = Pouze TČ
    2: 3,   # bit 2 → hp_mode 3 = Pouze bivalence
    3: 4,   # bit 3 → hp_mode 4 = Vypnuto
    4: 6,   # bit 4 → hp_mode 6 = Chlazení
}

# ---------------------------------------------------------------------------
# Mapa: zápisová entita (key z 40xxx) → zrcadlový sensor (key z 30xxx)
# ---------------------------------------------------------------------------
# Použito v number.py / switch.py / select.py pro single source of truth.
# Hodnoty entity (native_value / is_on / current_option) se čtou ze zrcadla
# v coordinator.data, ne z in-memory _last_value.
#
# Záměrně NEZAHRNUTO (vyžaduje speciální zacházení):
#   - t_corr_*  – korekce z ext. čidla, sémanticky nesedí se zrcadlem
#                  (ext. teplota vs. aktuální čidlo TČ). Ponecháno in-memory.
#   - tc_set_bit_0..4 – mode switche, čteno přes MODE_BY_BIT a hp_mode
#   - tc_set_bit_5, 8 + reset_plc_set – buttony bez state, není co zrcadlit
WRITE_KEY_TO_MIRROR_KEY: dict[str, str] = {
    # --- Number entity (NUMBER_DEFINITIONS) ---
    "t_set_indoor1":          "t_set_indoor1",      # 40001 → 30001
    "t_set_indoor2":          "t_set_indoor2",      # 40003 → 30003
    "t_set_tuv":              "t_set_tuv",          # 40005 → 30005
    "t_set_water_back":       "t_set_water_back",   # 40008 → 30008
    "t_set_pool":             "t_set_pool",         # 40012 → 30013
    "t_set_water_outlet":     "t_set_water_outlet", # 40013 → 30019
    "comp_capacity_max_set":  "comp_capacity_max_set",   # 40014 → 40014 (FC3 self-mirror, viz KROK 2.5)
    "pwm_set":                "pwm_set",                 # 40015 → 40015 (FC3 self-mirror, viz KROK 2.5)
    "silent_mode_start_set":  "silent_mode_start",  # 40019 → 30033
    "silent_mode_stop_set":   "silent_mode_stop",   # 40020 → 30034
    # --- Switch entity (SWITCH_DEFINITIONS) – celé registry ---
    "manual_pwm_set":         "manual_pwm",         # 40016 → 30026
    "manual_eh_set":          "manual_eh",          # 40017 → 30031
    "silent_mode_set":        "silent_mode",        # 40018 → 30032
    # --- Switch entity – bity 6, 7 v 40006 ---
    # Read-back z 30007 tc_status, příslušný bit. Speciální zacházení v switch.py.
    "tc_set_bit_6":           "tc_status",          # bit 6 (Solár)
    "tc_set_bit_7":           "tc_status",          # bit 7 (Bazén)
    # --- Select entity (SELECT_DEFINITIONS) ---
    "sel_regulation_type":    "regulation_type",    # 40007 → 30015
}

# ---------------------------------------------------------------------------
# Holding registry čtené přímo přes FC3 (KROK 2.5 – FC3 read-back)
# ---------------------------------------------------------------------------
# Některé 30xxx zrcadla pro 40xxx setpointy nejsou pasivní – TČ má vlastní
# řídící logiku (např. 30020 dispatcher cap pro otáčky kompresoru, 30025
# aktuální PWM oběhového čerpadla podle fáze provozu). V takovém případě
# je sémanticky správné číst přímo holding registr 40xxx přes FC3.
#
# Diagnostika z 9.-10.5.2026:
# - 30020 reaguje na zápis do 40014 s 3,5h ramp-up (= dispatcher cap)
# - 30025 sám moduluje 45/60/100 % podle fáze (klid/topení/TUV)
# - test FC3 čtení 40014 ověřen na kamarádově TČ (10.5.2026, address: 13,
#   data_type: int16, slave: 1) – Acond TČ FC3 pro holding registry plně
#   podporuje, hodnoty drží přesně dle zápisu.
#
# Coordinator polluje tyto registry stejným intervalem jako input registry
# (DEFAULT_SCAN_INTERVAL = 15 s). Hodnoty se ukládají do coordinator.data
# pod stejným klíčem (= název Number entity), což znamená že WRITE_KEY_TO_MIRROR_KEY
# obsahuje self-mapping (key → key) pro tyto entity.
#
# Položka: (adresa, key, scale, signed)
HOLDING_REGISTERS_TO_POLL: list[tuple[int, str, float, bool]] = [
    (40014, "comp_capacity_max_set", 1.0, False),  # max otáčky/výkon kompresoru
    (40015, "pwm_set",               1.0, False),  # nastavená rychlost ob. čerpadla
]

# ---------------------------------------------------------------------------
# Třída tepelného výkonu (registr 30044)
# Hodnoty 3, 4, 5 nejsou dokumentovány výrobcem – rezerva pro budoucí modely
# ---------------------------------------------------------------------------
THERMAL_POWER: dict[int, str] = {
    1: "12 kW",
    2: "5 kW",
    6: "20 kW",
}

# ---------------------------------------------------------------------------
# TC_status bity (registr 30007)
# ---------------------------------------------------------------------------
TC_STATUS_BITS: dict[int, str] = {
    0: "hp_on",
    1: "hp_running",
    2: "hp_alarm",
    3: "dhw_heating",
    4: "circuit1_pump",
    5: "circuit2_pump",
    6: "solar_circulation",
    7: "pool_circulation",
    8: "defrost",
    9: "bivalence",
    10: "summer_mode",
    11: "brine_pump",       # solankové čerpadlo
    12: "cooling",
}

# ---------------------------------------------------------------------------
# HP_component_status bity (registr 30045)
# ---------------------------------------------------------------------------
HP_COMPONENT_BITS: dict[int, str] = {
    0: "compressor",
    1: "fan",
    2: "primary_pump",
    3: "reverse_valve",
}

# ---------------------------------------------------------------------------
# Definice senzorů
# ---------------------------------------------------------------------------
@dataclass
class AcondSensorDefinition:
    key: str
    name: str
    address: int
    scale: float = 1.0
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    signed: bool = True
    dint: bool = False  # True = 32bit přes dva po sobě jdoucí registry


SENSOR_DEFINITIONS: list[AcondSensorDefinition] = [

    # -----------------------------------------------------------------------
    # Teploty – okruhy
    # -----------------------------------------------------------------------
    AcondSensorDefinition("t_set_indoor1",      "Požadovaná teplota okruh 1",            30001, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_act_indoor1",      "Teplota okruh 1",            30002, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_set_indoor2",      "Požadovaná teplota okruh 2",            30003, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_act_indoor2",      "Teplota okruh 2",            30004, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),

    # -----------------------------------------------------------------------
    # Teploty – TUV
    # -----------------------------------------------------------------------
    AcondSensorDefinition("t_set_tuv",          "Požadovaná teplota TUV",               30005, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_act_tuv",          "Teplota TUV",                   30006, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),

    # -----------------------------------------------------------------------
    # Stav TČ – word (bity rozebírá binary_sensor.py)
    # -----------------------------------------------------------------------
    AcondSensorDefinition("tc_status",          "Stav TČ",                       30007, 1.0, None, None, SensorStateClass.MEASUREMENT, signed=False),

    # -----------------------------------------------------------------------
    # Teploty – voda
    # -----------------------------------------------------------------------
    AcondSensorDefinition("t_set_water_back",   "Požadovaná teplota zpátečky",                  30008, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_act_water_back",   "Teplota zpátečky",                     30009, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),

    # -----------------------------------------------------------------------
    # Teploty – okolí
    # -----------------------------------------------------------------------
    AcondSensorDefinition("t_act_air",          "Venkovní teplota",                     30010, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_act_solar",        "Teplota solárního panelu",             30011, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_act_pool",         "Teplota bazénu",                       30012, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_set_pool",         "Požadovaná teplota bazénu",            30013, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),

    # -----------------------------------------------------------------------
    # Režim a regulace – textové hodnoty přes slovníky HP_MODES / REG_TYPES
    # -----------------------------------------------------------------------
    AcondSensorDefinition("hp_mode",            "Režim TČ",                             30014, 1.0, None, None, None, signed=False),
    AcondSensorDefinition("regulation_type",    "Typ regulace",                         30015, 1.0, None, None, None, signed=False),

    # -----------------------------------------------------------------------
    # Teplota solanky
    # -----------------------------------------------------------------------
    AcondSensorDefinition("brine_temp",         "Teplota solanky",                      30016, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),

    # -----------------------------------------------------------------------
    # Komunikace
    # -----------------------------------------------------------------------
    AcondSensorDefinition("heartbeat",          "Čítač komunikace Modbus",                 30017, 1.0, None, None, SensorStateClass.MEASUREMENT, signed=False),

    # -----------------------------------------------------------------------
    # Teploty – výstup vody / chlazení
    # -----------------------------------------------------------------------
    AcondSensorDefinition("t_act_water_outlet", "Teplota topné vody",                30018, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_set_water_outlet", "Požadovaná teplota výstupu chlazení", 30019, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),

    # -----------------------------------------------------------------------
    # Kompresor – max. otáčky nebo výkon
    # Jednotka se přiřadí dynamicky v __init__.py podle CONF_HP_SERIES:
    #   PRO série      → UnitOfPower.WATT
    #   Standard série → "rpm"
    # Výchozí hodnota "rpm" slouží jen jako fallback.
    # -----------------------------------------------------------------------
    AcondSensorDefinition("comp_rpm_max",       "Max. otáčky kompresoru"               ,   30020, 1.0, "rpm", None, SensorStateClass.MEASUREMENT, signed=False),

    # -----------------------------------------------------------------------
    # Chybové kódy – převod na text v sensor.py přes ERROR_CODES / DRIVER_ERROR_CODES
    # -----------------------------------------------------------------------
    AcondSensorDefinition("err_number",         "Stav TČ – popis chyby",               30021, 1.0, None, None, None, signed=False),
    AcondSensorDefinition("err_number_driver",  "Stav driveru – popis chyby",          30023, 1.0, None, None, None, signed=False),

    # -----------------------------------------------------------------------
    # Kompresor – aktuální otáčky nebo výkon (stejná logika jako comp_rpm_max)
    # -----------------------------------------------------------------------
    AcondSensorDefinition("comp_rpm_actual",    "Aktuální otáčky kompresoru",                30024, 1.0, "rpm", None, SensorStateClass.MEASUREMENT, signed=False),

    # -----------------------------------------------------------------------
    # Čerpadlo
    # -----------------------------------------------------------------------
    AcondSensorDefinition("actual_pwm",         "Rychlost oběhového čerpadla",         30025, 1.0, PERCENTAGE, None, SensorStateClass.MEASUREMENT, signed=False),
    AcondSensorDefinition("manual_pwm",         "Manuální režim prim. čerpadla",             30026, 1.0, None, None, None, signed=False),

    # -----------------------------------------------------------------------
    # Výkon a efektivita
    # -----------------------------------------------------------------------
    AcondSensorDefinition("aep",                "Elektrický příkon",                   30027, 1.0, UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, signed=False),
    AcondSensorDefinition("ahp",                "Tepelný výkon",                       30028, 1.0, UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, signed=False),
    AcondSensorDefinition("cop",                "Topný faktor COP",                    30029, 0.1, None, None, SensorStateClass.MEASUREMENT, signed=False),

    # -----------------------------------------------------------------------
    # E-heater
    # -----------------------------------------------------------------------
    AcondSensorDefinition("t02_eh",             "Teplota E-heateru",                   30030, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("manual_eh",          "Povolení režimu Bivalence",            30031, 1.0, None, None, None, signed=False),

    # -----------------------------------------------------------------------
    # Tichý provoz
    # -----------------------------------------------------------------------
    AcondSensorDefinition("silent_mode",        "Tichý provoz",                        30032, 1.0, None, None, None, signed=False),
    AcondSensorDefinition("silent_mode_start",  "Tichý provoz – začátek (min od 00:00)",              30033, 1.0, "min", None, SensorStateClass.MEASUREMENT, signed=False),
    AcondSensorDefinition("silent_mode_stop",   "Tichý provoz – konec (min od 00:00)",                30034, 1.0, "min", None, SensorStateClass.MEASUREMENT, signed=False),

    # -----------------------------------------------------------------------
    # Energie – součty (32-bit DINT)
    # -----------------------------------------------------------------------
    AcondSensorDefinition("tes",                "Tepelná energie celkem",              30035, 0.1, UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, dint=True),
    AcondSensorDefinition("ees",                "Elektrická energie celkem",           30037, 0.1, UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, dint=True),

    # -----------------------------------------------------------------------
    # Energie – denní (16-bit, reset o půlnoci)
    # -----------------------------------------------------------------------
    AcondSensorDefinition("ted",                "Tepelná energie dnes",                30039, 0.1, UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
    AcondSensorDefinition("eed",                "Elektrická energie dnes",             30040, 0.1, UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),

    # -----------------------------------------------------------------------
    # Sezónní COP
    # -----------------------------------------------------------------------
    AcondSensorDefinition("scop",               "Sezónní topný faktor SCOP",           30041, 0.1, None, None, SensorStateClass.MEASUREMENT, signed=False),

    # -----------------------------------------------------------------------
    # Teploty – chladivo
    # -----------------------------------------------------------------------
    AcondSensorDefinition("t_act_hp",           "Kondenzační teplota",                 30042, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_act_lp",           "Vypařovací teplota",                  30043, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),

    # -----------------------------------------------------------------------
    # Třída tepelného výkonu – převod na text v sensor.py přes THERMAL_POWER
    # -----------------------------------------------------------------------
    AcondSensorDefinition("thermal_power",      "Třída tepelného výkonu",              30044, 1.0, None, None, None, signed=False),

    # -----------------------------------------------------------------------
    # Stav komponent – word (bity rozebírá binary_sensor.py)
    # -----------------------------------------------------------------------
    AcondSensorDefinition("hp_component_status","Stav komponent",               30045, 1.0, None, None, SensorStateClass.MEASUREMENT, signed=False),

    # -----------------------------------------------------------------------
    # Ventilátor a EEV
    # -----------------------------------------------------------------------
    AcondSensorDefinition("fan_speed",          "Rychlost ventilátoru",                30046, 1.0, PERCENTAGE, None, SensorStateClass.MEASUREMENT, signed=False),
    AcondSensorDefinition("eev_steps",          "Poloha expanzního ventilu",           30047, 1.0, PERCENTAGE, None, SensorStateClass.MEASUREMENT, signed=False),

    # -----------------------------------------------------------------------
    # Teploty – sání a výtlak
    # -----------------------------------------------------------------------
    AcondSensorDefinition("t_act_suction",      "Sací teplota",                        30048, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    AcondSensorDefinition("t_act_discharge",    "Výtlačná teplota",                    30049, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),

    # -----------------------------------------------------------------------
    # Provozní hodiny (32-bit DINT) a minuty (16-bit)
    # POZOR: hodiny a minuty jsou na sousedních adresách – nesmí se překrývat!
    #   compressor_hours: 30050+30051 (DINT)
    #   compressor_min:   30052       (16-bit)
    #   fan_hours:        30053+30054 (DINT)
    #   fan_min:          30055       (16-bit)
    #   rv_hours:         30056+30057 (DINT)
    #   rv_min:           30058       (16-bit)
    #   pump_hours:       30059+30060 (DINT)
    #   pump_min:         30061       (16-bit)
    #   bivalence1_hours: 30062+30063 (DINT)
    #   bivalence1_min:   30064       (16-bit)
    #   bivalence2_hours: 30065+30066 (DINT)
    #   bivalence2_min:   30067       (16-bit)
    # -----------------------------------------------------------------------
    AcondSensorDefinition("compressor_hours",   "Hodiny kompresoru",                   30050, 1.0, "h", None, SensorStateClass.TOTAL_INCREASING, signed=False, dint=True),
    AcondSensorDefinition("compressor_min",     "Minuty kompresoru",                   30052, 1.0, "min", None, SensorStateClass.MEASUREMENT, signed=False),
    AcondSensorDefinition("fan_hours",          "Hodiny ventilátoru",                  30053, 1.0, "h", None, SensorStateClass.TOTAL_INCREASING, signed=False, dint=True),
    AcondSensorDefinition("fan_min",            "Minuty ventilátoru",                  30055, 1.0, "min", None, SensorStateClass.MEASUREMENT, signed=False),
    AcondSensorDefinition("rv_hours",           "Hodiny reverzního ventilu",           30056, 1.0, "h", None, SensorStateClass.TOTAL_INCREASING, signed=False, dint=True),
    AcondSensorDefinition("rv_min",             "Minuty reverzního ventilu",           30058, 1.0, "min", None, SensorStateClass.MEASUREMENT, signed=False),
    AcondSensorDefinition("pump_hours",         "Hodiny oběhového čerpadla",           30059, 1.0, "h", None, SensorStateClass.TOTAL_INCREASING, signed=False, dint=True),
    AcondSensorDefinition("pump_min",           "Minuty oběhového čerpadla",           30061, 1.0, "min", None, SensorStateClass.MEASUREMENT, signed=False),
    AcondSensorDefinition("bivalence1_hours",   "Hodiny bivalence 1",                  30062, 1.0, "h", None, SensorStateClass.TOTAL_INCREASING, signed=False, dint=True),
    AcondSensorDefinition("bivalence1_min",     "Minuty bivalence 1",                  30064, 1.0, "min", None, SensorStateClass.MEASUREMENT, signed=False),
    AcondSensorDefinition("bivalence2_hours",   "Hodiny bivalence 2",                  30065, 1.0, "h", None, SensorStateClass.TOTAL_INCREASING, signed=False, dint=True),
    AcondSensorDefinition("bivalence2_min",     "Minuty bivalence 2",                  30067, 1.0, "min", None, SensorStateClass.MEASUREMENT, signed=False),

    # -----------------------------------------------------------------------
    # Energie chlazení – součty (32-bit DINT)
    # -----------------------------------------------------------------------
    AcondSensorDefinition("cooling_energy",     "Chladicí energie celkem",             30069, 0.1, UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, dint=True),
    AcondSensorDefinition("ece",                "Elektrická energie chlazení celkem",  30071, 0.1, UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, dint=True),

    # -----------------------------------------------------------------------
    # Energie chlazení – denní (16-bit, reset o půlnoci)
    # -----------------------------------------------------------------------
    AcondSensorDefinition("ced",                "Chladicí energie dnes",               30073, 0.1, UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
    AcondSensorDefinition("eecd",               "Elektrická energie chlazení dnes",    30074, 0.1, UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),

    # -----------------------------------------------------------------------
    # Reset PLC – pro sledování v historii (0=klid, 1=reset probíhá)
    # -----------------------------------------------------------------------
    AcondSensorDefinition("reset_plc",          "Stav resetu PLC",                     30068, 1.0, None, None, None, signed=False),

    # -----------------------------------------------------------------------
    # Počet startů kompresoru (32-bit DINT)
    # -----------------------------------------------------------------------
    AcondSensorDefinition("compressor_starts",  "Počet startů kompresoru",             30075, 1.0, None, None, SensorStateClass.TOTAL_INCREASING, signed=False, dint=True),
]


# ===========================================================================
# HOLDING REGISTRY – zapisovatelné entity (40xxx)
# ===========================================================================

# ---------------------------------------------------------------------------
# Number – nastavitelné číselné hodnoty
# ---------------------------------------------------------------------------
@dataclass
class AcondNumberDefinition:
    key: str
    name: str
    address: int          # 40xxx
    scale: float = 1.0    # převod raw → zobrazovaná hodnota (a zpět při zápisu)
    unit: str | None = None
    device_class: str | None = None
    min_value: float = 0
    max_value: float = 100
    step: float = 1.0


NUMBER_DEFINITIONS: list[AcondNumberDefinition] = [
    # Nastavené teploty okruhů
    AcondNumberDefinition("t_set_indoor1",       "Požadovaná teplota okruh 1",              40001, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, 10.0, 30.0, 0.1),
    AcondNumberDefinition("t_corr_indoor1",      "Teplota okruh 1 z ext. senzoru",      40002, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,  0.0, 50.0, 0.1),
    AcondNumberDefinition("t_set_indoor2",       "Požadovaná teplota okruh 2",              40003, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, 10.0, 30.0, 0.1),
    AcondNumberDefinition("t_corr_indoor2",      "Teplota okruh 2 z ext. senzoru",      40004, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,  0.0, 50.0, 0.1),
    AcondNumberDefinition("t_set_tuv",           "Požadovaná teplota TUV",                 40005, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, 10.0, 46.0, 0.1),
    # Zpátečka
    AcondNumberDefinition("t_set_water_back",    "Požadovaná teplota zpátečky - Standard",           40008, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, 10.0, 65.0, 0.1),
    # Korekce senzorů – hodnoty mimo rozsah → Acond použije vlastní čidlo
    AcondNumberDefinition("t_corr_air",          "Venkovní teplota z ext. čidla",               40009, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, -50.0, 50.0, 0.1),
    AcondNumberDefinition("t_corr_solar",        "Solární teplota z ext. čidla",       40010, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, -50.0, 300.0, 0.1),
    AcondNumberDefinition("t_corr_pool",         "Bazénová teplota z ext. čidla",                 40011, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,   0.0,  50.0, 0.1),
    # Bazén a chlazení
    AcondNumberDefinition("t_set_pool",          "Požadovaná teplota bazénu",              40012, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, 10.0, 50.0, 0.1),
    AcondNumberDefinition("t_set_water_outlet",  "Požadovaná teplota výstupu chlazení",   40013, 0.1, UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, 15.0, 30.0, 0.1),
    # Kompresor – max. výkon/otáčky (jednotka se přiřadí dynamicky podle série)
    AcondNumberDefinition("comp_capacity_max_set", "Max. otáčky kompresoru",              40014, 1.0, "rpm", None, 1800, 6000, 1),
    # Čerpadlo
    AcondNumberDefinition("pwm_set",             "Nast. rychlosti oběh. čerpadla",  40015, 1.0, PERCENTAGE, None, 0, 100, 1),
    # Tichý provoz – časy v minutách od půlnoci (0–1440)
    AcondNumberDefinition("silent_mode_start_set", "Tichý provoz – začátek (min od 00:00)",              40019, 1.0, "min", None, 0, 1440, 15),
    AcondNumberDefinition("silent_mode_stop_set",  "Tichý provoz – konec (min od 00:00)",                40020, 1.0, "min", None, 0, 1440, 15),
]


# ---------------------------------------------------------------------------
# Switch – přepínače (0/1)
# ---------------------------------------------------------------------------
@dataclass
class AcondSwitchDefinition:
    key: str
    name: str
    address: int          # 40xxx
    bit: int | None = None  # None = celý registr, int = konkrétní bit (read-modify-write!)


SWITCH_DEFINITIONS: list[AcondSwitchDefinition] = [
    # Celé registry
    AcondSwitchDefinition("manual_pwm_set",  "Povolení řízení ob. čerpadla",    40016),
    AcondSwitchDefinition("manual_eh_set",   "Povolení bivalence",  40017),
    AcondSwitchDefinition("silent_mode_set", "Tichý provoz",                40018),
    # Bity registru 40006 – TC_set (read-modify-write!)
    # POZOR: při zápisu vždy přečti aktuální hodnotu, změň jen příslušný bit
    AcondSwitchDefinition("tc_set_bit_0",    "Automatický režim",           40006, bit=0),
    AcondSwitchDefinition("tc_set_bit_1",    "Režim pouze TČ",              40006, bit=1),
    AcondSwitchDefinition("tc_set_bit_2",    "Režim bivalence",           40006, bit=2),
    AcondSwitchDefinition("tc_set_bit_3",    "Vypnuto",                     40006, bit=3),  # ⚠️ nebezpečné
    AcondSwitchDefinition("tc_set_bit_4",    "Režim chlazení",              40006, bit=4),
    AcondSwitchDefinition("tc_set_bit_6",    "Solár zapnuto",               40006, bit=6),
    AcondSwitchDefinition("tc_set_bit_7",    "Bazén zapnuto",               40006, bit=7),
]


# ---------------------------------------------------------------------------
# Select – výběr z možností
# ---------------------------------------------------------------------------
@dataclass
class AcondSelectDefinition:
    key: str
    name: str
    address: int          # 40xxx
    options: dict[int, str]


SELECT_DEFINITIONS: list[AcondSelectDefinition] = [
    AcondSelectDefinition(
        "sel_regulation_type",
        "Typ regulace",
        40007,
        options=REG_TYPES,   # {0: "AcondTherm", 1: "Ekvitermní", 2: "Standard"}
    ),
]


# ---------------------------------------------------------------------------
# Button – jednorázové akce
# ---------------------------------------------------------------------------
@dataclass
class AcondButtonDefinition:
    key: str
    name: str
    address: int          # 40xxx
    value: int = 1        # hodnota zapsaná při stisku
    bit: int | None = None  # None = celý registr, int = bit (read-modify-write!)


BUTTON_DEFINITIONS: list[AcondButtonDefinition] = [
    # Potvrzení poruchy – bit 5 registru 40006, Acond bit sám shodí po potvrzení
    AcondButtonDefinition("tc_set_bit_5",   "Potvrzení poruchy",  40006, value=1, bit=5),  # ⚠️ nebezpečné
    # Reset PLC – zapíše 1, Acond sám vrátí na 0 po restartu
    AcondButtonDefinition("reset_plc_set",  "Reset PLC – varování, jen pro poučené",  40021, value=1),  # ⚠️ nebezpečné
    # Léto/zima přepnutí – bit 5 TČ sám shodí po přepnutí
    AcondButtonDefinition("tc_set_bit_8",   "Přepnout léto/zima",                     40006, value=1, bit=8),

    # Reset externích čidel – zapíše hodnotu jednoznačně mimo rozsah (0x8000 = 32768
    # unsigned = -32768 signed). Acond detekuje out-of-range a vrátí se k internímu
    # čidlu. Patří do view "Ovládání" k odpovídajícím number entitám 40002/40004/
    # 40009/40010/40011 – uživatel si jich má všimnout při zápisu externí hodnoty.
    AcondButtonDefinition("reset_t_corr_indoor1", "Přepnout na interní čidlo okruh 1",     40002, value=0x8000),
    AcondButtonDefinition("reset_t_corr_indoor2", "Přepnout na interní čidlo okruh 2",     40004, value=0x8000),
    AcondButtonDefinition("reset_t_corr_air",     "Přepnout na interní venkovní čidlo",    40009, value=0x8000),
    AcondButtonDefinition("reset_t_corr_solar",   "Přepnout na interní solární čidlo",     40010, value=0x8000),
    AcondButtonDefinition("reset_t_corr_pool",    "Přepnout na interní bazénové čidlo",    40011, value=0x8000),
]
