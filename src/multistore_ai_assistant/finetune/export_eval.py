"""Exporta as perguntas do eval com o prompt de sistema, para gerar SQL no Kaggle."""
import json
from pathlib import Path

from multistore_ai_assistant.db.schema import get_schema_text
from multistore_ai_assistant.evaluate import EVAL_FILE
from multistore_ai_assistant.finetune.export_chat import build_system

OUT = Path("data/eval_prompts.jsonl")


def main():
    """Escreve ``data/eval_prompts.jsonl`` com system+user (sem a resposta SQL)."""
    items = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    schema = get_schema_text()
    with OUT.open("w", encoding="utf-8") as f:
        for n, item in enumerate(items, 1):
            row = {"n": n, "messages": [
                {"role": "system", "content": build_system(item["q"], schema)},
                {"role": "user", "content": item["q"]},
            ]}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(items)} perguntas em {OUT}")


if __name__ == "__main__":
    main()
