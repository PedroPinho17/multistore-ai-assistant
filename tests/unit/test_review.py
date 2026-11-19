"""Revisão dos 👎 (/review): só quem tem ``teach`` (admin / Imperador) vê, testa, ensina ou ignora."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api import review as review_logic
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.routes import review as review_route
from tests.conftest import ADMIN, IMPERADOR, LOJA, MARCA

client = TestClient(api.app)


def bearer(user) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


class FakeReview:
    """O módulo api.review sem BD: uma lista de 👎 em memória."""

    def __init__(self):
        self.items = {
            1: {"id": 1, "kind": "sql", "question": "Faturação por loja?", "sql": "SELECT 1"},
            2: {"id": 2, "kind": "forecast", "question": "Quanto vou vender?", "sql": None},
        }
        self.taught, self.dismissed = [], []

    def pending(self):
        return {"pending": len(self.items), "items": list(self.items.values())}

    def _get(self, rid):
        if rid not in self.items:
            raise ApiError("review_not_found", 404)
        return self.items[rid]

    def preview(self, rid, sql, user):
        self._get(rid)
        return {"sql": sql, "columns": ["x"], "rows": [[1]], "row_count": 1}

    def teach(self, rid, question, sql, user):
        if self._get(rid)["kind"] in review_logic.NOT_SQL_KINDS:
            raise ApiError("review_not_sql", 400)
        self.taught.append((rid, question, sql, user["username"]))
        del self.items[rid]

    def dismiss(self, rid, user):
        self._get(rid)
        self.dismissed.append((rid, user["username"]))
        del self.items[rid]


@pytest.fixture
def fake(monkeypatch):
    f = FakeReview()
    monkeypatch.setattr(review_route, "review_db", f)
    return f


# ---------- quem pode rever ----------

@pytest.mark.parametrize("user", [IMPERADOR, ADMIN])
def test_imperador_and_admin_see_the_list(fake, user):
    r = client.get("/review", headers=bearer(user))
    assert r.status_code == 200 and r.json()["pending"] == 2


@pytest.mark.parametrize("user", [MARCA, LOJA])
def test_brand_and_store_managers_cannot_review(fake, user):
    for method, path in (("get", "/review"), ("post", "/review/1/dismiss")):
        r = getattr(client, method)(path, headers=bearer(user))
        assert r.status_code == 403 and r.json()["detail"]["code"] == "no_module"
    assert len(fake.items) == 2


def test_an_imperador_without_teach_cannot_review(fake, fake_users):
    fake_users[IMPERADOR["username"]]["modules"] = ["sql", "forecast"]
    assert client.get("/review", headers=bearer(IMPERADOR)).status_code == 403


def test_review_requires_login(fake):
    assert client.get("/review").status_code in (401, 403)


# ---------- ensinar e ignorar ----------

def test_teaching_removes_the_item_from_the_list(fake):
    body = {"question": "Faturação de cada loja", "sql": "SELECT 2"}
    assert client.post("/review/1/teach", json=body, headers=bearer(IMPERADOR)).json() == {"ok": True}
    assert fake.taught == [(1, "Faturação de cada loja", "SELECT 2", IMPERADOR["username"])]
    listed = client.get("/review", headers=bearer(IMPERADOR)).json()
    assert [i["id"] for i in listed["items"]] == [2] and listed["pending"] == 1


def test_dismissing_removes_the_item_without_teaching(fake):
    assert client.post("/review/2/dismiss", headers=bearer(ADMIN)).status_code == 200
    assert fake.dismissed == [(2, ADMIN["username"])] and fake.taught == [] and 2 not in fake.items


def test_forecast_answers_can_only_be_dismissed(fake):
    r = client.post("/review/2/teach", json={"question": "q", "sql": "SELECT 1"}, headers=bearer(IMPERADOR))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "review_not_sql"


def test_an_item_already_reviewed_is_404(fake):
    client.post("/review/1/dismiss", headers=bearer(IMPERADOR))
    r = client.post("/review/1/teach", json={"question": "q", "sql": "SELECT 1"},
                    headers={**bearer(IMPERADOR), "Accept-Language": "en"})
    assert r.status_code == 404 and r.json()["detail"]["message"] == "This answer is no longer waiting for review."


@pytest.mark.parametrize("body", [{"question": "", "sql": "SELECT 1"}, {"question": "q", "sql": ""},
                                  {"question": "q", "sql": "x" * 10_001}])
def test_teach_validates_input(fake, body):
    assert client.post("/review/1/teach", json=body, headers=bearer(IMPERADOR)).status_code == 422


# ---------- validação real do SQL (api.review com a BD simulada) ----------

@pytest.fixture
def logic(monkeypatch):
    calls = {"examples": [], "marked": [], "ran": []}
    monkeypatch.setattr(review_logic, "_get_pending", lambda rid: {"id": rid, "kind": "sql"})
    monkeypatch.setattr(review_logic, "_mark", lambda rid, user, action, conn=None: calls["marked"].append((rid, action, conn)))
    monkeypatch.setattr(review_logic, "add_example",
                        lambda q, s, source, created_by=None, conn=None: calls["examples"].append((q, s, source, created_by, conn)))

    class Conn:                                   # uma só ligação = uma só transação
        def __enter__(self):
            return "tx"

        def __exit__(self, *exc):
            return False
    monkeypatch.setattr(review_logic, "connection", lambda kind: Conn())

    def run_query(sql, user):
        calls["ran"].append((sql, user["role"]))
        return ["n"], [[i] for i in range(30)]
    monkeypatch.setattr(review_logic, "run_query", run_query)
    return calls


def test_teach_uses_the_same_checks_as_feedback(logic):
    review_logic.teach(1, "  Faturação?  ", "SELECT 1", IMPERADOR)
    assert logic["ran"] == [("EXPLAIN SELECT 1", "imperador")]
    assert logic["examples"] == [("Faturação?", "SELECT 1", "review", "pedro", "tx")]
    assert logic["marked"] == [(1, "taught", "tx")]                       # exemplo e 👎 na MESMA transação


@pytest.mark.parametrize("sql", ["DELETE FROM sales", "SELECT 1; SELECT 2", "SELECT set_config('app.role','x',true)"])
def test_dangerous_sql_is_never_taught(logic, sql):
    with pytest.raises(ApiError) as e:
        review_logic.teach(1, "q", sql, IMPERADOR)
    assert e.value.code == "invalid_sql" and logic["examples"] == [] and logic["marked"] == []


def test_sql_that_does_not_run_is_not_taught(logic, monkeypatch):
    def broken(sql, user):
        raise psycopg.errors.UndefinedColumn("coluna x")
    monkeypatch.setattr(review_logic, "run_query", broken)
    with pytest.raises(ApiError) as e:
        review_logic.teach(1, "q", "SELECT x FROM sales", IMPERADOR)
    assert e.value.code == "sql_not_running" and logic["marked"] == []


def test_preview_runs_with_the_reviewer_rls_and_trims_rows(logic):
    out = review_logic.preview(1, "SELECT n FROM t", IMPERADOR)
    assert logic["ran"] == [("SELECT n FROM t", "imperador")]
    assert out["row_count"] == 30 and len(out["rows"]) == review_logic.PREVIEW_ROWS
    assert logic["examples"] == [] and logic["marked"] == []          # testar não ensina nem tira da lista
