"""Dataset de faturação diária por loja e features para o modelo de forecast.

Features calendário (dia da semana, mês, fim-de-semana) + lags e médias móveis
por loja. ``dropna`` remove os primeiros dias sem histórico suficiente.
"""
import os
from functools import cache

import pandas as pd
import psycopg
from dotenv import load_dotenv

from multistore_ai_assistant.data.signals import is_holiday, weather

load_dotenv()

QUERY = """
SELECT store_id, sold_at::date AS day, sum(total) AS revenue, count(*) AS tickets
FROM sales
GROUP BY store_id, sold_at::date
ORDER BY store_id, day
"""


def load_daily() -> pd.DataFrame:
    """Carrega faturação e nº de talões por loja e dia a partir da BD."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        cur = conn.execute(QUERY)
        df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    df["day"] = pd.to_datetime(df["day"])
    df["revenue"] = df["revenue"].astype(float)
    return df


@cache
def store_districts() -> dict:
    """store_id -> distrito."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        return dict(conn.execute("SELECT id, district FROM stores").fetchall())


def add_weather(df: pd.DataFrame) -> pd.DataFrame:
    """temp_max, rain_mm e is_holiday pelo distrito da loja.

    Dias sem tempo no CSV usam a média do distrito nesse mês (clima normal).
    """
    w = pd.DataFrame([(dist, pd.Timestamp(d), t, r) for (dist, d), (t, r) in weather().items()],
                     columns=["district", "day", "temp_max", "rain_mm"])
    df = df.copy()
    df["district"] = df["store_id"].map(store_districts())
    df = df.merge(w, on=["district", "day"], how="left")

    w["month"] = w["day"].dt.month
    normal = w.groupby(["district", "month"])[["temp_max", "rain_mm"]].mean()
    key = pd.MultiIndex.from_arrays([df["district"], df["day"].dt.month])
    for col in ["temp_max", "rain_mm"]:
        df[col] = df[col].fillna(pd.Series(normal[col].reindex(key).values, index=df.index))

    df["is_holiday"] = [int(is_holiday(dist, d.date())) for dist, d in zip(df["district"], df["day"], strict=True)]
    return df.drop(columns="district")


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta features temporais e de histórico; remove linhas com NaN.

    Args:
        df: Deve ter ``store_id``, ``day``, ``revenue``.

    Returns:
        DataFrame com as colunas de ``FEATURES`` + ``revenue``.
    """
    df = add_weather(df).sort_values(["store_id", "day"])
    df["weekday"] = df["day"].dt.day_of_week
    df["month"] = df["day"].dt.month
    df["day_of_year"] = df["day"].dt.day_of_year
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)

    g = df.groupby("store_id")["revenue"]
    df["lag_7"] = g.shift(7)       # mesmo dia da semana passada
    df["lag_14"] = g.shift(14)     # há duas semanas
    df["mean_7"] = g.transform(lambda s: s.shift(1).rolling(7).mean())
    df["mean_28"] = g.transform(lambda s: s.shift(1).rolling(28).mean())
    return df.dropna()


FEATURES = [
    "store_id", "weekday", "month", "day_of_year", "is_weekend",
    "lag_7", "lag_14", "mean_7", "mean_28",
    "temp_max", "rain_mm", "is_holiday",
]


if __name__ == "__main__":
    df = add_features(load_daily())
    print(df.shape)
    print(df.head(10))
    print(df.groupby("store_id")["revenue"].mean().round(2))
