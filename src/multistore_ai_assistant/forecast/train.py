"""Treina o modelo de previsão de faturação diária e grava o joblib.

Usa HistGradientBoostingRegressor. Avalia nos últimos ``TEST_DAYS`` dias
contra um baseline ``lag_7`` (mesmo dia da semana anterior), depois retreina
em todos os dados e grava em ``models/sales_forecast.joblib``.
"""
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from .dataset import FEATURES, add_features, load_daily

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "sales_forecast.joblib"
TEST_DAYS = 60


def main():
    """Treino + relatório MAE (modelo vs baseline) + gravação do modelo final."""
    df = add_features(load_daily())
    cutoff = df["day"].max() - pd.Timedelta(days=TEST_DAYS)
    train, test = df[df["day"] <= cutoff], df[df["day"] > cutoff]

    model = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.05, categorical_features=[0], random_state=42
    )
    model.fit(train[FEATURES], train["revenue"])
    pred = model.predict(test[FEATURES])

    mae_model = mean_absolute_error(test["revenue"], pred)
    mae_baseline = mean_absolute_error(test["revenue"], test["lag_7"])
    print(f"Treino: {len(train)} linhas | Teste: {len(test)} linhas (últimos {TEST_DAYS} dias)")
    print(f"MAE baseline (mesmo dia da semana passada): {mae_baseline:.2f} €")
    print(f"MAE modelo: {mae_model:.2f} €")

    # Modelo de produção: todos os dados
    model.fit(df[FEATURES], df["revenue"])
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Modelo guardado em {MODEL_PATH}")


if __name__ == "__main__":
    main()
