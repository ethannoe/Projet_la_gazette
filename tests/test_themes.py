"""Regroupement, nommage, métriques et traçage des runs."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from gazette import db
from gazette.sources import Source
from gazette.themes import (
    _renumeroter,
    charger_config,
    empreinte_entree,
    executer,
    metriques,
    nommer,
    regrouper,
    run_du_jour_attendu,
)

RACINE = Path(__file__).parents[1]
CONFIG = charger_config(RACINE / "config" / "clustering.yaml")
FIN = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
MOTS_VIDES = ["le", "la", "les", "de", "des", "du", "en", "un", "une", "et", "à", "sur"]

SUJETS = {
    "tempete": [
        "Tempête Austen : vigilance orange",
        "Tempête Austen : rafales et coupures",
        "La tempête Austen frappe la Bretagne",
        "Tempête Austen : trains supprimés",
    ],
    "budget": [
        "Budget 2027 : les députés votent",
        "Budget de la Sécurité sociale rejeté",
        "Budget 2027 : la taxe rejetée",
    ],
    "tour": [
        "Tour de France 2027 : le parcours",
        "Tour de France 2027 : les étapes de montagne",
        "Le Tour de France 2027 passe par la Lozère",
    ],
}
ISOLES = [
    "Un fromager primé à Lyon",
    "Un musée rouvre à Toulouse",
    "Panne géante chez un opérateur",
]


def vecteurs_de_test() -> tuple[np.ndarray, list[str], list[str]]:
    """Trois paquets serrés, proches les uns des autres (l'actualité du jour partage une
    direction commune), et trois articles isolés, loin de tout : en 16 dimensions."""
    rng = np.random.default_rng(0)
    commun = np.zeros(16)
    commun[15] = 1
    vecteurs, textes, verite = [], [], []
    for k, (sujet, titres) in enumerate(SUJETS.items()):
        centre = commun.copy()
        centre[k] = 0.5
        for t in titres:
            vecteurs.append(centre + rng.normal(scale=0.01, size=16))
            textes.append(t)
            verite.append(sujet)
    for k, t in enumerate(ISOLES):
        isole = np.zeros(16)
        isole[4 + 3 * k] = 1
        isole[5 + 3 * k] = -0.3 * (k + 1)
        vecteurs.append(isole)
        textes.append(t)
        verite.append("bruit")
    return np.array(vecteurs), textes, verite


def test_regrouper_trouve_les_sujets_et_le_bruit():
    vecteurs, _, verite = vecteurs_de_test()
    etiquettes, probabilites = regrouper(vecteurs, CONFIG["regroupement"])
    assert len(set(etiquettes) - {-1}) == 3
    assert [e for e, v in zip(etiquettes, verite, strict=True) if v == "bruit"] == [-1, -1, -1]
    for sujet in SUJETS:
        assert len({e for e, v in zip(etiquettes, verite, strict=True) if v == sujet}) == 1
    assert etiquettes[0] == 0  # le plus gros thème (la tempête, 4 articles) est le numéro 0
    assert probabilites.shape == etiquettes.shape


def test_regrouper_est_deterministe():
    vecteurs, _, _ = vecteurs_de_test()
    a, _ = regrouper(vecteurs, CONFIG["regroupement"])
    b, _ = regrouper(vecteurs, CONFIG["regroupement"])
    assert a.tolist() == b.tolist()


def test_trop_peu_d_articles_tout_est_bruit():
    etiquettes, _ = regrouper(np.eye(2), CONFIG["regroupement"])
    assert etiquettes.tolist() == [-1, -1]


def test_renumeroter_par_taille():
    assert _renumeroter(np.array([5, 5, 2, 2, 2, -1])).tolist() == [1, 1, 0, 0, 0, -1]


def test_nommer_par_mots_discriminants():
    vecteurs, textes, _ = vecteurs_de_test()
    etiquettes, _ = regrouper(vecteurs, CONFIG["regroupement"])
    mots = nommer(textes, etiquettes, MOTS_VIDES, CONFIG["nommage"])
    tetes = [set(m[:3]) for m in mots.values()]  # les mots qui forment le nom
    assert any(t & {"austen", "tempête"} for t in tetes)
    assert any("budget" in t for t in tetes)
    assert any(t & {"tour", "france"} for t in tetes)
    assert all(len(m) <= CONFIG["nommage"]["mots_cles"] for m in mots.values())
    assert all("les" not in m and "de" not in m for m in mots.values())  # mots vides écartés


def test_metriques():
    vecteurs, _, _ = vecteurs_de_test()
    etiquettes, _ = regrouper(vecteurs, CONFIG["regroupement"])
    m = metriques(vecteurs, etiquettes)
    assert m["nb_themes"] == 3
    assert m["taille_mediane"] == 3
    assert m["part_bruit"] == pytest.approx(3 / 13, abs=1e-3)
    assert m["silhouette"] > 0.5


# --- runs complets, avec une vraie base ---------------------------------------------------


class EncodeurParSujet:
    """Encodeur factice : place chaque article près du centre de son sujet (mot-clé du titre)."""

    modele = "factice-par-sujet"
    version = "1"

    def encoder(self, textes):
        return np.array([self._vecteur(t) for t in textes], dtype=np.float32)

    def _vecteur(self, t):
        # comme vecteurs_de_test : une direction commune, un décalage par sujet, et les
        # articles isolés loin de tout ; un léger écart déterministe selon le titre
        v = np.zeros(16)
        for k, mot in enumerate(("austen", "budget", "tour de france")):
            if mot in t.lower():
                v[15] = 1
                v[k] = 0.5
                v[12 + len(t) % 3] = 0.01
                return v
        j = next(k for k, isole in enumerate(ISOLES) if t.startswith(isole))  # « titre. extrait »
        v[4 + 3 * j] = 1
        v[5 + 3 * j] = -0.3 * (j + 1)
        return v


def preparer(conn):
    db.migrate(conn)
    db.sync_sources(conn, [Source("test", "Test", "PQN", "National", "https://test/rss")])
    titres = [t for titres in SUJETS.values() for t in titres] + ISOLES
    for i, titre in enumerate(titres):
        conn.execute(
            "INSERT INTO articles_propres (item_id, source_id, lien, titre, extrait, publie_le,"
            " recupere_le, titre_cle, passage)"
            " VALUES (%s, 'test', %s, %s, 'Extrait.', %s, %s, '', %s)",
            (f"a{i:02}", f"https://test/{i}", titre, FIN - timedelta(hours=1 + i), FIN, FIN),
        )
    # hors de la fenêtre des 24 h : ne doit pas compter
    conn.execute(
        "INSERT INTO articles_propres (item_id, source_id, lien, titre, extrait, publie_le,"
        " recupere_le, titre_cle, passage) VALUES ('vieux', 'test', 'https://test/v',"
        " 'Tempête Austen hier', 'Extrait.', %s, %s, '', %s)",
        (FIN - timedelta(hours=30), FIN, FIN),
    )


def lancer(conn, tmp_path, **options):
    return executer(
        conn, CONFIG, EncodeurParSujet(), fin=FIN, runs_dir=tmp_path / "runs",
        code_version="test", racine=RACINE, **options,
    )  # fmt: skip


def test_un_run_est_trace_avec_ses_themes(conn, tmp_path):
    preparer(conn)
    run = lancer(conn, tmp_path)

    assert run.nb_articles == 13  # l'article de 30 h n'est pas dans la fenêtre
    assert run.metriques["nb_themes"] == 3
    statut, nb, entree, modele, version, params, metriques_db, artefacts = conn.execute(
        "SELECT statut, nb_articles, hash_entree, modele, modele_version, parametres, metriques,"
        " artefacts FROM runs WHERE run_id = %s",
        (run.run_id,),
    ).fetchone()
    assert (statut, nb, modele, version) == ("ok", 13, "factice-par-sujet", "1")
    assert params["regroupement"]["algorithme"] == "hdbscan"
    assert metriques_db["nb_themes"] == 3 and "silhouette" in metriques_db
    for chemin in artefacts.values():
        assert Path(chemin).exists()
    assert json.loads(Path(artefacts["themes"]).read_text())[0]["taille"] == 4

    themes = conn.execute(
        "SELECT numero, nom, taille FROM themes_du_jour ORDER BY numero"
    ).fetchall()
    assert [t[2] for t in themes] == [4, 3, 3]
    assert "Austen" in themes[0][1] or "Tempête" in themes[0][1]
    rattaches = conn.execute(
        "SELECT count(*) FROM articles_themes WHERE run_id = %s", (run.run_id,)
    ).fetchone()[0]
    assert rattaches == 10  # les 3 isolés ne sont rattachés à aucun thème
    assert entree == empreinte_entree(
        [{"item_id": i, "titre": t, "extrait": e} for i, t, e in conn.execute(
            "SELECT item_id, titre, extrait FROM articles_propres WHERE item_id <> 'vieux'")]
    )  # fmt: skip


def test_meme_entree_memes_themes(conn, tmp_path):
    preparer(conn)
    premier = lancer(conn, tmp_path)
    second = lancer(conn, tmp_path)

    empreintes = conn.execute("SELECT DISTINCT hash_entree, hash_parametres FROM runs").fetchall()
    assert len(empreintes) == 1  # même fenêtre, mêmes paramètres
    assert [t["nom"] for t in premier.themes] == [t["nom"] for t in second.themes]
    assert premier.metriques["embeddings_calcules"] == 13
    assert second.metriques["embeddings_calcules"] == 0  # le cache a servi
    # les thèmes du jour sont ceux du dernier run
    (run_id,) = conn.execute("SELECT DISTINCT run_id FROM themes_du_jour").fetchone()
    assert run_id == second.run_id


def test_un_run_en_echec_est_trace(conn, tmp_path):
    preparer(conn)

    class EncodeurEnPanne(EncodeurParSujet):
        def encoder(self, textes):
            raise RuntimeError("modèle introuvable")

    with pytest.raises(RuntimeError):
        executer(conn, CONFIG, EncodeurEnPanne(), fin=FIN, runs_dir=tmp_path, racine=RACINE)
    statut, erreur = conn.execute("SELECT statut, erreur FROM runs").fetchone()
    assert statut == "echec"
    assert "modèle introuvable" in erreur
    assert conn.execute("SELECT count(*) FROM themes_du_jour").fetchone()[0] == 0


def test_un_run_par_jour_dans_le_pipeline(conn, tmp_path):
    preparer(conn)
    paris_6h = datetime(2026, 10, 23, 4, 0, tzinfo=UTC)  # 6 h à Paris (heure d'été)
    paris_7h = datetime(2026, 10, 23, 5, 0, tzinfo=UTC)
    assert run_du_jour_attendu(conn, CONFIG, paris_6h) is False  # avant 6 h 30
    assert run_du_jour_attendu(conn, CONFIG, paris_7h) is True

    conn.execute(
        "INSERT INTO runs (run_id, debut, statut, declencheur, fenetre_debut, fenetre_fin,"
        " nb_articles, hash_entree, modele, modele_version, algorithme, parametres,"
        " hash_parametres, code_version) VALUES ('r', %s, 'ok', 'pipeline', %s, %s, 0, '', '',"
        " '', '', '{}', '', '')",
        (paris_7h, paris_7h, paris_7h),
    )
    assert run_du_jour_attendu(conn, CONFIG, paris_7h + timedelta(hours=3)) is False
    assert run_du_jour_attendu(conn, CONFIG, paris_7h + timedelta(days=1)) is True
