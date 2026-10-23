"""Le collecteur multi-sources : un passage = chaque source active, l'une après l'autre.

Pour chaque source : requête conditionnelle, parse, écriture des nouveaux items,
mise à jour de la table `sources`, une ligne dans `collectes` et une ligne de journal.
Une source en erreur n'arrête jamais le passage ; à 3 échecs de suite, elle dort.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg

from gazette import db
from gazette.fetch import ErreurCollecte, fetch_feed
from gazette.parser import FeedError, parse_feed
from gazette.sources import load_sources
from gazette.stockage import build_item, write_item

log = logging.getLogger("gazette.collecteur")


@dataclass
class Bilan:
    source: str
    statut: str = "echec"  # ok, inchange (304) ou echec
    http: int | None = None
    tentatives: int = 0
    recus: int = 0
    ecrits: int = 0
    ignores: int = 0
    duree_ms: int = 0
    erreur: str | None = None
    echecs_consecutifs: int = 0
    mise_en_sommeil: bool = False


def collect_source(
    conn: psycopg.Connection,
    source: db.EtatSource,
    articles_dir: str | Path,
    *,
    fetch: Callable = fetch_feed,
) -> Bilan:
    debut, t0 = datetime.now(UTC), time.monotonic()
    bilan = Bilan(source=source.id)
    etag, last_modified = source.etag, source.last_modified
    try:
        reponse = fetch(source.url_flux, source.etag, source.last_modified)
        bilan.http, bilan.tentatives = reponse.status, reponse.tentatives
        if reponse.status == 304:
            bilan.statut = "inchange"
        else:
            items = parse_feed(reponse.content)
            recupere_le = datetime.now(UTC).isoformat(timespec="seconds")
            bilan.recus = len(items)
            for parsed in items:
                bilan.ecrits += write_item(articles_dir, build_item(parsed, source.id, recupere_le))
            bilan.ignores = bilan.recus - bilan.ecrits
            bilan.statut = "ok"
        etag, last_modified = reponse.etag, reponse.last_modified
    except ErreurCollecte as exc:
        bilan.http, bilan.tentatives, bilan.erreur = exc.status, exc.tentatives, str(exc)
    except FeedError as exc:
        bilan.erreur = str(exc)
    except Exception as exc:  # un bug sur une source ne doit pas arrêter le passage
        bilan.erreur = f"{type(exc).__name__}: {exc}"
        log.exception("erreur inattendue sur %s", source.id)
    bilan.duree_ms = round((time.monotonic() - t0) * 1000)

    with conn.transaction():
        if bilan.statut != "echec":
            db.record_success(conn, source.id, debut, etag, last_modified)
        elif bilan.http is None and bilan.tentatives:
            # Aucune réponse HTTP (connexion impossible, timeout) : on ne sait pas si la
            # panne vient de la source ou de notre réseau, donc on ne la compte pas pour
            # le sommeil. Le contrôle de fraîcheur (TD 4) alerte si ça dure.
            bilan.echecs_consecutifs = db.record_unreachable(conn, source.id, bilan.erreur)
        else:
            bilan.echecs_consecutifs, bilan.mise_en_sommeil = db.record_failure(
                conn, source.id, debut, bilan.erreur
            )
        db.record_run(conn, debut, bilan)
    _log(bilan)
    return bilan


def collect_all(
    conn: psycopg.Connection,
    sources_file: str | Path,
    articles_dir: str | Path,
    *,
    only: list[str] | None = None,
    delai: timedelta = timedelta(0),
    fetch: Callable = fetch_feed,
) -> list[Bilan]:
    """Un passage complet : migrations, synchro de sources.csv, puis chaque source active.

    `delai` : une source interrogée il y a moins longtemps est laissée pour le prochain
    passage (politesse, et pas de rafale si l'orchestrateur rattrape des passages manqués).
    """
    db.migrate(conn)
    sources = load_sources(sources_file)
    db.sync_sources(conn, sources)
    ids = [s.id for s in sources if not only or s.id in only]
    actives = db.active_sources(conn, ids)
    trop_tot = db.collected_since(conn, datetime.now(UTC) - delai) if delai else set()
    bilans = [
        collect_source(conn, source, articles_dir, fetch=fetch)
        for source in actives
        if source.id not in trop_tot
    ]
    ecrits = sum(b.ecrits for b in bilans)
    echecs = [b.source for b in bilans if b.statut == "echec"]
    en_sommeil = sorted(set(ids) - {s.id for s in actives})
    en_attente = sorted(trop_tot & {s.id for s in actives})
    log.info(
        "passage terminé : %d sources collectées (%d en échec), %d articles écrits ;"
        " %d en sommeil, %d interrogées il y a moins de %s",
        len(bilans),
        len(echecs),
        ecrits,
        len(en_sommeil),
        len(en_attente),
        delai,
        extra={
            "champs": {
                "evenement": "passage",
                "sources": len(bilans),
                "ecrits": ecrits,
                "echecs": echecs,
                "en_sommeil": en_sommeil,
                "en_attente": en_attente,
            }
        },
    )
    return bilans


def _log(bilan: Bilan) -> None:
    champs = {"evenement": "collecte_source", **asdict(bilan)}
    if bilan.mise_en_sommeil:
        log.error(
            "%s mise en sommeil après %d échecs consécutifs (%s) ; pour la relancer : "
            "python -m gazette reveiller %s",
            bilan.source,
            bilan.echecs_consecutifs,
            bilan.erreur,
            bilan.source,
            extra={"champs": champs},
        )
    elif bilan.statut == "echec" and bilan.http is None and bilan.tentatives:
        log.warning(
            "%s injoignable (%s) : non compté pour le sommeil, %d échec(s) compté(s)",
            bilan.source,
            bilan.erreur,
            bilan.echecs_consecutifs,
            extra={"champs": champs},
        )
    elif bilan.statut == "echec":
        log.warning(
            "%s en échec (%d/%d) : %s",
            bilan.source,
            bilan.echecs_consecutifs,
            db.SEUIL_SOMMEIL,
            bilan.erreur,
            extra={"champs": champs},
        )
    else:
        log.info(
            "%s : %d reçus, %d écrits, %d ignorés en %d ms%s",
            bilan.source,
            bilan.recus,
            bilan.ecrits,
            bilan.ignores,
            bilan.duree_ms,
            " (304, inchangé)" if bilan.statut == "inchange" else "",
            extra={"champs": champs},
        )
