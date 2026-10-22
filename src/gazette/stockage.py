"""Stockage brut : un fichier JSON par item, articles_bruts/<source>/<id>.json.

L'id est dérivé de la clé naturelle (source, lien) : un item déjà écrit ne
l'est pas une deuxième fois, quel que soit le nombre de passages.
"""

import hashlib
import json
from pathlib import Path

# L'ordre des clés dans chaque fichier JSON (cf. docs/donnees.md)
CHAMPS = (
    "id",
    "source",
    "lien",
    "titre",
    "resume",
    "publie_le",
    "recupere_le",
    "rubrique",
    "payload",
)


def item_id(source: str, lien: str) -> str:
    return hashlib.sha256(f"{source}\n{lien}".encode()).hexdigest()[:16]


def build_item(parsed: dict, source: str, recupere_le: str) -> dict:
    item = {**parsed, "id": item_id(source, parsed["lien"]), "source": source}
    item["recupere_le"] = recupere_le
    return {champ: item.get(champ) for champ in CHAMPS}


def write_item(root: str | Path, item: dict) -> bool:
    """Écrit l'item s'il est nouveau. Renvoie False s'il existait déjà."""
    path = Path(root) / item["source"] / f"{item['id']}.json"
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)  # atomique : jamais de fichier à moitié écrit
    return True


def count_items(root: str | Path, source: str) -> int:
    return sum(1 for _ in (Path(root) / source).glob("*.json"))
