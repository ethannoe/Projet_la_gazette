"""Après la collecte : nettoyage, contrôles de qualité, rapport, rétention.

Les mêmes étapes servent à la ligne de commande et aux tâches Prefect (flows.py).
"""

from datetime import UTC, date, datetime
from pathlib import Path

import psycopg

from gazette import controles, nettoyage, rapport, regles, retention, themes
from gazette.config import Config
from gazette.embeddings import EncodeurFastembed
from gazette.sources import load_sources


def nettoyer(conn: psycopg.Connection, cfg: Config) -> nettoyage.BilanNettoyage:
    return nettoyage.nettoyer(conn, cfg.articles_dir, regles.charger(cfg.regles_file))


def controler(conn: psycopg.Connection, cfg: Config) -> list[controles.Resultat]:
    actives = [s.id for s in load_sources(cfg.sources_file)]
    seuils = regles.charger(cfg.regles_file).seuils
    return controles.controler(conn, seuils, actives, cfg.alerte_webhook)


def rapporter(
    conn: psycopg.Connection,
    cfg: Config,
    dernier: nettoyage.BilanNettoyage | None = None,
    jour: date | None = None,
) -> tuple[Path, str]:
    jour = jour or (dernier.passage if dernier else datetime.now(UTC)).date()
    contenu = rapport.construire(conn, jour, regles.charger(cfg.regles_file), dernier)
    return rapport.ecrire(cfg.rapports_dir, jour, contenu), contenu


def retenir(conn: psycopg.Connection, cfg: Config) -> dict[str, int]:
    return retention.purger(conn, cfg.articles_dir, cfg.rapports_dir, cfg.runs_dir)


def regrouper(
    conn: psycopg.Connection,
    cfg: Config,
    *,
    declencheur: str = "manuel",
    fin: datetime | None = None,
) -> themes.Run | None:
    """Un run de regroupement tracé. Lancé par le pipeline, il ne tourne qu'une fois par jour."""
    config_themes = themes.charger_config(cfg.clustering_file)
    if declencheur == "pipeline" and not themes.run_du_jour_attendu(
        conn, config_themes, datetime.now(UTC)
    ):
        return None
    encodeur = EncodeurFastembed(config_themes["embeddings"]["modele"], cfg.modeles_dir)
    return themes.executer(
        conn,
        config_themes,
        encodeur,
        fin=fin,
        declencheur=declencheur,
        runs_dir=cfg.runs_dir,
        code_version=cfg.code_version,
        racine=Path(cfg.clustering_file).resolve().parents[1],
    )


def tracer(conn: psycopg.Connection, cfg: Config, cle: str) -> dict | None:
    """D'un article (id ou lien), retrouver son sort, sa source et son item brut."""
    row = conn.execute(
        """
        SELECT 'gardé', item_id, source_id, lien, titre, NULL, NULL, passage
        FROM articles_propres WHERE item_id = %(cle)s OR lien = %(cle)s
        UNION ALL
        SELECT 'rejeté', item_id, source_id, lien, titre, regle, detail, passage
        FROM rejets WHERE item_id = %(cle)s OR lien = %(cle)s
        """,
        {"cle": cle},
    ).fetchone()
    if row is None:
        return None
    sort, item_id, source_id, lien, titre, regle, detail, passage = row
    nom, url_flux = conn.execute(
        "SELECT nom, url_flux FROM sources WHERE id = %s", (source_id,)
    ).fetchone()
    brut = Path(cfg.articles_dir) / source_id / f"{item_id}.json"
    return {
        "sort": sort,
        "regle": regle,
        "detail": detail,
        "titre": titre,
        "lien": lien,
        "passage": passage,
        "source": f"{nom} ({source_id}), flux {url_flux}",
        "item_brut": str(brut) if brut.exists() else f"{brut} (purgé : plus de 90 jours)",
    }
