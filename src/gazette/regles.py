"""Règles d'exclusion : chaque article normalisé les passe dans l'ordre, la première qui
correspond donne la raison du rejet (son identifiant va dans la table `rejets`).

Les motifs et les seuils sont dans regles.toml ; documentation dans docs/qualite.md.
"""

import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from gazette.normalisation import encodage_casse, jaccard

# Les règles qui ne sont pas des motifs : leur logique est ici, leurs seuils dans regles.toml
REGLES_CODE = {
    "R10_titre_vide": "Titre vide ou trop court pour être un titre d'article",
    "R11_date_future": "Date de publication dans le futur",
    "R12_sans_date": "Pas de date de publication (ou date illisible)",
    "R13_encodage_casse": "Encodage cassé qu'on n'a pas su réparer (« Ã© », « � »)",
    "R14_doublon_exact": "Même titre qu'un article déjà gardé (dépêche reprise à l'identique)",
    "R15_doublon_proche": "Titre presque identique à un article déjà gardé (à deux mots près)",
}


class Verdict(NamedTuple):
    regle: str
    detail: str


@dataclass(frozen=True)
class Seuils:
    titre_min_caracteres: int
    date_future_tolerance_min: int
    doublon_jaccard: float
    doublon_mots_min: int
    doublon_fenetre_heures: int
    extrait_max: int
    rejet_max_par_source: float
    rejet_min_items: int
    fraicheur_max_heures: int


@dataclass(frozen=True)
class RegleMotifs:
    id: str
    description: str
    motifs: dict[str, list[re.Pattern]]  # champ (titre, lien, rubrique) → motifs

    def correspond(self, article: dict) -> str | None:
        """Le champ et le motif qui ont déclenché la règle, ou None."""
        for champ, motifs in self.motifs.items():
            valeur = article.get(champ) or ""
            for motif in motifs:
                if motif.search(valeur):
                    return f"{champ} ~ {motif.pattern}"
        return None


@dataclass(frozen=True)
class Regles:
    seuils: Seuils
    motifs: list[RegleMotifs]

    @property
    def descriptions(self) -> dict[str, str]:
        tout = {r.id: r.description for r in self.motifs} | REGLES_CODE
        return dict(sorted(tout.items()))


def charger(path: str | Path) -> Regles:
    config = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    seuils = Seuils(**config.pop("seuils"))
    motifs = [
        RegleMotifs(
            id=regle_id,
            description=section["description"],
            motifs={
                champ: [re.compile(m, re.I) for m in section[champ]]
                for champ in ("titre", "lien", "rubrique")
                if champ in section
            },
        )
        for regle_id, section in config.items()  # l'ordre du fichier est l'ordre d'application
    ]
    return Regles(seuils, motifs)


@dataclass
class Dedoublonneur:
    """Les articles gardés récemment, pour repérer reprises (R14) et quasi-doublons (R15)."""

    seuils: Seuils
    par_cle: dict[str, tuple[str, str]] = field(default_factory=dict)  # titre_cle → (item, source)
    recents: list[tuple[frozenset[str], str, str]] = field(default_factory=list)

    def ajouter(self, article: dict) -> None:
        reference = (article["item_id"], article["source_id"])
        self.par_cle.setdefault(article["titre_cle"], reference)
        if len(article["mots"]) >= self.seuils.doublon_mots_min:
            self.recents.append((article["mots"], *reference))

    def verifier(self, article: dict) -> Verdict | None:
        if garde := self.par_cle.get(article["titre_cle"]):
            return Verdict("R14_doublon_exact", f"même titre que {garde[0]} ({garde[1]})")
        if len(article["mots"]) < self.seuils.doublon_mots_min:
            return None
        meilleur = max(
            ((jaccard(article["mots"], m), item, src) for m, item, src in self.recents),
            default=None,
        )
        if meilleur and meilleur[0] >= self.seuils.doublon_jaccard:
            score, item, source = meilleur
            return Verdict("R15_doublon_proche", f"jaccard {score:.2f} avec {item} ({source})")
        return None


def evaluer(
    article: dict, regles: Regles, dedoublonneur: Dedoublonneur, maintenant: datetime
) -> Verdict | None:
    """La raison de rejeter l'article, ou None s'il est gardé."""
    s = regles.seuils
    if len(article["titre"]) < s.titre_min_caracteres:
        return Verdict("R10_titre_vide", f"{len(article['titre'])} caractères")
    if encodage_casse(article["titre"]) or encodage_casse(article["extrait"]):
        return Verdict("R13_encodage_casse", article["titre"][:60])
    if article["publie_le"] is None:
        return Verdict("R12_sans_date", "publie_le absent")
    if article["publie_le"] > maintenant + timedelta(minutes=s.date_future_tolerance_min):
        return Verdict("R11_date_future", f"publié le {article['publie_le'].isoformat()}")
    for regle in regles.motifs:
        if detail := regle.correspond(article):
            return Verdict(regle.id, detail)
    return dedoublonneur.verifier(article)
