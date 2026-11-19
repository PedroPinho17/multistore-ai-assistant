"""Execution accuracy do text-to-SQL (perguntas em eval/questions.json).

Corre cada pergunta RUNS vezes, porque o LLM nem sempre gera o mesmo SQL.
Cada corrida fica guardada com data em ``eval/results/`` e ``eval/history.csv``
(ver ``eval_results``), para medir a qualidade ao longo do tempo.

Uso:  python -m multistore_ai_assistant.evaluate [runs] [nivel] [--no-save]
      ex.: ... evaluate 1 hard
"""
import json
import os
import re
import sys
import time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import psycopg

from .assistant.sql_generator import generate_sql
from .assistant.sql_validator import InvalidSQL, validate_sql
from .db.query import IMPERADOR, run_query
from .eval_results import save_result, summarize

EVAL_FILE = Path(__file__).resolve().parents[2] / "eval" / "questions.json"
RUNS = 3
SLEEP = 1.0
LEVELS = ["easy", "medium", "hard", "refusal"]
SPECIAL = ("NO_SQL", "FORECAST", "ORDERS")


class DailyLimit(Exception):
    pass


def generate_with_retry(question: str) -> str:
    """Chama ``generate_sql`` com retries em rate-limit (429) da API."""
    for _ in range(5):
        try:
            return generate_sql(question)
        except Exception as e:
            msg = str(e)
            if "429" not in msg:
                raise
            if "tokens per day" in msg:
                raise DailyLimit(msg) from e
            wait = re.search(r"try again in ([\d.]+)s", msg)
            time.sleep(float(wait.group(1)) + 1 if wait else 10)
    raise RuntimeError("Limite de pedidos: 5 tentativas falhadas")


def same(a, b) -> bool:
    """Compara valores com tolerância numérica (euros / arredondamentos)."""
    if isinstance(a, (int, float, Decimal)) and isinstance(b, (int, float, Decimal)):
        a, b = float(a), float(b)
        return abs(a - b) <= max(0.06, 0.005 * abs(a))
    return str(a).strip().lower() == str(b).strip().lower()


def row_in(gold_row, pred_row) -> bool:
    """True se cada valor da linha gold aparece em algum sítio da linha predita."""
    return all(any(same(g, p) for p in pred_row) for g in gold_row)


def matches(gold, pred) -> bool:
    """Execution accuracy: mesmas linhas (ordem/colunas podem diferir)."""
    if len(gold) != len(pred):
        return False
    return all(any(row_in(gr, pr) for pr in pred) for gr in gold)


def run_once(item, gold):
    """Devolve (acertou, sql_gerado_ou_erro)."""
    try:
        sql = generate_with_retry(item["q"]).strip()
    except DailyLimit:
        raise
    except Exception as e:  # erro da API do LLM, limite de pedidos, etc.
        return False, f"ERRO LLM: {e}"

    if item.get("expect") == "NO_SQL":
        # Só conta como certo se o LLM recusar. FORECAST/ORDERS ou SQL = falha.
        return sql == "NO_SQL", sql

    if sql in SPECIAL:
        return False, sql
    try:
        sql = validate_sql(sql)
        _, pred = run_query(sql, IMPERADOR)
    except (InvalidSQL, psycopg.Error) as e:
        return False, f"{sql}\n     ERRO: {e}".strip()
    except Exception as e:
        return False, f"{sql}\n     ERRO: {e}".strip()
    return matches(gold, pred), sql


def main(argv: list[str] | None = None):
    """Corre o benchmark, imprime accuracy por nível e global, e guarda o resultado."""
    args = list(sys.argv[1:] if argv is None else argv)
    save = "--no-save" not in args
    args = [a for a in args if a != "--no-save"]
    runs = int(args[0]) if args else RUNS
    only = args[1] if len(args) > 1 else None
    started = time.monotonic()
    details = []
    items = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    if only:
        items = [it for it in items if it.get("level") == only]

    by_level = defaultdict(lambda: [0, 0])   # nivel -> [acertos, tentativas]
    always_ok = 0

    for n, item in enumerate(items, 1):
        level = item.get("level", "?")
        gold = None
        if item.get("sql"):
            try:
                _, gold = run_query(item["sql"], IMPERADOR)
            except Exception as e:
                print(f"[!!] {n}. SQL de referência falhou, pergunta ignorada: {e}")
                continue

        hits, fails = 0, []
        try:
            for _ in range(runs):
                ok, sql = run_once(item, gold)
                hits += ok
                if not ok and sql not in fails:
                    fails.append(sql)
                time.sleep(SLEEP)
        except DailyLimit:
            print("\nLimite diário do Groq atingido. Corre o resto mais tarde, por exemplo: evaluate 1 hard")
            break

        by_level[level][0] += hits
        by_level[level][1] += runs
        details.append({"id": item.get("id", n), "level": level, "question": item["q"],
                        "hits": hits, "runs": runs, "fails": fails[:3]})
        always_ok += hits == runs
        mark = "OK" if hits == runs else ("~ " if hits else "X ")
        print(f"[{mark}] {hits}/{runs}  {item.get('id', n)}. ({level}) {item['q']}")
        if fails:
            # Mostra cada SQL errado uma só vez por pergunta.
            for sql in fails:
                print("     SQL: " + sql.replace("\n", "\n          "))

    total_hits = sum(h for h, _ in by_level.values())
    total_runs = sum(t for _, t in by_level.values())
    if not total_runs:
        print("Nenhuma pergunta avaliada.")
        return
    print("\nPor nível:")
    for level in LEVELS + sorted(set(by_level) - set(LEVELS)):
        if level in by_level:
            h, t = by_level[level]
            print(f"  {level:<8} {h:>3}/{t:<3} = {100 * h / t:5.1f} %")
    n_items = total_runs // runs
    print(f"\nExecution accuracy ({runs} corridas): {total_hits}/{total_runs} = "
          f"{100 * total_hits / total_runs:.1f} %")
    print(f"Perguntas sempre certas: {always_ok}/{n_items} = {100 * always_ok / n_items:.1f} %")
    if save:
        path = save_result(summarize(dict(by_level), always_ok, n_items, runs), details,
                           model=os.getenv("LLM_MODEL", "?"), level=only,
                           duration_s=time.monotonic() - started)
        print(f"\nResultado guardado em eval/results/{path.name} (e em eval/history.csv)")


if __name__ == "__main__":
    main()
