"""Normalisation : une fonction pure par transformation, testée une par une.

Utilisée par le parseur (items bruts) et par le nettoyage (articles propres).
Toutes les fonctions sont idempotentes : les appliquer deux fois ne change rien.
"""

import html
import re
import unicodedata
from datetime import UTC, datetime

EXTRAIT_MAX = 300  # l'extrait court qu'on a le droit de republier

_SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_ESPACES_SPECIAUX = re.compile(r"[  -   　]")
_INVISIBLES = re.compile(r"[​-‍⁠﻿]")
_ESPACES = re.compile(r"\s+")
# Traces d'un texte UTF-8 relu en Latin-1 / Windows-1252 : « Ã© » pour « é », « â€™ » pour « ’ »
_MOJIBAKE = re.compile(r"Ã[\u0080-¿]|â€|Â[ -¿]|�")
# Les caractères qu'un octet ≥ 0x80 donne en Windows-1252 : candidats à une relecture
_SUITE_SUSPECTE = re.compile(
    "[\u0080-\u00ff\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u0192\u02c6\u02dc"
    "\u2013\u2014\u2018-\u201a\u201c-\u201e\u2020-\u2022\u2026\u2030\u2039\u203a"
    "\u20ac\u2122]{2,}"
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
MOTS_VIDES = frozenset(
    "le la les l un une des de du d et ou a au aux en dans sur sous par pour avec sans "
    "ce cet cette ces qui que quoi dont ou ne pas plus se sa son ses leur leurs est sont "
    "il elle ils elles on nous vous y".split()
)


def retirer_html(texte: str) -> str:
    """Retire les balises (et le contenu des <script> et <style>)."""
    return _TAG.sub(" ", _SCRIPT_STYLE.sub(" ", texte))


def decoder_entites(texte: str) -> str:
    """&amp; → &, &eacute; → é ; deux fois pour les entités doublement encodées."""
    return html.unescape(html.unescape(texte))


def reparer_encodage(texte: str) -> str:
    """« Ã©tÃ© » → « été ». Ne touche pas un texte sain, même mélangé (« L’Ã©tÃ© »).

    Chaque suite de caractères suspects est ré-encodée en Windows-1252 puis relue en
    UTF-8 ; les octets qui ne forment pas d'UTF-8 valide gardent leur caractère d'origine.
    """
    if not _MOJIBAKE.search(texte):
        return texte
    return _SUITE_SUSPECTE.sub(lambda m: _relire_en_utf8(m.group(0)), texte)


def _relire_en_utf8(suite: str) -> str:
    octets = b"".join(bytes([ord(c)]) if ord(c) < 0x100 else c.encode("cp1252") for c in suite)
    relu = octets.decode("utf-8", errors="surrogateescape")
    # un octet invalide revient sous forme de « surrogate » \udcXX : on remet son caractère
    return "".join(
        bytes([ord(c) - 0xDC00]).decode("cp1252", errors="replace")
        if 0xDC80 <= ord(c) <= 0xDCFF
        else c
        for c in relu
    )


def encodage_casse(texte: str) -> bool:
    """Reste-t-il des traces d'encodage cassé ?"""
    return bool(_MOJIBAKE.search(texte))


def normaliser_espaces(texte: str) -> str:
    """Espaces insécables et fines → espace, caractères invisibles retirés, espaces fusionnés."""
    texte = _INVISIBLES.sub("", _ESPACES_SPECIAUX.sub(" ", texte))
    return _ESPACES.sub(" ", texte).strip()


def normaliser_texte(texte: str | None) -> str:
    """La chaîne complète pour un titre ou un extrait."""
    texte = retirer_html(texte or "")
    texte = decoder_entites(texte)
    texte = reparer_encodage(texte)
    return normaliser_espaces(texte)


def borner_extrait(texte: str, limite: int = EXTRAIT_MAX) -> str:
    """Coupe au dernier mot entier avant la limite, et ajoute « … »."""
    if len(texte) <= limite:
        return texte
    return texte[:limite].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"


def date_utc(valeur: str | datetime | None) -> datetime | None:
    """Une date ISO 8601 (ou un datetime) en datetime UTC ; None si absente ou illisible.

    Une date sans fuseau est supposée en UTC.
    """
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, str):
        try:
            valeur = datetime.fromisoformat(valeur)
        except ValueError:
            return None
    if valeur.tzinfo is None:
        return valeur.replace(tzinfo=UTC)
    return valeur.astimezone(UTC)


def cle_titre(titre: str) -> str:
    """Le titre réduit à ses lettres et chiffres, sans accents ni majuscules.

    Deux titres identiques à la ponctuation, la casse et les accents près ont la même clé.
    """
    sans_accents = unicodedata.normalize("NFKD", titre.lower())
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return _NON_ALNUM.sub(" ", sans_accents).strip()


def mots(titre: str) -> frozenset[str]:
    """Les mots porteurs de sens du titre (sans mots vides), pour comparer deux titres."""
    return frozenset(m for m in cle_titre(titre).split() if m not in MOTS_VIDES)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Part de mots communs : |a ∩ b| / |a ∪ b|, entre 0 (rien en commun) et 1 (identiques)."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)
