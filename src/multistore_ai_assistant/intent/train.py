"""Treina o classificador de intenção: MiniLM (embeddings) + LogisticRegression.

Avalia com StratifiedGroupKFold (grupos = templates mascarados) para não
testar a mesma frase com marcas/cidades diferentes. Grava o modelo em
``models/intent.joblib`` e o relatório em ``eval/intent_report.txt``.
"""
import joblib
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold

from multistore_ai_assistant.intent.dataset import LABELS, ROOT, load

EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
THRESHOLD = 0.60
MODEL_PATH = ROOT / "models" / "intent.joblib"
REPORT_PATH = ROOT / "eval" / "intent_report.txt"


def new_clf() -> LogisticRegression:
    """LogReg com classes balanceadas (há menos exemplos de write / off_topic)."""
    return LogisticRegression(max_iter=2000, C=10, class_weight="balanced")


def main() -> None:
    """Gera embeddings, avalia em CV, treina no conjunto completo e grava."""
    texts, labels, groups = load()
    y = np.array(labels)
    print(f"A gerar embeddings de {len(texts)} frases…")
    encoder = SentenceTransformer(EMBED_MODEL)
    X = encoder.encode(texts, normalize_embeddings=True, show_progress_bar=True)

    # Avaliação: 5 folds, cada um testa templates que o modelo nunca viu
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    y_true, y_pred, conf = [], [], []
    for train_idx, test_idx in cv.split(X, y, groups):
        clf = new_clf().fit(X[train_idx], y[train_idx])
        proba = clf.predict_proba(X[test_idx])
        y_true += list(y[test_idx])
        y_pred += list(clf.classes_[proba.argmax(1)])
        conf += list(proba.max(1))
    y_true, y_pred, conf = np.array(y_true), np.array(y_pred), np.array(conf)

    lines = [
        "Classificador de intenção: MiniLM + LogisticRegression",
        f"Avaliação: StratifiedGroupKFold (5 folds, split por template), {len(texts)} frases",
        "",
        classification_report(y_true, y_pred, labels=LABELS, digits=3, zero_division=0),
        "Matriz de confusão (linhas = real, colunas = previsto):",
        "               " + " ".join(f"{name[:8]:>8}" for name in LABELS),
    ]
    for lab, row in zip(LABELS, confusion_matrix(y_true, y_pred, labels=LABELS), strict=False):
        lines.append(f"{lab:<14} " + " ".join(f"{v:>8}" for v in row))
    lines += ["", "Limiar | decididas pelo classificador | accuracy nessas"]
    for th in (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8):
        s = conf >= th
        lines.append(f"  {th:.2f} | {s.mean():6.1%} | {(y_true[s] == y_pred[s]).mean():6.1%}")
    report = "\n".join(lines)
    print(report)
    REPORT_PATH.write_text(report, encoding="utf-8")

    # Modelo final com todos os dados
    clf = new_clf().fit(X, y)
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump({"clf": clf, "embed_model": EMBED_MODEL, "threshold": THRESHOLD}, MODEL_PATH)
    print(f"\nGravado em {MODEL_PATH}")


if __name__ == "__main__":
    main()
