"""Un test par fonction de normalisation."""

from datetime import UTC, datetime, timedelta, timezone

from gazette.normalisation import (
    borner_extrait,
    cle_titre,
    date_utc,
    decoder_entites,
    encodage_casse,
    jaccard,
    mots,
    normaliser_espaces,
    normaliser_texte,
    reparer_encodage,
    retirer_html,
)


def test_retirer_html():
    assert retirer_html("<p>Un <b>titre</b></p>").split() == ["Un", "titre"]
    assert "alert" not in retirer_html("avant<script>alert(1)</script>après")
    assert retirer_html("sans balise") == "sans balise"


def test_decoder_entites():
    assert decoder_entites("Tom &amp; Jerry") == "Tom & Jerry"
    assert decoder_entites("&eacute;t&eacute;") == "été"
    assert decoder_entites("&amp;eacute;") == "é"  # doublement encodée


def test_reparer_encodage():
    # « à » = octets C3 A0, relus « Ã » + espace insécable
    assert reparer_encodage("Ã‰tÃ© brÃ»lant Ã\u00a0 BesanÃ§on") == "Été brûlant à Besançon"
    assert reparer_encodage("lâ€™actu") == "l’actu"
    assert reparer_encodage("L’Ã©tÃ© « chaud »") == "L’été « chaud »"  # mélangé
    assert (
        reparer_encodage("Déjà correct : été, ça, œuvre, «»") == "Déjà correct : été, ça, œuvre, «»"
    )


def test_encodage_casse():
    assert encodage_casse("Ã©tÃ©")
    assert encodage_casse("caract�re perdu")
    assert not encodage_casse("Été brûlant à Besançon")


def test_normaliser_espaces():
    assert normaliser_espaces("  Mot : suite\n\tfin  ") == "Mot : suite fin"
    assert normaliser_espaces("in​visible") == "invisible"


def test_normaliser_texte():
    brut = "<p>L&#8217;Ã©tÃ©&nbsp;&amp; <i>la</i>   rentrÃ©e</p>"
    assert normaliser_texte(brut) == "L’été & la rentrée"
    assert normaliser_texte(normaliser_texte(brut)) == "L’été & la rentrée"  # idempotente
    assert normaliser_texte(None) == ""


def test_borner_extrait():
    assert borner_extrait("court") == "court"
    long = "mot " * 100
    borne = borner_extrait(long, limite=50)
    assert len(borne) <= 51
    assert borne.endswith("mot…")


def test_date_utc():
    assert date_utc("2026-10-22T09:45:09+02:00") == datetime(2026, 10, 22, 7, 45, 9, tzinfo=UTC)
    assert date_utc("2026-10-22T07:45:09Z") == datetime(2026, 10, 22, 7, 45, 9, tzinfo=UTC)
    assert date_utc("2026-10-22T07:45:09") == datetime(2026, 10, 22, 7, 45, 9, tzinfo=UTC)
    paris = datetime(2026, 10, 22, 9, 0, tzinfo=timezone(timedelta(hours=2)))
    assert date_utc(paris) == datetime(2026, 10, 22, 7, 0, tzinfo=UTC)
    assert date_utc("jeudi 22 octobre") is None
    assert date_utc(None) is None


def test_cle_titre():
    assert cle_titre("Tempête Austen : « vigilance orange » !") == "tempete austen vigilance orange"
    assert cle_titre("TEMPÊTE AUSTEN — Vigilance Orange") == cle_titre(
        "Tempête Austen : vigilance orange"
    )


def test_mots():
    assert mots("Le prix Sakharov est attribué à la CPI") == {"prix", "sakharov", "attribue", "cpi"}


def test_jaccard():
    a = mots("Le prix Sakharov 2026 attribué à la Cour pénale internationale")
    b = mots("Le prix Sakharov 2026 est accordé à la Cour pénale internationale")
    assert 0.7 < jaccard(a, b) < 1
    assert jaccard(a, a) == 1
    assert jaccard(a, mots("Tempête Austen sur la Bretagne")) == 0
