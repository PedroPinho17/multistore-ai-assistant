"""Dados de treino do classificador de intenção (sem modelo, sem BD)."""
import csv
from pathlib import Path

import pytest

from multistore_ai_assistant.intent.dataset import load

CSV = Path(__file__).resolve().parents[2] / "data" / "intent_dataset.csv"

# Compras a fornecedores (estado/histórico) são perguntas de dados, não sugestões de encomenda.
# Antes destas frases, o XLM-R mandava "Que compras estão por receber?" para "orders" (99,9 %).
PENDING_PURCHASES = [
    "Que compras estão por receber?", "Quais as compras pendentes?", "Compras por receber",
    "Which purchases are still pending?", "Purchases not yet received",
    "¿Qué compras están pendientes?", "Quels achats sont en attente ?",
]


@pytest.fixture(scope="module")
def dataset() -> dict[str, set[str]]:
    texts, labels, _ = load()
    by_text: dict[str, set[str]] = {}
    for text, label in zip(texts, labels, strict=True):
        by_text.setdefault(text, set()).add(label)
    return by_text


@pytest.mark.parametrize("phrase", PENDING_PURCHASES)
def test_pending_purchases_are_data_questions(dataset, phrase):
    assert dataset.get(phrase) == {"data"}


def test_no_purchase_status_phrase_is_labelled_orders(dataset):
    """Nenhuma frase sobre compras pendentes/recebidas pode ensinar o atalho "orders"."""
    words = ("pendente", "por receber", "recebida", "pending", "not yet received", "en attente")
    wrong = [t for t, labs in dataset.items() if "orders" in labs and any(w in t.lower() for w in words)]
    assert wrong == []


def test_exported_csv_matches_the_dataset(dataset):
    """data/intent_dataset.csv (o que vai para o Kaggle) tem de estar atualizado: python -m ...intent.export"""
    with CSV.open(encoding="utf-8", newline="") as f:
        rows = {(r["text"], r["label"]) for r in csv.DictReader(f)}
    expected = {(t, lab) for t, labs in dataset.items() for lab in labs}
    assert rows == expected
