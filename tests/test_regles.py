"""Les règles d'exclusion, testées sur des exemples (dont nos vrais pollueurs) et des
contre-exemples (de vrais articles qui ressemblent aux pièges)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import FIXTURES

from gazette.nettoyage import normaliser_item
from gazette.regles import REGLES_CODE, Dedoublonneur, charger, evaluer

REGLES = charger(Path(__file__).parents[1] / "regles.toml")
MAINTENANT = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
QUALITE = json.loads((FIXTURES / "qualite.json").read_text(encoding="utf-8"))


def article(titre="Un titre d'article tout à fait normal", **champs) -> dict:
    item = {
        "id": champs.pop("id", "id-test"),
        "source": champs.pop("source", "test"),
        "lien": champs.pop("lien", "https://exemple.test/societe/un-article"),
        "titre": titre,
        "resume": champs.pop("resume", "Un extrait."),
        "publie_le": champs.pop("publie_le", "2026-10-23T08:00:00+00:00"),
        "recupere_le": "2026-10-23T09:00:00+00:00",
        "rubrique": champs.pop("rubrique", None),
    }
    return normaliser_item(item, REGLES.seuils.extrait_max)


def verdict(a: dict, dedoublonneur: Dedoublonneur | None = None):
    v = evaluer(a, REGLES, dedoublonneur or Dedoublonneur(REGLES.seuils), MAINTENANT)
    return v.regle if v else None


def test_chaque_regle_a_un_identifiant_et_une_description():
    ids = list(REGLES.descriptions)
    assert ids == sorted(ids)
    assert [r.id[:3] for r in REGLES.motifs] == [f"R0{i}" for i in range(1, 10)]
    assert set(REGLES_CODE) <= set(ids)
    assert all(REGLES.descriptions.values())


@pytest.mark.parametrize("cas", QUALITE["pollueurs"], ids=lambda c: c["regle_attendue"])
def test_nos_dix_pollueurs_sont_ecartes(cas):
    a = normaliser_item(cas["item"], REGLES.seuils.extrait_max)
    assert verdict(a) == cas["regle_attendue"]


@pytest.mark.parametrize("item", QUALITE["vrais_articles"], ids=lambda i: i["titre"][:30])
def test_de_vrais_articles_sont_gardes(item):
    assert verdict(normaliser_item(item, REGLES.seuils.extrait_max)) is None


@pytest.mark.parametrize(
    ("regle", "titre", "lien"),
    [
        ("R01_publi", "CONTENU SPONSORISÉ. Les meilleures offres de la rentrée", None),
        ("R01_publi", "Les bons plans du week-end", None),
        ("R01_publi", "Un article sur une offre", "https://exemple.test/bons-plans/offre"),
        ("R02_horoscope", "Horoscope du jour : ce que les astres vous réservent", None),
        ("R03_programme_tv", "Programme TV : que regarder ce soir ?", None),
        ("R04_jeux", "Résultat du Loto de ce samedi : le tirage", None),
        ("R04_jeux", "Concours : 10 places à gagner pour le festival", None),
        ("R05_meteo_service", "La météo à Toulouse du vendredi 23 octobre 2026", None),
        ("R06_page_service", "Pharmacies de garde ce week-end dans le Rhône", None),
        ("R07_media_seul", "EN IMAGES. Les plus belles photos de la tempête", None),
        ("R08_autopromo", "Abonnez-vous à notre offre numérique", None),
        ("R09_recapitulatif", "L’actu de ce vendredi : tempête, grève, budget", None),
    ],
)
def test_regles_a_motifs(regle, titre, lien):
    a = article(titre, lien=lien) if lien else article(titre)
    assert verdict(a) == regle


@pytest.mark.parametrize(
    "titre",
    [
        "Ce que Macron a à gagner avec ce remaniement",  # « à gagner » sans lot
        "VIDÉO. Tempête Austen : les images des vagues à Brest",  # vrai article
        "REPLAY. Guerre en Ukraine : le Kremlin prêt à reprendre des négociations",  # direct fini
        "Angèle annule sa participation aux NRJ Music Awards",  # « Awards » ailleurs
        "Libération des otages : les négociations reprennent",  # « Libération »
        "Tempête Austen : la météo se dégrade sur la Bretagne",  # actualité météo
        "Les jeunes jouent un rôle clé dans la mobilisation",  # « jeu »
    ],
)
def test_pas_de_faux_positifs(titre):
    assert verdict(article(titre)) is None


def test_r10_titre_vide():
    assert verdict(article("")) == "R10_titre_vide"
    assert verdict(article("Météo")) == "R10_titre_vide"


def test_r11_date_future():
    futur = (MAINTENANT + timedelta(hours=3)).isoformat()
    assert verdict(article(publie_le=futur)) == "R11_date_future"
    tolere = (MAINTENANT + timedelta(minutes=30)).isoformat()
    assert verdict(article(publie_le=tolere)) is None


def test_r12_sans_date():
    assert verdict(article(publie_le=None)) == "R12_sans_date"


def test_r13_encodage_casse():
    # « Ã© » est réparé à la normalisation ; un « � » ne peut pas l'être
    assert verdict(article("Un titre avec un caractÃ¨re cassÃ© mais rÃ©parable")) is None
    assert verdict(article("Un titre avec un caract�re perdu pour de bon")) == "R13_encodage_casse"


def test_r14_doublon_exact_entre_sources():
    d = Dedoublonneur(REGLES.seuils)
    premier = article(
        "Le virus Shamonda détecté pour la première fois chez un humain", source="lemonde"
    )
    d.ajouter(premier)
    reprise = article(
        "Le virus Shamonda détecté pour la première fois chez un humain !", source="liberation"
    )
    assert verdict(reprise, d) == "R14_doublon_exact"


def test_r15_doublon_proche():
    d = Dedoublonneur(REGLES.seuils)
    d.ajouter(
        article(
            "Le prix Sakharov 2026 attribué à la Cour pénale internationale,"
            " un pied de nez à Donald Trump"
        )
    )
    proche = article(
        "Le Prix Sakharov 2026 est accordé à la Cour pénale internationale,"
        " un pied de nez à Donald Trump"
    )
    assert verdict(proche, d) == "R15_doublon_proche"
    autre = article("Manifestation du 24 octobre à Toulouse : accord préfecture-syndicats")
    d.ajouter(
        article("Manifestation du 24 octobre à Toulouse : un parcours plus éloigné du centre")
    )
    assert verdict(autre, d) is None  # jaccard 0,73 sur nos données : deux articles différents
