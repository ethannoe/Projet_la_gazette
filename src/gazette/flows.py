"""Orchestration Prefect : un passage toutes les N minutes, en six tâches.

collecte → nettoyage → contrôles de qualité → rapport → thèmes (une fois par jour) → rétention

`planifier()` enregistre le déploiement auprès du serveur Prefect (PREFECT_API_URL)
puis exécute lui-même les passages prévus. L'historique, les journaux, les métriques
des contrôles et le rapport de chaque passage sont visibles dans l'interface Prefect
(http://localhost:4200, onglet Artifacts).
"""

from dataclasses import asdict
from datetime import timedelta

from prefect import flow, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact
from prefect.cache_policies import NO_CACHE

from gazette import config, db, journal, pipeline
from gazette.collecteur import collect_all
from gazette.config import Config
from gazette.nettoyage import BilanNettoyage


@task(name="collecte", cache_policy=NO_CACHE)
def tache_collecte(cfg: Config) -> list:
    with db.connect(cfg.database_url) as conn:
        return collect_all(
            conn, cfg.sources_file, cfg.articles_dir, delai=timedelta(minutes=cfg.delai_min)
        )


@task(name="nettoyage", cache_policy=NO_CACHE)
def tache_nettoyage(cfg: Config) -> BilanNettoyage:
    with db.connect(cfg.database_url) as conn:
        return pipeline.nettoyer(conn, cfg)


@task(name="controles-qualite", cache_policy=NO_CACHE)
def tache_controles(cfg: Config) -> list:
    with db.connect(cfg.database_url) as conn:
        resultats = pipeline.controler(conn, cfg)
    create_table_artifact(
        key="controles-qualite",
        table=[asdict(r) for r in resultats],
        description="Contrôles de qualité du dernier passage (historique : table controles)",
    )
    return resultats


@task(name="rapport-qualite", cache_policy=NO_CACHE)
def tache_rapport(cfg: Config, bilan: BilanNettoyage) -> str:
    with db.connect(cfg.database_url) as conn:
        path, contenu = pipeline.rapporter(conn, cfg, bilan)
    create_markdown_artifact(key="rapport-qualite", markdown=contenu, description=str(path))
    return str(path)


@task(name="themes", cache_policy=NO_CACHE)
def tache_themes(cfg: Config) -> str | None:
    """Le regroupement du jour, tracé dans la table runs ; ne tourne qu'une fois par jour."""
    with db.connect(cfg.database_url) as conn:
        run = pipeline.regrouper(conn, cfg, declencheur="pipeline")
    if run is None:
        return None
    lignes = [
        f"# Thèmes du run {run.run_id}",
        "",
        f"{run.nb_articles} articles, {run.metriques['nb_themes']} thèmes, "
        f"{run.metriques['part_bruit']:.0%} de bruit, silhouette {run.metriques['silhouette']}",
        "",
        "| # | Thème | Articles | Mots-clés |",
        "|---|---|---|---|",
        *(
            f"| {t['numero']} | {t['nom']} | {t['taille']} | {', '.join(t['mots_cles'])} |"
            for t in run.themes
        ),
    ]
    create_markdown_artifact(
        key="themes-du-jour", markdown="\n".join(lignes), description=run.run_id
    )
    return run.run_id


@task(name="retention", cache_policy=NO_CACHE)
def tache_retention(cfg: Config) -> dict:
    with db.connect(cfg.database_url) as conn:
        return pipeline.retenir(conn, cfg)


# Les nouveaux essais sur erreur HTTP sont faits par le collecteur (backoff) ;
# Prefect ne relance le passage que s'il plante en entier (base injoignable…).
@flow(name="collecte", retries=1, retry_delay_seconds=300)
def collecte() -> dict:
    journal.configure()  # chaque passage tourne dans son propre processus
    cfg = config.load()
    bilans = tache_collecte(cfg)
    nettoyage = tache_nettoyage(cfg)
    controles = tache_controles(cfg)
    rapport = tache_rapport(cfg, nettoyage)
    run_themes = tache_themes(cfg)
    tache_retention(cfg)
    return {
        "sources": len(bilans),
        "ecrits": sum(b.ecrits for b in bilans),
        "echecs": [b.source for b in bilans if b.statut == "echec"],
        "gardes": nettoyage.gardes,
        "rejetes": nettoyage.rejetes,
        "controles_en_echec": [r.controle for r in controles if not r.ok],
        "rapport": rapport,
        "run_themes": run_themes,
    }


def planifier(intervalle_min: int) -> None:
    collecte.serve(
        name="planifiee",
        interval=timedelta(minutes=intervalle_min),
        description="Collecte, nettoyage, contrôles de qualité, rapport et thèmes du jour",
        # Un seul passage à la fois. Au réveil d'une machine en veille, les passages
        # manqués s'enchaînent, mais le délai minimal par source (GAZETTE_DELAI_MIN) les
        # rend vides : les éditeurs ne voient qu'une requête. Pas de limite globale côté
        # serveur : un passage fantôme (conteneur tué au démarrage) la garderait pour
        # toujours et bloquerait tous les suivants.
        limit=1,
    )
