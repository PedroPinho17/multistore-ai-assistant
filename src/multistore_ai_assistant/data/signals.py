"""Sinais reais (tempo e feriados) lidos dos CSVs, e o efeito deles nas vendas."""
import csv
from datetime import date
from functools import cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "data"


@cache
def weather() -> dict:
    """(distrito, dia) -> (temp_max, rain_mm)."""
    with (DATA / "weather.csv").open(encoding="utf-8") as f:
        return {(r["district"], date.fromisoformat(r["day"])): (float(r["temp_max"]), float(r["rain_mm"]))
                for r in csv.DictReader(f)}


@cache
def holidays() -> dict:
    """(distrito ou "", dia) -> nome. Distrito vazio = feriado nacional."""
    with (DATA / "holidays.csv").open(encoding="utf-8") as f:
        return {(r["district"], date.fromisoformat(r["day"])): r["name"] for r in csv.DictReader(f)}


def is_holiday(district: str, d: date) -> bool:
    h = holidays()
    return ("", d) in h or (district, d) in h


def weather_factor(segment: str, district: str, d: date) -> float:
    """Multiplicador pelo tempo real. Sem dados (dia futuro) = 1."""
    w = weather().get((district, d))
    if w is None:
        return 1.0
    temp, rain = w
    if segment == "geladaria":
        f = 1 + 0.04 * (temp - 22)          # +4% por grau acima de 22 °C
        f *= 0.6 if rain > 5 else 1.0       # chuva forte afasta clientes
        return max(0.3, min(f, 1.8))
    if segment == "café":
        return 1.08 if rain > 5 or temp < 12 else 1.0   # frio e chuva: mais cafés
    return 0.9 if rain > 10 else 1.0                     # hamburgueria: só a chuva forte pesa


def holiday_factor(segment: str, district: str, d: date) -> float:
    """Feriado: geladaria e hamburgueria sobem, o café (rotina de trabalho) desce."""
    if not is_holiday(district, d):
        return 1.0
    return {"geladaria": 1.35, "hamburgueria": 1.25, "café": 0.85}[segment]
