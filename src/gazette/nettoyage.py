"""Du brut au propre : chaque nouvel item de articles_bruts/ est normalisé, passe les
règles d'exclusion, puis va dans `articles_propres` ou dans `rejets` avec sa règle.

Un item n'est traité qu'une fois : ceux déjà présents dans l'une des deux tables sont
sautés, donc relancer le nettoyage ne change rien (idempotence).
"""

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg

from gazette import db
from gazette.normalisation import borner_extrait, cle_titre, date_utc, mots, normaliser_texte
from gazette.regles import Dedoublonneur, Regles, evaluer

log = logging.getLogger("gazette.nettoyage")


@dataclass
class BilanNettoyage:
    passage: datetime
    entres: int = 0
    gardes: int = 0
    par_regle: Counter = field(default_factory=Counter)
    par_source: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))

    @property
    def rejetes(self) -> int:
        return self.entres - self.gardes


def normaliser_item(item: dict, extrait_max: int) -> dict:
    """Un item brut (fichier JSON) → un article normalisé, prêt pour les règles."""
    titre = normaliser_texte(item.get("titre"))
    return {
        "item_id": item["id"],
        "source_id": item["source"],
        "lien": item["lien"],
        "titre": titre,
        "extrait": borner_extrait(normaliser_texte(item.get("resume")), extrait_max),
        "publie_le": date_utc(item.get("publie_le")),
        "recupere_le": date_utc(item.get("recupere_le")),
        "rubrique": normaliser_texte(item.get("rubrique")) or None,
        "titre_cle": cle_titre(titre),
        "mots": mots(titre),
    }


def items_nouveaux(conn: psycopg.Connection, articles_dir: str | Path) -> list[dict]:
    """Les items bruts qui ne sont encore ni dans articles_propres ni dans rejets."""
    deja = {
        row[0]
        for row in conn.execute(
            "SELECT item_id FROM articles_propres UNION ALL SELECT item_id FROM rejets"
        )
    }
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(Path(articles_dir).glob("*/*.json"))
        if path.stem not in deja
    ]


def nettoyer(
    conn: psycopg.Connection,
    articles_dir: str | Path,
    regles: Regles,
    maintenant: datetime | None = None,
) -> BilanNettoyage:
    maintenant = maintenant or datetime.now(UTC)
    db.migrate(conn)
    seuils = regles.seuils
    bilan = BilanNettoyage(passage=maintenant)

    dedoublonneur = Dedoublonneur(seuils)
    fenetre = maintenant - timedelta(hours=seuils.doublon_fenetre_heures)
    for item_id, source_id, titre in conn.execute(
        "SELECT item_id, source_id, titre FROM articles_propres WHERE publie_le > %s"
        " ORDER BY publie_le",
        (fenetre,),
    ):
        dedoublonneur.ajouter(
            {
                "item_id": item_id,
                "source_id": source_id,
                "titre_cle": cle_titre(titre),
                "mots": mots(titre),
            }
        )

    sources = {row[0] for row in conn.execute("SELECT id FROM sources")}
    articles = [
        normaliser_item(item, seuils.extrait_max)
        for item in items_nouveaux(conn, articles_dir)
        if item["source"] in sources
    ]
    # Le plus ancien d'abord : quand une dépêche est reprise, c'est la première qu'on garde
    articles.sort(key=lambda a: (a["publie_le"] or a["recupere_le"], a["item_id"]))

    with conn.transaction():
        for article in articles:
            verdict = evaluer(article, regles, dedoublonneur, maintenant)
            source = bilan.par_source[article["source_id"]]
            bilan.entres += 1
            source["entres"] += 1
            if verdict:
                _inserer_rejet(conn, article, verdict, maintenant)
                bilan.par_regle[verdict.regle] += 1
                source["rejetes"] += 1
            else:
                _inserer_propre(conn, article, maintenant)
                dedoublonneur.ajouter(article)
                bilan.gardes += 1
                source["gardes"] += 1

    log.info(
        "nettoyage : %d items entrés, %d gardés, %d rejetés",
        bilan.entres,
        bilan.gardes,
        bilan.rejetes,
        extra={
            "champs": {
                "evenement": "nettoyage",
                "entres": bilan.entres,
                "gardes": bilan.gardes,
                "rejetes": bilan.rejetes,
                "par_regle": dict(bilan.par_regle),
            }
        },
    )
    return bilan


def _inserer_propre(conn: psycopg.Connection, a: dict, passage: datetime) -> None:
    conn.execute(
        "INSERT INTO articles_propres (item_id, source_id, lien, titre, extrait, publie_le,"
        " recupere_le, rubrique, titre_cle, passage)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            a["item_id"],
            a["source_id"],
            a["lien"],
            a["titre"],
            a["extrait"],
            a["publie_le"],
            a["recupere_le"],
            a["rubrique"],
            a["titre_cle"],
            passage,
        ),
    )


def _inserer_rejet(conn: psycopg.Connection, a: dict, verdict, passage: datetime) -> None:
    conn.execute(
        "INSERT INTO rejets (item_id, source_id, regle, detail, titre, lien, passage)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (
            a["item_id"],
            a["source_id"],
            verdict.regle,
            verdict.detail,
            a["titre"],
            a["lien"],
            passage,
        ),
    )
