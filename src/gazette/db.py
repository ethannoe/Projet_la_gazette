"""Accès à PostgreSQL : migrations versionnées et état des sources."""

from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files

import psycopg

from gazette.sources import Source

SEUIL_SOMMEIL = 3  # échecs consécutifs avant la mise en sommeil
_VERROU_MIGRATIONS = 20261022  # verrou consultatif : deux migrations jamais en même temps


@dataclass
class EtatSource:
    id: str
    nom: str
    url_flux: str
    etag: str | None
    last_modified: str | None
    echecs_consecutifs: int


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=True)


def migrate(conn: psycopg.Connection) -> list[str]:
    """Applique, dans l'ordre, les migrations de gazette/migrations/ pas encore passées."""
    applied = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_VERROU_MIGRATIONS,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY, appliquee_le timestamptz NOT NULL DEFAULT now())"
        )
        done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        scripts = sorted(
            (
                f
                for f in files("gazette").joinpath("migrations").iterdir()
                if f.name.endswith(".sql")
            ),
            key=lambda f: f.name,
        )
        for script in scripts:
            version = script.name.removesuffix(".sql")
            if version in done:
                continue
            conn.execute(script.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied.append(version)
    return applied


def sync_sources(conn: psycopg.Connection, sources: list[Source]) -> None:
    """Recopie sources.csv dans la table, sans toucher à l'état des sources connues.

    Une source dont l'adresse change repart de zéro : réveillée, compteurs remis à zéro.
    """
    with conn.transaction():
        for s in sources:
            conn.execute(
                """
                INSERT INTO sources (id, nom, type, url_flux) VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    nom = EXCLUDED.nom,
                    type = EXCLUDED.type,
                    url_flux = EXCLUDED.url_flux,
                    actif = sources.actif OR sources.url_flux <> EXCLUDED.url_flux,
                    echecs_consecutifs = CASE WHEN sources.url_flux <> EXCLUDED.url_flux
                        THEN 0 ELSE sources.echecs_consecutifs END,
                    etag = CASE WHEN sources.url_flux <> EXCLUDED.url_flux
                        THEN NULL ELSE sources.etag END,
                    last_modified = CASE WHEN sources.url_flux <> EXCLUDED.url_flux
                        THEN NULL ELSE sources.last_modified END
                """,
                (s.id, s.name, s.kind, s.url),
            )


def active_sources(conn: psycopg.Connection, ids: list[str]) -> list[EtatSource]:
    """Les sources de la liste qui ne sont pas en sommeil."""
    rows = conn.execute(
        "SELECT id, nom, url_flux, etag, last_modified, echecs_consecutifs FROM sources"
        " WHERE actif AND id = ANY(%s) ORDER BY id",
        (ids,),
    )
    return [EtatSource(*row) for row in rows]


def collected_since(conn: psycopg.Connection, since: datetime) -> set[str]:
    """Les sources déjà interrogées depuis `since`, quel que soit le résultat."""
    rows = conn.execute("SELECT DISTINCT source_id FROM collectes WHERE debut > %s", (since,))
    return {row[0] for row in rows}


def record_success(
    conn: psycopg.Connection,
    source_id: str,
    at: datetime,
    etag: str | None,
    last_modified: str | None,
) -> None:
    conn.execute(
        "UPDATE sources SET derniere_reussite = %s, echecs_consecutifs = 0, derniere_erreur = NULL,"
        " etag = %s, last_modified = %s WHERE id = %s",
        (at, etag, last_modified, source_id),
    )


def record_failure(
    conn: psycopg.Connection, source_id: str, at: datetime, erreur: str
) -> tuple[int, bool]:
    """Compte un échec ; renvoie (échecs consécutifs, mise en sommeil à l'instant)."""
    echecs, actif = conn.execute(
        """
        UPDATE sources SET
            echecs_consecutifs = echecs_consecutifs + 1,
            derniere_erreur = %(erreur)s,
            actif = echecs_consecutifs + 1 < %(seuil)s,
            mise_en_sommeil_le = CASE WHEN echecs_consecutifs + 1 >= %(seuil)s
                THEN %(at)s ELSE mise_en_sommeil_le END
        WHERE id = %(id)s
        RETURNING echecs_consecutifs, actif
        """,
        {"erreur": erreur, "seuil": SEUIL_SOMMEIL, "at": at, "id": source_id},
    ).fetchone()
    return echecs, not actif


def record_unreachable(conn: psycopg.Connection, source_id: str, erreur: str) -> int:
    """Note l'erreur sans toucher au compteur d'échecs ; renvoie ce compteur."""
    (echecs,) = conn.execute(
        "UPDATE sources SET derniere_erreur = %s WHERE id = %s RETURNING echecs_consecutifs",
        (erreur, source_id),
    ).fetchone()
    return echecs


def record_run(conn: psycopg.Connection, debut: datetime, bilan) -> None:
    conn.execute(
        "INSERT INTO collectes (source_id, debut, duree_ms, statut, http_status, tentatives,"
        " recus, ecrits, ignores, erreur, mise_en_sommeil)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            bilan.source,
            debut,
            bilan.duree_ms,
            bilan.statut,
            bilan.http,
            bilan.tentatives,
            bilan.recus,
            bilan.ecrits,
            bilan.ignores,
            bilan.erreur,
            bilan.mise_en_sommeil,
        ),
    )


def wake_up(conn: psycopg.Connection, source_id: str) -> bool:
    row = conn.execute(
        "UPDATE sources SET actif = true, echecs_consecutifs = 0 WHERE id = %s RETURNING id",
        (source_id,),
    ).fetchone()
    return row is not None


def report(conn: psycopg.Connection) -> list[dict]:
    """L'état de chaque source, avec l'historique utile : passages, échecs, sommeils."""
    cur = conn.execute(
        """
        SELECT s.id, s.actif, s.derniere_reussite, s.echecs_consecutifs, s.derniere_erreur,
               s.mise_en_sommeil_le,
               count(c.id) AS passages,
               count(c.id) FILTER (WHERE c.statut = 'echec') AS echecs,
               count(c.id) FILTER (WHERE c.mise_en_sommeil) AS sommeils,
               coalesce(sum(c.ecrits), 0) AS ecrits
        FROM sources s LEFT JOIN collectes c ON c.source_id = s.id
        GROUP BY s.id ORDER BY s.id
        """
    )
    columns = [col.name for col in cur.description]
    return [dict(zip(columns, row, strict=True)) for row in cur]


def forget_rejections(conn: psycopg.Connection, regle: str) -> int:
    """Oublie les rejets d'une règle : le prochain nettoyage les repassera dans les règles."""
    return conn.execute("DELETE FROM rejets WHERE regle = %s", (regle,)).rowcount
