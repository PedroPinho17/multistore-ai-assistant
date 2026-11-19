"""Converte os pares em conversas (system/user/assistant) para o fine-tune."""
import json
import random
from datetime import date
from pathlib import Path

from multistore_ai_assistant.assistant.examples import find_similar
from multistore_ai_assistant.assistant.sql_generator import (
    BUSINESS_NOTES,
    SYSTEM_PROMPT,
)
from multistore_ai_assistant.db.schema import get_schema_text

random.seed(42)
PAIRS = Path("data/finetune_pairs.jsonl")
TRAIN = Path("data/finetune_train.jsonl")
VALID = Path("data/finetune_valid.jsonl")
VALID_SHARE = 0.1


def build_system(question: str, schema: str) -> str:
    """Monta o system prompt igual ao de produção (schema + RAG + data de hoje)."""
    similar = find_similar(question)
    examples = "\n\n".join(f"Q: {q}\nSQL: {s}" for q, s in similar) or "(none)"
    return SYSTEM_PROMPT.format(
        schema=schema, notes=BUSINESS_NOTES,
        examples=examples, today=date.today().isoformat(),
    )


def main():
    """Escreve train/valid em formato chat (system / user / assistant)."""
    pairs = [json.loads(line) for line in PAIRS.read_text(encoding="utf-8").splitlines()]
    schema = get_schema_text()  # lido uma vez só
    rows = []
    for i, p in enumerate(pairs, 1):
        rows.append({"messages": [
            {"role": "system", "content": build_system(p["question"], schema)},
            {"role": "user", "content": p["question"]},
            {"role": "assistant", "content": p["sql"]},
        ]})
        if i % 50 == 0:
            print(f"{i}/{len(pairs)}")

    random.shuffle(rows)
    cut = int(len(rows) * VALID_SHARE)
    for path, part in ((VALID, rows[:cut]), (TRAIN, rows[cut:])):
        with path.open("w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{len(part)} conversas em {path}")


if __name__ == "__main__":
    main()
