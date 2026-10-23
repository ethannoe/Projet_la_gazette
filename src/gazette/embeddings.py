"""Embeddings : « titre. extrait » → un vecteur, avec un cache en base (table embeddings).

Un vecteur n'est calculé qu'une fois par article et par modèle (nom@révision) : les runs
suivants le relisent. Si le modèle change de révision, la clé du cache change aussi.
"""

import hashlib
from pathlib import Path
from typing import Protocol

import numpy as np
import psycopg


class Encodeur(Protocol):
    modele: str  # ex. sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    version: str  # révision exacte du modèle

    def encoder(self, textes: list[str]) -> np.ndarray: ...


class EncodeurFastembed:
    """Un modèle de phrases en ONNX, sur CPU, téléchargé une fois dans `cache_dir`."""

    def __init__(self, modele: str, cache_dir: str | Path):
        from fastembed import TextEmbedding  # chargé seulement quand on vectorise

        self.modele = modele
        self._modele = TextEmbedding(modele, cache_dir=str(cache_dir))
        # fastembed range le modèle comme Hugging Face : …/snapshots/<commit>
        dossier = getattr(self._modele.model, "_model_dir", None)
        self.version = Path(dossier).name if dossier else "inconnue"

    def encoder(self, textes: list[str]) -> np.ndarray:
        return np.asarray(list(self._modele.embed(textes)), dtype=np.float32)


def texte(article: dict) -> str:
    return f"{article['titre']}. {article['extrait']}".strip()


def cle_cache(encodeur: Encodeur) -> str:
    return f"{encodeur.modele}@{encodeur.version}"


def vectoriser(
    conn: psycopg.Connection, articles: list[dict], encodeur: Encodeur
) -> tuple[np.ndarray, int]:
    """Les vecteurs des articles (dans leur ordre) et le nombre qu'il a fallu calculer."""
    if not articles:
        return np.zeros((0, 0), dtype=np.float32), 0
    cle = cle_cache(encodeur)
    textes = {a["item_id"]: texte(a) for a in articles}
    empreintes = {i: hashlib.sha256(t.encode()).hexdigest()[:16] for i, t in textes.items()}

    vecteurs = {
        item_id: np.asarray(vecteur, dtype=np.float32)
        for item_id, empreinte, vecteur in conn.execute(
            "SELECT item_id, texte_hash, vecteur FROM embeddings"
            " WHERE modele = %s AND item_id = ANY(%s)",
            (cle, list(textes)),
        )
        if empreinte == empreintes[item_id]
    }
    manquants = [i for i in textes if i not in vecteurs]
    if manquants:
        calcules = encodeur.encoder([textes[i] for i in manquants])
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO embeddings (item_id, modele, texte_hash, vecteur)"
                " VALUES (%s, %s, %s, %s) ON CONFLICT (item_id, modele) DO UPDATE"
                " SET texte_hash = EXCLUDED.texte_hash, vecteur = EXCLUDED.vecteur,"
                " calcule_le = now()",
                [
                    (i, cle, empreintes[i], v.tolist())
                    for i, v in zip(manquants, calcules, strict=True)
                ],
            )
        vecteurs.update(zip(manquants, calcules, strict=True))
    return np.vstack([vecteurs[a["item_id"]] for a in articles]), len(manquants)
