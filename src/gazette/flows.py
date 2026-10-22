"""Orchestration Prefect : la collecte comme flow, planifiée toutes les N minutes.

`planifier()` enregistre le déploiement auprès du serveur Prefect (PREFECT_API_URL)
puis exécute lui-même les passages prévus. L'historique et les journaux de chaque
passage sont visibles dans l'interface Prefect (http://localhost:4200).
"""

from datetime import timedelta

from prefect import flow

from gazette import config, db, journal
from gazette.collecteur import collect_all


# Les nouveaux essais sur erreur HTTP sont faits par le collecteur (backoff) ;
# Prefect ne relance le passage que s'il plante en entier (base injoignable…).
@flow(name="collecte", retries=1, retry_delay_seconds=300)
def collecte() -> dict:
    journal.configure()  # chaque passage tourne dans son propre processus
    cfg = config.load()
    with db.connect(cfg.database_url) as conn:
        bilans = collect_all(
            conn, cfg.sources_file, cfg.articles_dir, delai=timedelta(minutes=cfg.delai_min)
        )
    return {
        "sources": len(bilans),
        "ecrits": sum(b.ecrits for b in bilans),
        "echecs": [b.source for b in bilans if b.statut == "echec"],
        "mis_en_sommeil": [b.source for b in bilans if b.mise_en_sommeil],
    }


def planifier(intervalle_min: int) -> None:
    collecte.serve(
        name="planifiee",
        interval=timedelta(minutes=intervalle_min),
        description="Collecte de toutes les sources actives de sources.csv",
        # Un seul passage à la fois. Au réveil d'une machine en veille, les passages
        # manqués s'enchaînent, mais le délai minimal par source (GAZETTE_DELAI_MIN) les
        # rend vides : les éditeurs ne voient qu'une requête. Pas de limite globale côté
        # serveur : un passage fantôme (conteneur tué au démarrage) la garderait pour
        # toujours et bloquerait tous les suivants.
        limit=1,
    )
