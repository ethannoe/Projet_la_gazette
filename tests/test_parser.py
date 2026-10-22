from pathlib import Path

import pytest

from gazette.parser import MAX_SUMMARY, FeedError, clean_text, parse_feed

FIXTURES = Path(__file__).parent / "fixtures"
FIELDS = {"source", "title", "summary", "url", "published_at"}


def parse(name: str, source: str = "Test") -> list[dict]:
    return parse_feed((FIXTURES / name).read_bytes(), source)


def by_url(items: list[dict]) -> dict[str, dict]:
    return {item["url"]: item for item in items}


# Flux du Monde enregistré le 22/10/2026 (tests/fixtures/lemonde_une.xml)


def test_lemonde_tous_les_items_sont_lus():
    items = parse("lemonde_une.xml", "Le Monde")
    assert len(items) == 3
    for item in items:
        assert set(item) == FIELDS
        assert item["source"] == "Le Monde"
        assert item["url"].startswith("https://www.lemonde.fr/")
        assert item["title"] and item["summary"]


def test_lemonde_premier_item():
    first = parse("lemonde_une.xml", "Le Monde")[0]
    assert first["title"].startswith("Interpellés devant leurs lycées début octobre")
    assert first["summary"].startswith("Leïla, Inès et Nino ont 17, 16 et 15 ans.")
    assert first["url"].endswith("_6798586_3224.html")
    # pubDate : Thu, 22 Oct 2026 09:45:09 +0200
    assert first["published_at"] == "2026-10-22T07:45:09+00:00"


# Cas limites (tests/fixtures/cas_limites.xml)


def test_date_convertie_en_utc():
    item = by_url(parse("cas_limites.xml"))["https://exemple.test/fuseau"]
    assert item["published_at"] == "2026-10-22T03:30:00+00:00"


def test_article_sans_date_ou_sans_lien_rejete():
    items = parse("cas_limites.xml")
    assert "https://exemple.test/sans-date" not in by_url(items)
    assert all(item["url"] for item in items)
    assert "Article sans lien" not in [item["title"] for item in items]


def test_html_retire_du_titre_et_de_l_extrait():
    item = by_url(parse("cas_limites.xml"))["https://exemple.test/html"]
    assert item["title"] == "Extrait en HTML & entités"
    assert item["summary"] == "Un extrait avec un lien et des espaces."


def test_texte_integral_jamais_conserve():
    items = by_url(parse("cas_limites.xml"))
    assert items["https://exemple.test/integral"]["summary"] == "Le vrai extrait."
    assert items["https://exemple.test/integral-seul"]["summary"] == ""
    assert all("TEXTE INTÉGRAL" not in str(item) for item in items.values())


def test_doublon_par_url_ignore():
    items = parse("cas_limites.xml")
    urls = [item["url"] for item in items]
    assert len(urls) == len(set(urls))
    assert by_url(items)["https://exemple.test/html"]["title"] != "Doublon"


def test_extrait_tronque():
    item = by_url(parse("cas_limites.xml"))["https://exemple.test/long"]
    assert len(item["summary"]) <= MAX_SUMMARY + 1
    assert item["summary"].endswith("…")


def test_flux_illisible():
    with pytest.raises(FeedError):
        parse_feed(b"<html><body>Ceci n'est pas un flux</body>", "Test")


def test_clean_text_vide():
    assert clean_text(None) == ""
    assert clean_text("  <br/>  ") == ""
