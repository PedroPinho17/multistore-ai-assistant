"""Histórico da avaliação automática (eval_results) e regras da password do admin."""
import csv
import json
from datetime import datetime

import pytest

from multistore_ai_assistant import eval_results as er
from multistore_ai_assistant.data.create_admin import check_admin_password


def test_summarize_computes_accuracy_per_level():
    s = er.summarize({"easy": [10, 10], "hard": [3, 4]}, always_ok=12, n_items=14, runs=1)
    assert s["accuracy"] == round(13 / 14, 4) and s["always_ok"] == round(12 / 14, 4)
    assert s["by_level"]["hard"] == {"hits": 3, "total": 4, "accuracy": 0.75}


def test_summarize_handles_an_empty_run():
    assert er.summarize({}, 0, 0, 1)["accuracy"] is None


def test_save_result_writes_json_and_appends_to_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "git_commit", lambda: "abc1234")
    summary = er.summarize({"easy": [1, 2]}, 1, 2, 1)
    kwargs = {"model": "m", "level": None, "duration_s": 3.21,
              "results_dir": tmp_path / "results", "history_csv": tmp_path / "history.csv"}
    p1 = er.save_result(summary, [{"id": 1}], when=datetime(2026, 11, 19, 10, 0, 0), **kwargs)
    er.save_result(summary, [], when=datetime(2026, 11, 20, 10, 0, 0), **kwargs)

    data = json.loads(p1.read_text(encoding="utf-8"))
    assert p1.name == "2026-11-19T10-00-00.json"
    assert data["commit"] == "abc1234" and data["level"] == "all" and data["details"] == [{"id": 1}]
    rows = list(csv.DictReader((tmp_path / "history.csv").open(encoding="utf-8")))
    assert len(rows) == 2 and rows[0]["easy"] == "0.5" and rows[0]["accuracy"] == "0.5"


def test_load_history_is_sorted_and_drops_details(tmp_path):
    d = tmp_path / "results"
    d.mkdir()
    (d / "b.json").write_text(json.dumps({"date": "2026-11-20", "details": [1]}), encoding="utf-8")
    (d / "a.json").write_text(json.dumps({"date": "2026-11-19"}), encoding="utf-8")
    (d / "partido.json").write_text("{", encoding="utf-8")
    history = er.load_history(d)
    assert [h["date"] for h in history] == ["2026-11-19", "2026-11-20"]
    assert "details" not in history[1] and history[1]["file"] == "b.json"


def test_load_history_without_results_folder(tmp_path):
    assert er.load_history(tmp_path / "nao-existe") == []


def test_repository_history_has_the_imported_baselines():
    models = {h["model"] for h in er.load_history()}
    assert "openai/gpt-oss-120b" in models and any("Qwen" in m for m in models)


@pytest.mark.parametrize("password,ok", [
    ("curta1", False), ("sóletrasaquiaqui", False), ("123456789012345", False),
    ("dono-da-app-2026", False),          # contém o username
    ("Painel#Seguro-2026", True),
])
def test_admin_password_rules(password, ok):
    assert (check_admin_password("dono", password) is None) is ok
