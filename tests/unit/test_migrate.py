"""Runner de migrações: descoberta, ordem, checksums e o que fica pendente (sem BD)."""
import pytest

from multistore_ai_assistant.db import migrate as mg


def write(d, name, sql="SELECT 1;"):
    (d / name).write_text(sql, encoding="utf-8")


def test_versioned_by_number_then_repeatables(tmp_path):
    for name in ("V010__ten.sql", "V002__two.sql", "R__views.sql", "V001__one.sql", "R__grants.sql"):
        write(tmp_path, name)
    assert [m.path.name for m in mg.discover(tmp_path)] == [
        "V001__one.sql", "V002__two.sql", "V010__ten.sql", "R__grants.sql", "R__views.sql"]


@pytest.mark.parametrize("bad", ["001_x.sql", "V1__x.sql", "V001-x.sql", "V001__X Y.sql", "seed.sql"])
def test_invalid_names_are_rejected(tmp_path, bad):
    write(tmp_path, bad)
    with pytest.raises(ValueError):
        mg.discover(tmp_path)


def test_duplicate_versions_are_rejected(tmp_path):
    write(tmp_path, "V001__a.sql")
    write(tmp_path, "V001__b.sql")
    with pytest.raises(ValueError):
        mg.discover(tmp_path)


def test_checksum_ignores_line_endings(tmp_path):
    (tmp_path / "V001__a.sql").write_bytes(b"SELECT 1;\r\nSELECT 2;\r\n")
    (tmp_path / "V002__b.sql").write_bytes(b"SELECT 1;\nSELECT 2;\n")
    a, b = mg.discover(tmp_path)
    assert a.checksum == b.checksum


def test_pending_rules(tmp_path, caplog):
    write(tmp_path, "V001__done.sql")
    write(tmp_path, "V002__changed.sql", "SELECT 2;")
    write(tmp_path, "V003__new.sql")
    write(tmp_path, "R__same.sql")
    write(tmp_path, "R__edited.sql", "SELECT 'novo';")
    ms = {m.path.name: m for m in mg.discover(tmp_path)}
    done = {"001": ms["V001__done.sql"].checksum, "002": "antigo",
            "R__same": ms["R__same.sql"].checksum, "R__edited": "antigo"}
    todo = [m.path.name for m in mg.pending(list(ms.values()), done)]
    # versionada nova e repetível alterada correm; versionada alterada só avisa
    assert todo == ["V003__new.sql", "R__edited.sql"]
    assert "V002__changed.sql" in caplog.text


def test_no_transaction_marker_and_statement_split(tmp_path):
    write(tmp_path, "V001__idx.sql", "-- migrate: no-transaction\nCREATE INDEX a ON t (x);\n-- nota\nREINDEX DATABASE db;\n")
    m = mg.discover(tmp_path)[0]
    assert not m.transactional
    assert mg.split_statements(m.sql) == ["CREATE INDEX a ON t (x)", "REINDEX DATABASE db"]


def test_project_migrations_are_valid_and_ordered():
    names = [m.path.name for m in mg.discover()]
    assert names[0] == "V001__roles.sql" and names[-1] == "R__readonly.sql"
    assert [m for m in mg.discover() if not m.transactional] == [m for m in mg.discover() if m.version == "006"]
