"""Pontua SQL gerado fora (ex.: Qwen no Kaggle) com a mesma lógica do evaluate.py.

Uso:  python -m multistore_ai_assistant.finetune.score eval/preds_qwen_ft.jsonl [eval/preds_qwen_base.jsonl ...]
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from multistore_ai_assistant.assistant.sql_validator import validate_sql
from multistore_ai_assistant.db.query import IMPERADOR, run_query
from multistore_ai_assistant.evaluate import EVAL_FILE, LEVELS, SPECIAL, matches

FENCE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE)


def clean(sql: str) -> str:
    """Remove fences Markdown do SQL gerado (blocos tipo sql)."""
    return FENCE.sub("", sql.strip()).strip()


def score_one(item, gold, sql):
    """Avalia uma previsão; devolve ``(acertou, sql_ou_erro)``."""
    if item.get("expect") == "NO_SQL":
        return sql == "NO_SQL", sql
    if sql in SPECIAL:
        return False, sql
    try:
        sql = validate_sql(sql)
        _, pred = run_query(sql, IMPERADOR)
    except Exception as e:
        return False, f"{sql}\n     ERRO: {e}"
    return matches(gold, pred), sql


def score_file(path: Path, items):
    """Pontua um ficheiro de previsões e imprime o relatório por nível."""
    preds = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            p = json.loads(line)
            preds[p["n"]] = clean(p["sql"])

    by_level = defaultdict(lambda: [0, 0])
    print(f"\n=== {path.name} ===")
    for n, item in enumerate(items, 1):
        level = item.get("level", "?")
        gold = None
        if item.get("sql"):
            try:
                _, gold = run_query(item["sql"], IMPERADOR)
            except Exception as e:
                print(f"[!!] {n}. SQL de referência falhou, ignorada: {e}")
                continue
        ok, shown = score_one(item, gold, preds.get(n, ""))
        by_level[level][0] += ok
        by_level[level][1] += 1
        print(f"[{'OK' if ok else 'X '}] {item.get('id', n)}. ({level}) {item['q']}")
        if not ok:
            print("     SQL: " + shown.replace("\n", "\n          "))

    print("\nPor nível:")
    for level in LEVELS + sorted(set(by_level) - set(LEVELS)):
        if level in by_level:
            h, t = by_level[level]
            print(f"  {level:<8} {h:>3}/{t:<3} = {100 * h / t:5.1f} %")
    hits = sum(h for h, _ in by_level.values())
    total = sum(t for _, t in by_level.values())
    print(f"Execution accuracy: {hits}/{total} = {100 * hits / total:.1f} %")
    return hits, total


def main():
    """Aceita um ou mais ficheiros ``.jsonl`` de previsões e compara accuracy."""
    items = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    results = [(Path(a).name, *score_file(Path(a), items)) for a in sys.argv[1:]]
    if len(results) > 1:
        print("\nResumo:")
        for name, h, t in results:
            print(f"  {name:<28} {h}/{t} = {100 * h / t:.1f} %")


if __name__ == "__main__":
    main()
