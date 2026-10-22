import pytest
from conftest import FIXTURES

from gazette.parser import (
    MAX_RESUME,
    FeedError,
    _rubrique,
    clean_text,
    normalize_link,
    parse_feed,
)

CHAMPS = {"lien", "titre", "resume", "publie_le", "rubrique", "payload"}


def parse(name: str) -> list[dict]:
    return parse_feed((FIXTURES / name).read_bytes())


def by_link(items: list[dict]) -> dict[str, dict]:
    return {item["lien"]: item for item in items}


# Flux du Monde enregistré le 22/10/2026 (tests/fixtures/lemonde_une.xml)


def test_lemonde_tous_les_items_sont_lus():
    items = parse("lemonde_une.xml")
    assert len(items) == 3
    for item in items:
        assert set(item) == CHAMPS
        assert item["lien"].startswith("https://www.lemonde.fr/")
        assert item["titre"] and item["resume"]


def test_lemonde_premier_item():
    first = parse("lemonde_une.xml")[0]
    assert first["titre"].startswith("Interpellés devant leurs lycées début octobre")
    assert first["resume"].startswith("Leïla, Inès et Nino ont 17, 16 et 15 ans.")
    assert first["lien"].endswith("_6798586_3224.html")
    # pubDate : Thu, 22 Oct 2026 09:45:09 +0200
    assert first["publie_le"] == "2026-10-22T07:45:09+00:00"
    assert first["rubrique"] == "societe"  # pas de <category> : premier segment de l'URL
    assert first["payload"]["published"] == "Thu, 22 Oct 2026 09:45:09 +0200"


# Cas limites (tests/fixtures/cas_limites.xml)


def test_date_convertie_en_utc():
    item = by_link(parse("cas_limites.xml"))["https://exemple.test/monde/fuseau"]
    assert item["publie_le"] == "2026-10-22T03:30:00+00:00"


def test_article_sans_date_garde_avec_date_vide():
    item = by_link(parse("cas_limites.xml"))["https://exemple.test/sans-date"]
    assert item["publie_le"] is None


def test_article_sans_lien_rejete():
    titres = [item["titre"] for item in parse("cas_limites.xml")]
    assert "Article sans lien" not in titres


def test_titre_vide_garde_en_brut():
    assert by_link(parse("cas_limites.xml"))["https://exemple.test/titre-vide"]["titre"] == ""


def test_html_retire_du_titre_et_de_l_extrait():
    item = parse("cas_limites.xml")[2]
    assert item["titre"] == "Extrait en HTML & entités"
    assert item["resume"] == "Un extrait avec un lien et des espaces."


def test_rubrique_du_flux_puis_de_l_url():
    items = parse("cas_limites.xml")
    assert items[2]["rubrique"] == "Société"  # <category>
    assert by_link(items)["https://exemple.test/monde/fuseau"]["rubrique"] == "monde"
    assert by_link(items)["https://exemple.test/sans-date"]["rubrique"] is None  # slug seul


@pytest.mark.parametrize(
    ("lien", "attendu"),
    [
        ("https://www.latribune.fr/article/afrique/11500292245967/ludovic-peze", "afrique"),
        ("https://www.leprogres.fr/sport/2026/10/21/stan-wawrinka", "sport"),
        ("https://www.ladepeche.fr/2026/10/22/il-achete-une-maison", None),
        ("https://www.la-croix.com/mairie-incendiee-a-limoges-20261022", None),
        ("https://www.sudouest.fr/gironde/bordeaux/la-meteo-31182838.php", "gironde"),
    ],
)
def test_rubrique_depuis_l_url(lien, attendu):
    assert _rubrique({}, lien) == attendu


def test_texte_integral_jamais_conserve():
    items = by_link(parse("cas_limites.xml"))
    assert items["https://exemple.test/integral"]["resume"] == "Le vrai extrait."
    assert items["https://exemple.test/integral-seul"]["resume"] == ""
    assert all("TEXTE INTÉGRAL" not in str(item) for item in items.values())


def test_payload_sans_auteur():
    payload = parse("cas_limites.xml")[2]["payload"]
    assert set(payload) <= {"id", "title", "link", "published", "updated", "summary", "tags"}
    assert "Jeanne" not in str(payload)


def test_liens_normalises_pour_le_dedoublonnage():
    items = parse("cas_limites.xml")
    doublons = [item for item in items if item["lien"] == "https://exemple.test/html"]
    assert len(doublons) == 2  # le parseur garde tout, le stockage dédoublonne


@pytest.mark.parametrize(
    ("lien", "attendu"),
    [
        ("https://EXEMPLE.test/a?utm_source=rss#haut", "https://exemple.test/a"),
        ("https://exemple.test/a?id=3&xtor=RSS-1", "https://exemple.test/a?id=3"),
        ("  https://exemple.test/a  ", "https://exemple.test/a"),
        ("/relatif", ""),
        (None, ""),
    ],
)
def test_normalize_link(lien, attendu):
    assert normalize_link(lien) == attendu


def test_extrait_tronque():
    item = by_link(parse("cas_limites.xml"))["https://exemple.test/long"]
    assert len(item["resume"]) <= MAX_RESUME + 1
    assert item["resume"].endswith("…")


# Atom et encodages


def test_atom():
    first, second = parse("atom.xml")
    assert first["titre"] == "Un titre Atom"
    assert first["lien"] == "https://exemple.test/culture/atom-1"
    assert first["resume"] == "Le résumé Atom."
    assert first["publie_le"] == "2026-10-22T06:00:00+00:00"  # <updated>
    assert first["rubrique"] == "Culture"
    assert first["payload"]["id"] == "urn:exemple:article:1"
    assert second["publie_le"] == "2026-10-21T23:00:00+00:00"  # <published> avant <updated>
    assert second["resume"] == ""
    assert "TEXTE INTÉGRAL" not in str([first, second])


def test_iso_8859_1_et_formats_de_date():
    ete, chataigne, illisible = parse("latin1.xml")
    assert ete["titre"] == "Été brûlant à Besançon"
    assert ete["publie_le"] == "2026-10-22T06:00:00+00:00"
    assert chataigne["titre"] == "Fête de la châtaigne"
    assert chataigne["publie_le"] == "2026-10-22T06:00:00+00:00"
    assert illisible["publie_le"] is None
    assert illisible["payload"]["published"] == "jeudi 22 octobre 2026, 8 h"


@pytest.mark.parametrize(
    "contenu",
    [
        b"<html><body>Ceci n'est pas un flux</body>",  # XML mal formé
        b"<html><body><p>Acceptez les cookies</p></body></html>",  # HTML bien formé
    ],
)
def test_flux_illisible(contenu):
    with pytest.raises(FeedError):
        parse_feed(contenu)


def test_flux_valide_mais_vide():
    assert parse_feed(b'<rss version="2.0"><channel><title>Vide</title></channel></rss>') == []


def test_clean_text_vide():
    assert clean_text(None) == ""
    assert clean_text("  <br/>  ") == ""
