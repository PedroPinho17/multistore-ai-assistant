"""Descarrega o tempo diário real (Open-Meteo) por distrito para data/weather.csv.

Corre-se à mão, só quando é preciso atualizar. O gerador lê só o CSV
(reprodutível, sem internet, e a CI não depende da API).
"""
import csv
from datetime import date, timedelta
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parents[3] / "data" / "weather.csv"
START = date(2025, 1, 1)

# Distritos das lojas (o generate_activity já usa o district)
DISTRICTS = {
    "Porto": (41.15, -8.61), "Braga": (41.55, -8.42), "Aveiro": (40.64, -8.65),
    "Coimbra": (40.21, -8.43), "Lisboa": (38.72, -9.14), "Faro": (37.02, -7.93),
}
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"


def fetch(url: str, lat: float, lon: float, **params) -> dict:
    r = httpx.get(url, params={"latitude": lat, "longitude": lon, "daily": DAILY,
                               "timezone": "Europe/Lisbon", **params}, timeout=60)
    r.raise_for_status()
    return r.json()["daily"]


def main():
    yesterday = date.today() - timedelta(days=1)
    archive_end = yesterday - timedelta(days=7)   # o arquivo tem alguns dias de atraso
    rows = {}
    for district, (lat, lon) in DISTRICTS.items():
        old = fetch(ARCHIVE, lat, lon, start_date=START.isoformat(), end_date=archive_end.isoformat())
        recent = fetch(FORECAST, lat, lon, past_days=10, forecast_days=16)
        for d in (old, recent):
            for day, tmax, tmin, rain in zip(d["time"], d["temperature_2m_max"],
                                             d["temperature_2m_min"], d["precipitation_sum"], strict=True):
                if tmax is not None:
                    rows[(district, day)] = (tmax, tmin, rain or 0.0)
        print(f"{district}: ok")

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["district", "day", "temp_max", "temp_min", "rain_mm"])
        for (district, day), values in sorted(rows.items()):
            w.writerow([district, day, *values])
    print(f"{len(rows)} linhas em {OUT}")


if __name__ == "__main__":
    main()
