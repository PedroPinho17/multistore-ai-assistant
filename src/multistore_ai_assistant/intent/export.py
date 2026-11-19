"""Exporta o dataset de intenções para CSV (treino XLM-R no Kaggle, Opção B).

Colunas: ``text``, ``label``, ``group`` (template mascarado para o split).
"""
import csv
from pathlib import Path

from multistore_ai_assistant.intent.dataset import load

OUT = Path("data/intent_dataset.csv")

if __name__ == "__main__":
    texts, labels, groups = load()
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["text", "label", "group"])
        w.writerows(zip(texts, labels, groups, strict=False))
    print(f"{len(texts)} frases gravadas em {OUT}")
