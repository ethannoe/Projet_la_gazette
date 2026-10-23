"""Les thèmes du jour : vectoriser, regrouper, nommer, stocker, et tracer chaque run.

Un run = une fenêtre de données (les articles propres des 24 dernières heures), un modèle
d'embeddings et sa révision, des paramètres (config/clustering.yaml), des métriques et des
artefacts. Tout est enregistré dans la table `runs`, avant (statut en_cours) et après
(ok ou echec) : on sait toujours quel run a produit les thèmes qui sont en base.
Même fenêtre, mêmes paramètres, même modèle → mêmes thèmes (HDBSCAN est déterministe).
"""

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import psycopg
import yaml
from psycopg.types.json import Jsonb
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

from gazette import db
from gazette.embeddings import Encodeur, texte, vectoriser

log = logging.getLogger("gazette.themes")

MOTIF_MOT = r"(?u)\b[^\W\d_][^\W\d_'’-]{2,}\b"  # au moins 3 lettres, sans chiffres


@dataclass(frozen=True)
class ConfigThemes:
    brut: str  # le fichier tel quel : c'est lui qu'on trace
    valeurs: dict

    @property
    def empreinte(self) -> str:
        return hashlib.sha256(self.brut.encode()).hexdigest()[:16]

    def __getitem__(self, cle: str):
        return self.valeurs[cle]


def charger_config(path: str | Path) -> ConfigThemes:
    brut = Path(path).read_text(encoding="utf-8")
    return ConfigThemes(brut, yaml.safe_load(brut))


@dataclass
class Run:
    run_id: str
    debut: datetime
    nb_articles: int
    metriques: dict = field(default_factory=dict)
    themes: list[dict] = field(default_factory=list)  # numero, nom, mots_cles, taille, titres
    artefacts: dict = field(default_factory=dict)


# --- les étapes, chacune testable seule -------------------------------------------------


def articles_de_la_fenetre(conn: psycopg.Connection, fin: datetime, heures: int) -> list[dict]:
    rows = conn.execute(
        "SELECT item_id, source_id, titre, extrait, publie_le FROM articles_propres"
        " WHERE publie_le > %s AND publie_le <= %s ORDER BY item_id",
        (fin - timedelta(hours=heures), fin),
    )
    colonnes = ("item_id", "source_id", "titre", "extrait", "publie_le")
    return [dict(zip(colonnes, row, strict=True)) for row in rows]


def empreinte_entree(articles: list[dict]) -> str:
    """Deux runs sur la même entrée ont la même empreinte (ordre des ids, texte vectorisé)."""
    h = hashlib.sha256()
    for a in sorted(articles, key=lambda a: a["item_id"]):
        h.update(f"{a['item_id']}\t{texte(a)}\n".encode())
    return h.hexdigest()[:16]


def regrouper(vecteurs: np.ndarray, params: dict) -> tuple[np.ndarray, np.ndarray]:
    """Les étiquettes (-1 = bruit) et la force du rattachement de chaque article."""
    n = len(vecteurs)
    if n < max(params["min_cluster_size"], params["min_samples"] + 1, 2):
        return np.full(n, -1), np.zeros(n)
    normes = np.linalg.norm(vecteurs, axis=1, keepdims=True)
    unitaires = vecteurs / np.where(normes == 0, 1, normes)  # euclidien ≈ cosinus
    modele = HDBSCAN(
        min_cluster_size=params["min_cluster_size"],
        min_samples=params["min_samples"],
        cluster_selection_method=params["cluster_selection_method"],
        copy=True,
    ).fit(unitaires)
    return _renumeroter(modele.labels_), modele.probabilities_


def _renumeroter(etiquettes: np.ndarray) -> np.ndarray:
    """Thème 0 = le plus gros, puis par taille décroissante ; le bruit reste -1."""
    tailles = {e: int(np.sum(etiquettes == e)) for e in set(etiquettes.tolist()) - {-1}}
    ordre = sorted(tailles, key=lambda e: (-tailles[e], int(np.argmax(etiquettes == e))))
    correspondance = {ancien: nouveau for nouveau, ancien in enumerate(ordre)} | {-1: -1}
    return np.array([correspondance[e] for e in etiquettes.tolist()], dtype=int)


def nommer(
    textes: list[str], etiquettes: np.ndarray, mots_vides: list[str], params: dict
) -> dict[int, list[str]]:
    """Les mots les plus discriminants de chaque thème (TF-IDF calculé par thème).

    Chaque thème est un document ; les articles isolés (bruit) forment un document de
    fond, pour que les mots communs à toute l'actualité du jour ne nomment aucun thème.
    """
    numeros = sorted(set(etiquettes.tolist()) - {-1})
    if not numeros:
        return {}
    corpus = [
        " ".join(t for t, e in zip(textes, etiquettes, strict=True) if e == n) for n in numeros
    ]
    corpus.append(" ".join(t for t, e in zip(textes, etiquettes, strict=True) if e == -1))
    tfidf = TfidfVectorizer(
        stop_words=mots_vides,
        token_pattern=MOTIF_MOT,
        ngram_range=(1, params["ngram_max"]),
        sublinear_tf=True,
    )
    poids = tfidf.fit_transform(corpus).toarray()
    vocabulaire = tfidf.get_feature_names_out()
    return {
        n: [
            str(vocabulaire[j]) for j in np.argsort(-poids[k], kind="stable")[: params["mots_cles"]]
        ]
        for k, n in enumerate(numeros)
    }


def metriques(vecteurs: np.ndarray, etiquettes: np.ndarray) -> dict:
    tailles = [int(np.sum(etiquettes == n)) for n in sorted(set(etiquettes.tolist()) - {-1})]
    dans_un_theme = etiquettes >= 0
    silhouette = None
    if len(tailles) >= 2 and dans_un_theme.sum() > len(tailles):
        silhouette = round(
            float(
                silhouette_score(
                    vecteurs[dans_un_theme], etiquettes[dans_un_theme], metric="cosine"
                )
            ),
            4,
        )
    return {
        "nb_articles": int(len(etiquettes)),
        "nb_themes": len(tailles),
        "taille_mediane": float(np.median(tailles)) if tailles else 0.0,
        "taille_max": max(tailles, default=0),
        "part_bruit": round(float(np.mean(~dans_un_theme)), 4) if len(etiquettes) else 0.0,
        "silhouette": silhouette,
    }


def run_du_jour_attendu(conn: psycopg.Connection, cfg: ConfigThemes, maintenant: datetime) -> bool:
    """Le pipeline lance un run par jour, au premier passage après l'heure prévue."""
    fuseau = ZoneInfo(cfg["planification"]["fuseau"])
    heure, minute = map(int, cfg["planification"]["heure"].split(":"))
    local = maintenant.astimezone(fuseau)
    seuil = local.replace(hour=heure, minute=minute, second=0, microsecond=0)
    if local < seuil:
        return False
    deja = conn.execute(
        "SELECT 1 FROM runs WHERE statut = 'ok' AND declencheur = 'pipeline' AND debut >= %s",
        (seuil.astimezone(UTC),),
    ).fetchone()
    return deja is None


# --- un run complet, tracé -------------------------------------------------------------


def executer(
    conn: psycopg.Connection,
    cfg: ConfigThemes,
    encodeur: Encodeur,
    *,
    fin: datetime | None = None,
    declencheur: str = "manuel",
    runs_dir: str | Path = "runs",
    code_version: str = "inconnue",
    racine: str | Path = ".",
) -> Run:
    db.migrate(conn)
    debut = datetime.now(UTC)
    fin = fin or debut.replace(microsecond=0)
    t0 = time.monotonic()
    articles = articles_de_la_fenetre(conn, fin, cfg["fenetre_heures"])
    empreinte = empreinte_entree(articles)
    run = Run(f"{debut:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}", debut, len(articles))
    params = cfg["regroupement"]

    conn.execute(
        "INSERT INTO runs (run_id, debut, statut, declencheur, fenetre_debut, fenetre_fin,"
        " nb_articles, hash_entree, modele, modele_version, algorithme, parametres,"
        " hash_parametres, code_version)"
        " VALUES (%s, %s, 'en_cours', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            run.run_id, debut, declencheur, fin - timedelta(hours=cfg["fenetre_heures"]), fin,
            len(articles), empreinte, encodeur.modele, encodeur.version, params["algorithme"],
            Jsonb(cfg.valeurs), cfg.empreinte, code_version,
        ),
    )  # fmt: skip
    try:
        vecteurs, calcules = vectoriser(conn, articles, encodeur)
        etiquettes, probabilites = regrouper(vecteurs, params)
        mots_vides = _mots_vides(Path(racine) / cfg["nommage"]["mots_vides"])
        textes = [texte(a) for a in articles]
        mots_cles = nommer(textes, etiquettes, mots_vides, cfg["nommage"])
        run.metriques = metriques(vecteurs, etiquettes) | {
            "embeddings_calcules": calcules,
            "duree_s": round(time.monotonic() - t0, 2),
        }
        run.themes = [
            {
                "numero": n,
                "nom": " · ".join(
                    m.capitalize() for m in mots_cles[n][: cfg["nommage"]["mots_nom"]]
                ),
                "mots_cles": mots_cles[n],
                "taille": int(np.sum(etiquettes == n)),
                "titres": [a["titre"] for a, e in zip(articles, etiquettes, strict=True) if e == n],
            }
            for n in sorted(mots_cles)
        ]
        affectations = {
            a["item_id"]: {"theme": int(e), "probabilite": round(float(p), 4)}
            for a, e, p in zip(articles, etiquettes, probabilites, strict=True)
        }
        run.artefacts = _ecrire_artefacts(Path(runs_dir) / run.run_id, cfg, run, affectations)
        _enregistrer(conn, run, articles, etiquettes, probabilites)
    except Exception as exc:
        conn.execute(
            "UPDATE runs SET statut = 'echec', erreur = %s, duree_s = %s WHERE run_id = %s",
            (f"{type(exc).__name__}: {exc}", round(time.monotonic() - t0, 2), run.run_id),
        )
        raise
    log.info(
        "run %s : %d articles, %d thèmes, %.0f %% de bruit",
        run.run_id,
        run.nb_articles,
        run.metriques["nb_themes"],
        100 * run.metriques["part_bruit"],
        extra={"champs": {"evenement": "run_themes", "run_id": run.run_id, **run.metriques}},
    )
    return run


def _mots_vides(path: Path) -> list[str]:
    lignes = path.read_text(encoding="utf-8").splitlines()
    return sorted({mot for ligne in lignes if not ligne.startswith("#") for mot in ligne.split()})


def _ecrire_artefacts(dossier: Path, cfg: ConfigThemes, run: Run, affectations: dict) -> dict:
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers = {
        "parametres.yaml": cfg.brut,
        "metriques.json": json.dumps(run.metriques, ensure_ascii=False, indent=2),
        "themes.json": json.dumps(run.themes, ensure_ascii=False, indent=2),
        "affectations.json": json.dumps(affectations, ensure_ascii=False, indent=2),
    }
    for nom, contenu in fichiers.items():
        (dossier / nom).write_text(contenu + "\n", encoding="utf-8")
    return {nom.split(".")[0]: str(dossier / nom) for nom in fichiers}


def _enregistrer(conn, run: Run, articles, etiquettes, probabilites) -> None:
    with conn.transaction():
        ids_themes = {}
        for t in run.themes:
            (ids_themes[t["numero"]],) = conn.execute(
                "INSERT INTO themes (run_id, numero, nom, mots_cles, taille)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING theme_id",
                (run.run_id, t["numero"], t["nom"], t["mots_cles"], t["taille"]),
            ).fetchone()
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO articles_themes (run_id, item_id, theme_id, probabilite)"
                " VALUES (%s, %s, %s, %s)",
                [
                    (run.run_id, a["item_id"], ids_themes[int(e)], round(float(p), 4))
                    for a, e, p in zip(articles, etiquettes, probabilites, strict=True)
                    if e >= 0
                ],
            )
        conn.execute(
            "UPDATE runs SET statut = 'ok', duree_s = %s, metriques = %s, artefacts = %s"
            " WHERE run_id = %s",
            (run.metriques["duree_s"], Jsonb(run.metriques), Jsonb(run.artefacts), run.run_id),
        )
