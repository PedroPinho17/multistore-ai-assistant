"""Sinais reais: tempo e feriados a partir dos CSVs."""
from datetime import date

from multistore_ai_assistant.data.signals import is_holiday, weather_factor


def test_faro_agosto_geladaria_acima_de_um():
    assert weather_factor("geladaria", "Faro", date(2025, 8, 1)) > 1


def test_dia_sem_dados_devolve_um():
    assert weather_factor("geladaria", "Porto", date(2099, 1, 1)) == 1.0


def test_sao_joao_no_porto_e_feriado():
    assert is_holiday("Porto", date(2025, 6, 24))


# ---------- multiplicadores ----------

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from multistore_ai_assistant.data import signals  # noqa: E402
from multistore_ai_assistant.data.signals import holiday_factor, weather  # noqa: E402

DISTRICTS = {"Porto", "Braga", "Aveiro", "Coimbra", "Lisboa", "Faro"}      # distritos das 15 lojas


@pytest.fixture
def fake_weather(monkeypatch):
    def install(temp, rain):
        monkeypatch.setattr(signals, "weather", lambda: {("Faro", date(2025, 8, 1)): (temp, rain)})
    return install


@pytest.mark.parametrize("temp,rain,expected", [
    (22, 0, 1.0), (32, 0, 1.4), (45, 0, 1.8), (0, 0, 0.3), (32, 10, 0.84),
])
def test_ice_cream_follows_temperature_within_limits(fake_weather, temp, rain, expected):
    fake_weather(temp, rain)
    assert weather_factor("geladaria", "Faro", date(2025, 8, 1)) == pytest.approx(expected)


@pytest.mark.parametrize("segment,temp,rain,expected", [
    ("café", 20, 0, 1.0), ("café", 10, 0, 1.08), ("café", 20, 6, 1.08),
    ("hamburgueria", 20, 5, 1.0), ("hamburgueria", 20, 11, 0.9),
])
def test_cafe_and_burgers(fake_weather, segment, temp, rain, expected):
    fake_weather(temp, rain)
    assert weather_factor(segment, "Faro", date(2025, 8, 1)) == expected


def test_holiday_effect_by_segment():
    christmas = date(2025, 12, 25)
    assert [holiday_factor(s, "Faro", christmas) for s in ("geladaria", "hamburgueria", "café")] == [1.35, 1.25, 0.85]
    assert holiday_factor("café", "Faro", date(2025, 12, 23)) == 1.0


def test_municipal_holiday_only_in_its_district():
    assert is_holiday("Porto", date(2025, 6, 24)) and is_holiday("Braga", date(2025, 6, 24))
    assert not is_holiday("Lisboa", date(2025, 6, 24)) and is_holiday("Lisboa", date(2025, 6, 13))


def test_national_holidays_everywhere():
    assert all(is_holiday(d, date(2026, 4, 25)) for d in DISTRICTS)


# ---------- os CSVs (o gerador e o forecast só leem estes ficheiros) ----------

def test_weather_covers_every_store_district_without_gaps():
    days = {}
    for (district, d) in weather():
        days.setdefault(district, set()).add(d)
    assert set(days) == DISTRICTS
    for district, ds in days.items():
        span = (max(ds) - min(ds)).days + 1
        assert min(ds) == date(2025, 1, 1) and len(ds) == span, f"falhas no tempo de {district}"


def test_weather_values_are_plausible():
    temps = [t for t, _ in weather().values()]
    rains = [r for _, r in weather().values()]
    assert min(temps) > -5 and max(temps) < 48 and min(rains) >= 0


# ---------- forecast: dias sem tempo no CSV usam o clima normal do mês ----------

def test_future_days_without_weather_use_the_monthly_normal(monkeypatch):
    from multistore_ai_assistant.forecast import dataset
    monkeypatch.setattr(dataset, "store_districts", lambda: {1: "Faro"})
    df = pd.DataFrame({"store_id": [1, 1], "day": pd.to_datetime(["2025-08-01", "2099-08-01"]), "revenue": [1.0, 0.0]})
    out = dataset.add_weather(df)
    august = [t for (dist, d), (t, _) in weather().items() if dist == "Faro" and d.month == 8]
    assert out["temp_max"].notna().all()
    assert out.loc[1, "temp_max"] == pytest.approx(sum(august) / len(august))
