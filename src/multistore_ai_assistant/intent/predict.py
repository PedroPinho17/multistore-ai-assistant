"""Classifica a intenção de uma pergunta (carrega o modelo uma só vez).

``INTENT_MODEL`` no ``.env`` escolhe o classificador:
  ``xlmr``   → XLM-RoBERTa afinado (``models/intent-xlmr``)
  ``minilm`` → MiniLM + LogisticRegression (``models/intent.joblib``)

Se o XLM-R não existir na pasta, usa o MiniLM. Se nenhum existir, devolve
``(None, 0.0)`` e o LLM decide sozinho.

Etiquetas: ``data``, ``forecast``, ``orders``, ``chat``, ``personal_data``,
``write``, ``off_topic``.
"""
import os
import re
from functools import lru_cache

import joblib
from dotenv import load_dotenv

from multistore_ai_assistant.intent.dataset import LABELS, ROOT
from multistore_ai_assistant.intent.train import MODEL_PATH

load_dotenv()
# Caminho absoluto: funciona seja qual for a pasta de onde se arranca o uvicorn
XLMR_PATH = ROOT / "models" / "intent-xlmr"
XLMR_THRESHOLD = 0.90

# Cumprimento no início da frase (PT/EN/ES/FR); se só restar isso → chat
GREETING = re.compile(
    r"^\s*(olá|ola|oi|bom dia|boa tarde|boa noite|hello|hi|hey|good (morning|afternoon|evening)"
    r"|hola|buenos días|buenos dias|buenas tardes|buenas noches|bonjour|bonsoir|salut)\b[\s,!.¡]*",
    re.I,
)


def strip_greeting(question: str) -> str:
    """Remove um cumprimento inicial; o resto é o que o classificador vê."""
    return GREETING.sub("", question).strip()


def backend() -> str:
    """Qual backend está disponível: ``xlmr``, ``minilm`` ou ``none``."""
    wanted = os.getenv("INTENT_MODEL", "xlmr").lower()
    if wanted == "xlmr" and (XLMR_PATH / "model.safetensors").exists():
        return "xlmr"
    return "minilm" if MODEL_PATH.exists() else "none"


@lru_cache(maxsize=1)
def _load_minilm():
    """Carrega LogReg + encoder MiniLM a partir do joblib."""
    from sentence_transformers import SentenceTransformer
    bundle = joblib.load(MODEL_PATH)
    return bundle["clf"], SentenceTransformer(bundle["embed_model"]), bundle["threshold"]


@lru_cache(maxsize=1)
def _load_xlmr():
    """Carrega tokenizer + modelo XLM-R fine-tuned."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))
    tok = AutoTokenizer.from_pretrained(XLMR_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(XLMR_PATH).eval()
    return tok, model


def xlmr_labels(config) -> list[str]:
    """Nomes das classes pela ordem das saídas do modelo.

    Usa ``id2label`` do modelo quando tem nomes reais; modelos antigos têm
    ``LABEL_0…`` e então vale a ordem de ``LABELS`` (a mesma do treino).
    """
    names = [config.id2label[i] for i in range(config.num_labels)]
    if all(n.startswith("LABEL_") for n in names):
        names = list(LABELS)
    if len(names) != len(LABELS) or set(names) != set(LABELS):
        raise RuntimeError(f"O modelo XLM-R tem as classes {names}, mas o código espera {LABELS}.")
    return names


def _proba_xlmr(text: str):
    """Vector de probabilidades por classe (ordem = ``LABELS``)."""
    import torch
    tok, model = _load_xlmr()
    with torch.no_grad():
        logits = model(**tok(text, truncation=True, max_length=64, return_tensors="pt")).logits
    return torch.softmax(logits, dim=-1)[0].numpy()


def classify(question: str) -> tuple[str | None, float]:
    """Classifica a intenção da pergunta.

    Returns:
        ``(intenção, confiança)``. Intenção ``None`` = abaixo do limiar;
        o assistente deixa o LLM decidir.
    """
    rest = strip_greeting(question)
    if not rest or len(rest) <= 2:  # só um cumprimento ("Olá!", "Bom dia")
        return "chat", 1.0
    which = backend()
    if which == "xlmr":
        proba, labels, threshold = _proba_xlmr(rest), xlmr_labels(_load_xlmr()[1].config), XLMR_THRESHOLD
    elif which == "minilm":
        clf, encoder, threshold = _load_minilm()
        proba = clf.predict_proba(encoder.encode([rest], normalize_embeddings=True))[0]
        labels = [str(c) for c in clf.classes_]
    else:
        return None, 0.0
    i = int(proba.argmax())
    return (labels[i] if proba[i] >= threshold else None), float(proba[i])


if __name__ == "__main__":
    import sys
    print("Classificador:", backend())
    for q in sys.argv[1:] or [
        "Olá!", "Olá, quanto faturou Braga em agosto?", "Vendas de Gaia na semana passada",
        "Qual é a morada da Sofia?", "Quanto vamos faturar amanhã?",
        "Que ingredientes faltam?", "Altera o stock do pão", "Qual a capital de Espanha?",
    ]:
        print(f"{classify(q)}  {q}")
