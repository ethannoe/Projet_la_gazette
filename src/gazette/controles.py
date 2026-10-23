"""Contrôles de qualité : des faits vérifiés sur les vraies données après chaque passage.

Ils ne testent pas le code (c'est le rôle de la CI) mais l'état réel des tables. Ce sont
des requêtes SQL maison : une par fait, lisible, sans outil de plus à faire tourner.
Chaque résultat est enregistré dans la table `controles` (les métriques), et une alerte
part quand un fait devient faux, puis quand il redevient vrai.
"""

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

import psycopg

from gazette import alertes, db
from gazette.regles import Seuils

log = logging.getLogger("gazette.controles")

MOJIBAKE_SQL = "Ã[\u0080-¿]|â€|�"


@dataclass
class Resultat:
    controle: str
    ok: bool
    valeur: float
    seuil: float
    detail: str = ""


def verifier(
    conn: psycopg.Connection, seuils: Seuils, sources_actives: list[str], maintenant: datetime
) -> list[Resultat]:
    def compter(sql: str, *params) -> int:
        return conn.execute(sql, params).fetchone()[0]

    resultats = []

    futures = compter(
        "SELECT count(*) FROM articles_propres WHERE publie_le > %s",
        maintenant + timedelta(minutes=seuils.date_future_tolerance_min),
    )
    resultats.append(Resultat("C01_aucune_date_future", futures == 0, futures, 0))

    vides = compter(
        "SELECT count(*) FROM articles_propres WHERE length(titre) < %s",
        seuils.titre_min_caracteres,
    )
    resultats.append(Resultat("C02_aucun_titre_vide", vides == 0, vides, 0))

    taux = conn.execute(
        """
        SELECT source_id, sum(rejete)::float / count(*) AS taux, count(*) AS entres
        FROM (SELECT source_id, 0 AS rejete FROM articles_propres WHERE passage > %(depuis)s
              UNION ALL
              SELECT source_id, 1 FROM rejets WHERE passage > %(depuis)s) t
        GROUP BY source_id HAVING count(*) >= %(min)s
        """,
        {"depuis": maintenant - timedelta(hours=24), "min": seuils.rejet_min_items},
    ).fetchall()
    trop = [f"{s} {t:.0%} sur {n}" for s, t, n in taux if t > seuils.rejet_max_par_source]
    pire = max((t for _, t, _ in taux), default=0.0)
    resultats.append(
        Resultat(
            "C03_taux_rejet_par_source",
            not trop,
            round(pire, 3),
            seuils.rejet_max_par_source,
            ", ".join(trop),
        )
    )

    anciennes = conn.execute(
        "SELECT id, derniere_reussite FROM sources WHERE id = ANY(%s) AND actif"
        " AND (derniere_reussite IS NULL OR derniere_reussite < %s) ORDER BY id",
        (sources_actives, maintenant - timedelta(hours=seuils.fraicheur_max_heures)),
    ).fetchall()
    retard = max(
        ((maintenant - r).total_seconds() / 3600 if r else 999.0 for _, r in anciennes),
        default=0.0,
    )
    resultats.append(
        Resultat(
            "C04_fraicheur_collecte",
            not anciennes,
            round(retard, 1),
            seuils.fraicheur_max_heures,
            ", ".join(s for s, _ in anciennes),
        )
    )

    endormies = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM sources WHERE id = ANY(%s) AND NOT actif ORDER BY id",
            (sources_actives,),
        )
    ]
    resultats.append(
        Resultat(
            "C05_aucune_source_en_sommeil", not endormies, len(endormies), 0, ", ".join(endormies)
        )
    )

    trop_longs = compter(
        "SELECT count(*) FROM articles_propres WHERE length(extrait) > %s", seuils.extrait_max + 1
    )
    resultats.append(Resultat("C06_extraits_bornes", trop_longs == 0, trop_longs, 0))

    sales = compter(
        "SELECT count(*) FROM articles_propres WHERE titre ~ '<[a-zA-Z/][^>]*>'"
        " OR extrait ~ '<[a-zA-Z/][^>]*>' OR titre ~ %s OR extrait ~ %s",
        MOJIBAKE_SQL,
        MOJIBAKE_SQL,
    )
    resultats.append(Resultat("C07_ni_html_ni_encodage_casse", sales == 0, sales, 0))

    du_jour = compter(
        "SELECT count(*) FROM articles_propres WHERE publie_le > %s",
        maintenant - timedelta(hours=24),
    )
    resultats.append(Resultat("C08_articles_des_dernieres_24h", du_jour > 0, du_jour, 1))
    return resultats


def controler(
    conn: psycopg.Connection,
    seuils: Seuils,
    sources_actives: list[str],
    webhook: str | None,
    maintenant: datetime | None = None,
) -> list[Resultat]:
    """Vérifie, enregistre les métriques, et alerte sur chaque changement d'état."""
    maintenant = maintenant or datetime.now(UTC)
    db.migrate(conn)
    precedents = dict(
        conn.execute(
            "SELECT DISTINCT ON (controle) controle, ok FROM controles"
            " ORDER BY controle, passage DESC, id DESC"
        ).fetchall()
    )
    resultats = verifier(conn, seuils, sources_actives, maintenant)
    with conn.transaction():
        for r in resultats:
            conn.execute(
                "INSERT INTO controles (passage, controle, ok, valeur, seuil, detail)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (maintenant, r.controle, r.ok, r.valeur, r.seuil, r.detail or None),
            )

    for r in resultats:
        niveau = logging.INFO if r.ok else logging.ERROR
        log.log(
            niveau,
            "%s : %s (valeur %s, seuil %s)%s",
            r.controle,
            "ok" if r.ok else "ÉCHEC",
            r.valeur,
            r.seuil,
            f" : {r.detail}" if r.detail else "",
            extra={"champs": {"evenement": "controle", **asdict(r)}},
        )

    casses = [r for r in resultats if not r.ok and precedents.get(r.controle, True)]
    repares = [r for r in resultats if r.ok and precedents.get(r.controle) is False]
    if casses or repares:
        alertes.envoyer(message_alerte(casses, repares, maintenant), webhook)
    return resultats


def message_alerte(casses: list[Resultat], repares: list[Resultat], maintenant: datetime) -> str:
    lignes = [f"La gazette, contrôles de qualité du {maintenant:%d/%m/%Y %H:%M} UTC"]
    for r in casses:
        detail = f" ({r.detail})" if r.detail else ""
        lignes.append(f"🔴 {r.controle} : valeur {r.valeur}, seuil {r.seuil}{detail}")
    for r in repares:
        lignes.append(f"🟢 {r.controle} : rétabli")
    lignes.append(f"Rapport : rapports/qualite-{maintenant:%Y-%m-%d}.md")
    return "\n".join(lignes)
