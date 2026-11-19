"""Histórico da avaliação automática do text-to-SQL.

Cada corrida do ``evaluate`` grava ``eval/results/AAAA-MM-DDTHH-MM-SS.json``
(resumo + detalhe por pergunta) e acrescenta uma linha a ``eval/history.csv``.
Assim a qualidade é medida ao longo do tempo (mudança de modelo, de prompt,
de exemplos RAG), e não só uma vez. O painel admin mostra este histórico.
"""
import csv
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "eval"
RESULTS_DIR = EVAL_DIR / "results"
HISTORY_CSV = EVAL_DIR / "history.csv"
LEVELS = ["easy", "medium", "hard", "refusal"]
CSV_FIELDS = ["date", "model", "runs", "level", "questions", "accuracy", "always_ok",
              *LEVELS, "duration_s", "commit", "source"]


def git_commit() -> str | None:
    """Commit atual (curto), para saber que versão do código foi avaliada."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def summarize(by_level: dict, always_ok: int, n_items: int, runs: int) -> dict:
    """Resumo a partir de ``{nivel: [acertos, tentativas]}``."""
    hits = sum(h for h, _ in by_level.values())
    total = sum(t for _, t in by_level.values())
    return {
        "runs": runs, "questions": n_items, "hits": hits, "total": total,
        "accuracy": round(hits / total, 4) if total else None,
        "always_ok": round(always_ok / n_items, 4) if n_items else None,
        "by_level": {lvl: {"hits": h, "total": t, "accuracy": round(h / t, 4) if t else None}
                     for lvl, (h, t) in by_level.items()},
    }


def save_result(summary: dict, details: list[dict], *, model: str, level: str | None,
                duration_s: float, source: str = "evaluate", when: datetime | None = None,
                results_dir: Path | None = None, history_csv: Path | None = None) -> Path:
    """Grava o JSON da corrida e acrescenta a linha ao CSV; devolve o caminho do JSON."""
    when = when or datetime.now()
    results_dir = results_dir or RESULTS_DIR
    history_csv = history_csv or HISTORY_CSV
    results_dir.mkdir(parents=True, exist_ok=True)
    record = {"date": when.isoformat(timespec="seconds"), "model": model, "level": level or "all",
              "duration_s": round(duration_s, 1), "commit": git_commit(), "source": source,
              **summary, "details": details}
    path = results_dir / f"{when.strftime('%Y-%m-%dT%H-%M-%S')}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    new_file = not history_csv.exists()
    with history_csv.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow({**{k: record.get(k) for k in CSV_FIELDS},
                    **{lvl: (record["by_level"].get(lvl) or {}).get("accuracy") for lvl in LEVELS}})
    return path


def load_history(results_dir: Path | None = None, limit: int = 50) -> list[dict]:
    """Resumos das corridas guardadas (sem o detalhe), da mais antiga para a mais recente."""
    results_dir = results_dir or RESULTS_DIR
    out = []
    for path in sorted(results_dir.glob("*.json"))[-limit:]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        data.pop("details", None)
        data["file"] = path.name
        out.append(data)
    return sorted(out, key=lambda d: d.get("date", ""))
