# IoT Climate Monitor for Raspberry Pi

Prosty projekt na Raspberry Pi oparty o pojedynczy plik `SensorsIoT.py`, ktory zbiera dane z czujnikow, steruje LED i buzzerem oraz udostepnia dashboard webowy i API.

## Co robi aplikacja

- Odczytuje temperature i wilgotnosc z DHT11/DHT22.
- Odczytuje orientacyjne stezenie gazu (ppm) z MQ-135 przez ADC (ADS1x15).
- Ocenia jakosc powietrza na podstawie temperatury, wilgotnosci i MQ-135.
- Steruje diodami LED (status) i buzzerem (alarm).
- Udostepnia dashboard webowy oraz API JSON.
- Wysyla dane do ThingSpeak (mozna wlaczyc/wylaczyc z API).

## Plik uruchomieniowy

- `SensorsIoT.py` - zawiera logike sensorow, dashboard, API i uruchomienie serwera Flask.

## Wymagania

- Raspberry Pi OS (zalecane) lub Linux
- Python 3.11+
- DHT11 albo DHT22
- MQ-135 + ADS1x15 (opcjonalnie, ale wspierane przez aplikacje)

## Konfiguracja Raspberry Pi dla DHT11 / DHT22

1. Podlacz `VCC` modulu do `3.3V`, a `GND` do `GND`.
2. Podlacz `DATA` do GPIO (domyslnie `GPIO17`, czyli `DHT_GPIO_PIN=17`).
3. Dla golej wersji DHT11 (bez modulu) dodaj rezystor pull-up `4.7k-10k` miedzy `VCC` i `DATA`.

## Konfiguracja dla MQ-135 + ADS1x15 (opcjonalnie)

Aplikacja korzysta z I2C i ukladu ADS (np. ADS1115), aby odczytac sygnal analogowy z MQ-135.

1. Wlacz I2C:

```bash
sudo raspi-config
```

Wybierz `Interface Options -> I2C -> Enable`.

2. Ustaw parametry ADC przez zmienne srodowiskowe:

- `MQ135_I2C_ADDRESS` (domyslnie `0x48`)
- `MQ135_CHANNEL` (domyslnie `0`)

## Uruchomienie

Linux / Raspberry Pi:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python SensorsIoT.py
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python SensorsIoT.py
```

Dashboard bedzie dostepny pod adresem:

```text
http://<IP_RASPBERRY_PI>:8080
```

## Zmienne srodowiskowe (SensorsIoT.py)

- `HOST` - adres nasluchu HTTP (domyslnie `0.0.0.0`)
- `PORT` - port HTTP (domyslnie `8080`)
- `LED_RED_PIN` - GPIO czerwonej diody LED (domyslnie `24`)
- `LED_GREEN_PIN` - GPIO zielonej diody LED (domyslnie `23`)
- `BUZZER_PIN` - GPIO buzzera (domyslnie `16`)
- `BUZZER_THRESHOLD_C` - prog temperatury dla alarmu buzzera (domyslnie `24`)
- `DHT_GPIO_PIN` - GPIO dla pinu DATA DHT (domyslnie `17`)
- `DHT_MODEL` - `dht11` albo `dht22` (domyslnie `dht11`)
- `DHT_RETRY_COUNT` - liczba ponownych prob odczytu DHT (domyslnie `5`)
- `DHT_RETRY_DELAY_SECONDS` - opoznienie miedzy probami DHT (domyslnie `2`)
- `TEMPERATURE_POLL_INTERVAL_SECONDS` - interwal odswiezania pomiarow (domyslnie `1`)
- `SENSOR_FILTER_WINDOW_SAMPLES` - rozmiar okna filtra probek (domyslnie `5`)
- `SENSOR_FILTER_METHOD` - metoda filtra: `median` albo `mean` (domyslnie `median`)
- `MQ135_I2C_ADDRESS` - adres I2C ukladu ADS dla MQ-135 (domyslnie `0x48`)
- `MQ135_CHANNEL` - kanal ADS dla MQ-135 (domyslnie `0`)
- `THINGSPEAK_API_KEY` - klucz API ThingSpeak
- `THINGSPEAK_INTERVAL_SECONDS` - interwal wysylki do ThingSpeak (domyslnie `30`)

## API

- `GET /` - dashboard HTML
- `GET /api/status` - status systemu (LED, temperatura, buzzer, MQ-135, jakosc powietrza, status chmury)
- `POST /api/cloud-sync` - wlacza/wylacza wysylke do ThingSpeak (`{"enabled": true/false}`)
- `POST /api/buzzer-manual` - reczne wlaczanie/wylaczanie buzzera (`{"enabled": true/false}`)

## Kierunki rozwoju

- Dodanie autoryzacji dla endpointow API.
- Trwale zapisywanie historii pomiarow (np. SQLite).
- Konfigurowalne profile alarmow (temperatura i ppm).
- Eksport danych do CSV/JSON z poziomu dashboardu.