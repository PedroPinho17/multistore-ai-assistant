"""Exemplos do RAG (/examples): só quem tem ``teach``; SQL validado como no /feedback."""
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth, rag_examples
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.routes import examples as examples_route
from tests.conftest import ADMIN, IMPERADOR, LOJA, MARCA

client = TestClient(api.app)


def bearer(user) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


class FakeExamples:
    def __init__(self):
        self.rows = {1: {"id": 1, "question": "Faturação por marca", "sql": "SELECT 1", "source": "seed", "uses": 4}}

    def list_examples(self):
        return list(self.rows.values())

    def create(self, question, sql, user):
        if any(r["question"].lower() == question.strip().lower() for r in self.rows.values()):
            raise ApiError("example_exists", 409)
        new_id = max(self.rows) + 1
        self.rows[new_id] = {"id": new_id, "question": question.strip(), "sql": sql, "source": "manual",
                             "created_by": user["username"], "uses": 0}
        return new_id

    def update(self, example_id, question, sql, user):
        if example_id not in self.rows:
            raise ApiError("example_not_found", 404)
        self.rows[example_id].update(question=question, sql=sql, updated_by=user["username"])

    def delete(self, example_id):
        if self.rows.pop(example_id, None) is None:
            raise ApiError("example_not_found", 404)


@pytest.fixture
def fake(monkeypatch):
    f = FakeExamples()
    monkeypatch.setattr(examples_route, "rag_examples", f)
    return f


@pytest.mark.parametrize("user", [ADMIN, IMPERADOR])
def test_teachers_list_examples(fake, user):
    r = client.get("/examples", headers=bearer(user))
    assert r.status_code == 200 and r.json()["examples"][0]["uses"] == 4


@pytest.mark.parametrize("user", [MARCA, LOJA])
def test_others_cannot_see_or_change_examples(fake, user):
    h = bearer(user)
    for r in (client.get("/examples", headers=h), client.delete("/examples/1", headers=h),
              client.post("/examples", json={"question": "abc", "sql": "SELECT 1"}, headers=h)):
        assert r.status_code == 403
    assert 1 in fake.rows


def test_create_edit_delete(fake):
    h = bearer(IMPERADOR)
    r = client.post("/examples", json={"question": "Top 3 lojas", "sql": "SELECT 2"}, headers=h)
    assert r.status_code == 201 and fake.rows[r.json()["id"]]["created_by"] == "pedro"
    assert client.put("/examples/1", json={"question": "Faturação de cada marca", "sql": "SELECT 3"}, headers=h).status_code == 200
    assert fake.rows[1]["sql"] == "SELECT 3"
    assert client.delete("/examples/1", headers=h).status_code == 200 and 1 not in fake.rows
    assert client.delete("/examples/1", headers=h).json()["detail"]["code"] == "example_not_found"


def test_duplicate_question_is_refused_not_overwritten(fake):
    r = client.post("/examples", json={"question": "faturação POR marca ", "sql": "SELECT 9"}, headers=bearer(IMPERADOR))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "example_exists" and fake.rows[1]["sql"] == "SELECT 1"


@pytest.mark.parametrize("body", [{"question": "ab", "sql": "SELECT 1"}, {"question": "abc", "sql": ""}])
def test_input_is_validated(fake, body):
    assert client.post("/examples", json=body, headers=bearer(IMPERADOR)).status_code == 422


def test_create_and_update_validate_the_sql(monkeypatch):
    def refuse(sql, user):
        raise ApiError("invalid_sql", 400, reason="DELETE")
    monkeypatch.setattr(rag_examples, "teachable_sql", refuse)
    monkeypatch.setattr(rag_examples, "connection", lambda kind: pytest.fail("não devia tocar na BD"))
    for call in (lambda: rag_examples.create("q", "DELETE FROM sales", IMPERADOR),
                 lambda: rag_examples.update(1, "q", "DELETE FROM sales", IMPERADOR)):
        with pytest.raises(ApiError) as e:
            call()
        assert e.value.code == "invalid_sql"


def test_preview_uses_the_editor_rls(monkeypatch, fake):
    seen = []
    monkeypatch.setattr(examples_route.review_db, "run_preview",
                        lambda sql, user: seen.append(user["role"]) or {"columns": ["x"], "rows": [[1]], "row_count": 1})
    r = client.post("/examples/preview", json={"sql": "SELECT 1"}, headers=bearer(IMPERADOR))
    assert r.status_code == 200 and seen == ["imperador"]
