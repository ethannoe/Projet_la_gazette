"""Rétention : ce qu'on garde, et combien de temps (le contrat est dans docs/donnees.md)."""

import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import psycopg

from gazette import db

log = logging.getLogger("gazette.retention")

BRUT_JOURS = 90  # articles_bruts/ : de quoi rejouer le nettoyage sur un trimestre
REJETS_JOURS = 90  # même durée que le brut dont ils viennent
PROPRES_JOURS = 365  # articles_propres : un an d'historique pour les thèmes
TECHNIQUE_JOURS = 365  # collectes, controles, rapports


def purger(
    conn: psycopg.Connection,
    articles_dir: str | Path,
    rapports_dir: str | Path,
    maintenant: datetime | None = None,
) -> dict[str, int]:
    maintenant = maintenant or datetime.now(UTC)
    db.migrate(conn)

    def avant(jours: int) -> datetime:
        return maintenant - timedelta(days=jours)

    supprimes = {"brut": 0, "rapports": 0}
    limite_brut = avant(BRUT_JOURS).timestamp()
    for path in Path(articles_dir).glob("*/*.json"):
        if path.stat().st_mtime < limite_brut:  # date d'écriture = date de collecte
            path.unlink()
            supprimes["brut"] += 1
    limite_rapports = avant(TECHNIQUE_JOURS).date()
    for path in Path(rapports_dir).glob("qualite-*.md"):
        try:
            jour = date.fromisoformat(path.stem.removeprefix("qualite-"))
        except ValueError:
            continue
        if jour < limite_rapports:
            path.unlink()
            supprimes["rapports"] += 1

    with conn.transaction():
        for table, colonne, jours in (
            ("rejets", "passage", REJETS_JOURS),
            ("articles_propres", "publie_le", PROPRES_JOURS),
            ("collectes", "debut", TECHNIQUE_JOURS),
            ("controles", "passage", TECHNIQUE_JOURS),
        ):
            cur = conn.execute(f"DELETE FROM {table} WHERE {colonne} < %s", (avant(jours),))
            supprimes[table] = cur.rowcount

    if any(supprimes.values()):
        log.info(
            "rétention : %s", supprimes, extra={"champs": {"evenement": "retention", **supprimes}}
        )
    return supprimes
