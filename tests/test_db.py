import pytest

from gazette import db


def test_migrations_appliquees_une_seule_fois(conn):
    assert db.migrate(conn) == ["001_sources", "002_collectes"]
    assert db.migrate(conn) == []
    versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations")]
    assert versions == ["001_sources", "002_collectes"]


def test_table_sources_a_les_colonnes_attendues(conn):
    db.migrate(conn)
    colonnes = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'sources'"
        )
    }
    assert colonnes >= {
        "nom", "type", "url_flux", "actif", "derniere_reussite",
        "echecs_consecutifs", "etag", "last_modified",
    }  # fmt: skip


def test_type_de_source_controle(conn):
    import psycopg

    db.migrate(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO sources (id, nom, type, url_flux) VALUES ('x', 'X', 'BLOG', 'u')")
