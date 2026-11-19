"""Previsão dia a dia com o modelo HistGradientBoosting treinado.

Parte do histórico real, prevê o dia seguinte, acrescenta essa previsão ao
histórico (para lags/médias) e repete — assim os dias 2…N usam as previsões
anteriores como se fossem vendas já observadas.

A previsão começa sempre HOJE. Se os dados estiverem atrasados (última venda
antes de ontem), os dias em falta também são previstos, para alimentar os lags,
mas não são devolvidos.
"""
import sys
from datetime import date
from functools import lru_cache

import joblib
import pandas as pd

from .dataset import FEATURES, add_features, load_daily
from .train import MODEL_PATH


@lru_cache(maxsize=1)
def _load_model(mtime: float):
    """Modelo em memória; volta a carregar só se o ficheiro mudar (novo treino)."""
    return joblib.load(MODEL_PATH)


def load_model():
    """Modelo de previsão (em cache)."""
    return _load_model(MODEL_PATH.stat().st_mtime)


def forecast(days: int = 7, store_id: int | None = None, today: date | None = None) -> pd.DataFrame:
    """Prevê faturação diária por loja para ``days`` dias a partir de hoje.

    Args:
        days: Horizonte da previsão.
        store_id: Se definido, só essa loja; senão todas.
        today: Dia de início (por defeito, a data de hoje). Útil nos testes.

    Returns:
        DataFrame com ``store_id``, ``day``, ``revenue`` (previsão).
    """
    model = load_model()
    history = load_daily()[["store_id", "day", "revenue"]]
    if store_id is not None:
        history = history[history["store_id"] == store_id]

    last_day = history["day"].max()
    first_day = max(pd.Timestamp(today or date.today()), last_day + pd.Timedelta(days=1))
    steps = (first_day - last_day).days - 1 + days   # dias em falta + horizonte

    results = []
    for i in range(1, steps + 1):
        day = last_day + pd.Timedelta(days=i)
        future = pd.DataFrame({
            "store_id": history["store_id"].unique(),
            "day": day,
            "revenue": 0.0,  # placeholder; features usam lags do histórico
        })
        feats = add_features(pd.concat([history, future]))
        feats = feats[feats["day"] == day]
        future["revenue"] = model.predict(feats[FEATURES]).round(2)
        history = pd.concat([history, future])  # alimenta o próximo dia
        if day >= first_day:
            results.append(future)
    return pd.concat(results).reset_index(drop=True)


if __name__ == "__main__":
    store = int(sys.argv[1]) if len(sys.argv) > 1 else None
    df = forecast(7, store)
    print(df.pivot(index="day", columns="store_id", values="revenue"))
    print("\nTotal 7 dias por loja:")
    print(df.groupby("store_id")["revenue"].sum().round(2))
