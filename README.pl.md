# Acond Heat Pump — polska wersja integracji Home Assistant

Nieoficjalna integracja pomp ciepła Acond przez lokalny Modbus TCP.
Udostępnia pomiary, nastawy, polecenia i automatycznie tworzony panel Lovelace.

Projekt pozostaje wersją testową. Nie jest produktem Acond ani dodatkiem
zatwierdzonym lub wspieranym przez producenta.

## Zakres polskiego interfejsu

- formularz dodawania integracji, ustawienia i błędy formularzy;
- nazwy 117 encji, w tym odpowiednie nazwy mocy dla serii PRO;
- powiadomienia o eksporcie kontekstu AI i błędach eksportu;
- podstawowy dashboard, opisy błędów, przyciski, potwierdzenia i pomoc;
- informacja o dodatku MaR, jeśli nie jest zainstalowany.

Wybierz **polski jako język systemu Home Assistant** w Ustawienia → System
→ Ogólne. Po zmianie języka uruchom ponownie HA, aby odtworzyć dashboard.
Sam język profilu użytkownika nie zmienia języka generowanego panelu.

Długie nazwy i opisy są zawijane zamiast skracania wielokropkiem. Wbudowany
moduł prezentacji działa wyłącznie w panelu `/acond-dashboard`; nie wymaga
card-mod ani dodatkowych kart HACS. Na telefonie przyciski i stany są układane
w kolejnych wierszach. Po aktualizacji odśwież przeglądarkę.

W trybie cichym nastawy nadal są liczbą minut od 00:00, zgodnie z implementacją
autora. Odczyt pokazuje godziny, np. 1320 min = 22:00 i 360 min = 06:00,
oraz stan „Wyłączony/Włączony”. Nie zmienia to ustawień ani formatu zapisów pompy.

### Zgodność z automatyką i MaR

Zachowane są `entity_id`, `unique_id`, rejestry, przeliczniki, jednostki, zakresy,
algorytmy i wartości przesyłane do pompy. Tekstowe stany oraz opcje API,
np. `Standard` i `Ekvitermní`, również zachowują oryginalne wartości.
Polski panel pokazuje ich tłumaczenia, korzystając z dodatkowego atrybutu
`localized_state`, a przyciski regulacji wysyłają oryginalne opcje.

**Granica lokalizacji:** natywne okna szczegółów HA, narzędzia deweloperskie,
historia i obce panele mogą nadal pokazywać oryginalne stany i listy opcji.
Ich zmiana naruszałaby dotychczasowy interfejs używany przez automatyzacje.
Dzienniki techniczne i zawartość plików diagnostycznych AI pozostają w języku
oryginału. Osobny dodatek MaR i jego własne widoki nie są objęte tym tłumaczeniem.

## Pomiary i sterowanie

Integracja udostępnia temperatury pomieszczeń, CWU, zasilania i powrotu,
temperaturę zewnętrzną, moc elektryczną i cieplną, COP/SCOP, energię,
obroty, czas pracy, liczbę startów oraz stany podzespołów i błędy.

Encje sterujące pozwalają zmieniać temperatury zadane, tryby pracy,
typ regulacji, limit sprężarki i inne obsługiwane parametry. Wykonanie
takiej akcji zmienia pracę urządzenia. Integracja nie ma globalnego
przełącznika blokującego wszystkie zapisy.

## Wymagania i instalacja

- Home Assistant co najmniej 2024.11;
- HACS lub instalacja ręczna;
- aktywna komunikacja Modbus TCP pompy na porcie 502;
- jeden klient Modbus — istniejący klient YAML lub inny system nie może
  równocześnie zajmować połączenia z pompą.

Autor zaleca timeout komunikacji Modbus pompy co najmniej 4 min 30 s.
Integracja odczytuje dane co 15 s. Dla starszego firmware część rejestrów
może być niedostępna.

Docelowa instalacja przez HACS: dodaj oryginalne repozytorium
`https://github.com/pavorlechre/homeassistant-acond` jako integrację,
pobierz wybrane wydanie zawierające tłumaczenie i uruchom ponownie HA.
Następnie dodaj **Acond Heat Pump** w Ustawienia → Urządzenia i usługi.
Podaj adres IP i serię: **Grandis / Economis** albo **PRO**.

Ręczna instalacja wymaga całego katalogu `custom_components/acond/`.
Sam plik `pl.json` nie lokalizuje elementów zapisanych dotąd w Pythonie
i dashboardzie. Dopóki poprawka nie zostanie przyjęta i wydana przez autora,
HACS z oryginalnego repozytorium nie zawiera tej wersji językowej.

## Ustawienia

Opcje integracji pozwalają zmienić adres IP, maksymalną temperaturę CWU
i zakres suwaka sprężarki. Domyślne maksimum CWU to 50°C; większe wartości
wymagają odblokowania serwisowego. Nie rozszerzaj zakresów bez ustalenia
dopuszczalnych parametrów konkretnej pompy.

Typ regulacji AcondTherm można zachować. Sama integracja udostępnia
nastawy i nie zastępuje fabrycznego algorytmu. Osobny dodatek
**Acond Regulator / MaR** oferuje własne sterowanie i ma inne wymagania.

## Diagnostyka i aktualizacje

Przy problemie sprawdź połączenie, wyłączność klienta Modbus, firmware
i dziennik HA. Do zgłoszenia przydatne są model pompy, wersja firmware,
wersja HA i integracji. Przed udostępnieniem eksportu AI sprawdź jego treść;
automatyczne ukrywanie danych poufnych nie jest w pełni niezawodne.

Tłumaczenie zachowuje istniejące tabele opisów błędów. Ich zgodność z danym
sterownikiem musi być oceniana na podstawie dokumentacji i panelu pompy.

Panel dostarczany przez integrację jest odtwarzany po uruchomieniu.
Własna kopia panelu zachowuje Twoje zmiany, ale wymaga ręcznego przenoszenia
nowości autora. Szczegóły dla autorów tłumaczeń: [localization.md](docs/localization.md).

Licencja MIT. Autor oryginału: Pavel Vorlech, `@pavorlechre`.
