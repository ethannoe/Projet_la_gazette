"""Le module d'embeddings : cache en base, et le vrai modèle sur dix vrais articles."""

import hashlib
import json
import os
from datetime import UTC, datetime

import numpy as np
import pytest
from conftest import FIXTURES

from gazette import db
from gazette.embeddings import texte, vectoriser
from gazette.sources import Source

DIX = json.loads((FIXTURES / "dix_articles.json").read_text(encoding="utf-8"))
MODELE = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class EncodeurFactice:
    """Déterministe et instantané : un vecteur tiré de l'empreinte du texte."""

    modele = "factice"
    version = "1"

    def __init__(self):
        self.appels = 0

    def encoder(self, textes: list[str]) -> np.ndarray:
        self.appels += len(textes)
        return np.array(
            [
                np.random.default_rng(int(hashlib.sha256(t.encode()).hexdigest()[:8], 16)).normal(
                    size=8
                )
                for t in textes
            ],
            dtype=np.float32,
        )


def inserer_propres(conn, articles):
    db.migrate(conn)
    db.sync_sources(conn, [Source("test", "Test", "PQN", "National", "https://test/rss")])
    maintenant = datetime(2026, 10, 23, 12, tzinfo=UTC)
    for a in articles:
        conn.execute(
            "INSERT INTO articles_propres (item_id, source_id, lien, titre, extrait, publie_le,"
            " recupere_le, titre_cle, passage) VALUES (%s, 'test', %s, %s, %s, %s, %s, '', %s)",
            (a["item_id"], f"https://test/{a['item_id']}", a["titre"], a["extrait"],
             maintenant, maintenant, maintenant),
        )  # fmt: skip


def test_dix_articles_vectorises_puis_relus_du_cache(conn):
    inserer_propres(conn, DIX)
    encodeur = EncodeurFactice()

    vecteurs, calcules = vectoriser(conn, DIX, encodeur)
    assert vecteurs.shape == (10, 8)
    assert calcules == 10

    relus, calcules = vectoriser(conn, list(reversed(DIX)), encodeur)
    assert calcules == 0  # tout vient du cache
    assert encodeur.appels == 10
    np.testing.assert_allclose(relus, vecteurs[::-1], rtol=1e-6)  # dans l'ordre demandé


def test_texte_modifie_recalcule(conn):
    inserer_propres(conn, DIX)
    encodeur = EncodeurFactice()
    vectoriser(conn, DIX, encodeur)

    modifie = [dict(DIX[0], extrait="Un autre extrait.")] + DIX[1:]
    _, calcules = vectoriser(conn, modifie, encodeur)
    assert calcules == 1


def test_autre_modele_autre_cache(conn):
    inserer_propres(conn, DIX)
    vectoriser(conn, DIX, EncodeurFactice())
    autre = EncodeurFactice()
    autre.version = "2"
    _, calcules = vectoriser(conn, DIX, autre)
    assert calcules == 10


def test_texte_vectorise():
    assert texte({"titre": "Titre", "extrait": "Extrait."}) == "Titre. Extrait."


@pytest.mark.skipif(
    not os.environ.get("GAZETTE_TEST_MODELE"),
    reason="télécharge le vrai modèle (220 Mo) : GAZETTE_TEST_MODELE=1 pour le lancer",
)
def test_vrai_modele_sur_dix_articles(tmp_path):
    from gazette.embeddings import EncodeurFastembed

    encodeur = EncodeurFastembed(MODELE, os.environ.get("GAZETTE_MODELES_DIR", tmp_path))
    vecteurs = encodeur.encoder([texte(a) for a in DIX])
    assert vecteurs.shape == (10, 384)
    assert len(encodeur.version) == 40  # un commit Hugging Face

    unitaires = vecteurs / np.linalg.norm(vecteurs, axis=1, keepdims=True)
    similarite = unitaires @ unitaires.T
    sujets = [a["sujet"] for a in DIX]
    meme = [
        similarite[i, j]
        for i in range(10)
        for j in range(i + 1, 10)
        if sujets[i] == sujets[j] != "autre"
    ]
    differents = [
        similarite[i, j] for i in range(10) for j in range(i + 1, 10) if sujets[i] != sujets[j]
    ]
    # deux articles du même sujet se ressemblent plus que deux articles de sujets différents
    assert np.mean(meme) > np.mean(differents) + 0.2
    assert min(meme) > max(differents) - 0.1
