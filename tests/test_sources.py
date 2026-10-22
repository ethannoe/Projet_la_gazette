from pathlib import Path

import pytest

from gazette.sources import get_source, load_sources

SOURCES_CSV = Path(__file__).parents[1] / "sources.csv"


def test_sources_csv_lisible():
    sources = load_sources(SOURCES_CSV)
    assert len(sources) == 9
    assert {s.kind for s in sources} == {"PQN", "PQR"}
    assert len({s.id for s in sources}) == len(sources)
    assert all(s.url.startswith("https://") for s in sources)


def test_get_source():
    sources = load_sources(SOURCES_CSV)
    assert get_source(sources, "lemonde").name == "Le Monde"
    with pytest.raises(KeyError, match="inconnue"):
        get_source(sources, "la-voix-du-nord")
