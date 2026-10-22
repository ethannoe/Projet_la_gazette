import socket

import pytest
from conftest import FIXTURES

from gazette.fetch import ErreurPermanente, ErreurTransitoire, fetch_feed

FEED = (FIXTURES / "lemonde_une.xml").read_bytes()


def test_503_puis_200_reessaie_avec_attente_croissante(feed_server):
    feed_server.route("/flux", body=FEED, statuses=[503, 503, 200])
    attentes = []
    reponse = fetch_feed(feed_server.url("/flux"), sleep=attentes.append)
    assert reponse.status == 200
    assert reponse.content == FEED
    assert reponse.tentatives == 3
    assert attentes == [2.0, 4.0]


def test_503_persistant_erreur_transitoire(feed_server):
    feed_server.route("/flux", statuses=[503])
    attentes = []
    with pytest.raises(ErreurTransitoire, match="HTTP 503") as exc:
        fetch_feed(feed_server.url("/flux"), sleep=attentes.append)
    assert exc.value.tentatives == 3
    assert feed_server.hits("/flux") == 3
    assert attentes == [2.0, 4.0]


def test_retry_after_respecte(feed_server):
    feed_server.route("/flux", body=FEED, statuses=[429, 200], headers={"Retry-After": "7"})
    attentes = []
    fetch_feed(feed_server.url("/flux"), sleep=attentes.append)
    assert attentes == [7.0]


def test_404_erreur_permanente_sans_nouvel_essai(feed_server):
    attentes = []
    with pytest.raises(ErreurPermanente, match="HTTP 404"):
        fetch_feed(feed_server.url("/absent"), sleep=attentes.append)
    assert feed_server.hits("/absent") == 1
    assert attentes == []


def test_connexion_refusee_erreur_transitoire():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # port libéré à la sortie : personne n'écoute
    attentes = []
    with pytest.raises(ErreurTransitoire, match="ConnectionError"):
        fetch_feed(f"http://127.0.0.1:{port}/flux", sleep=attentes.append)
    assert len(attentes) == 2


def test_en_tetes_polis_et_304(feed_server):
    feed_server.route("/flux", body=FEED, etag='"v1"')
    premiere = fetch_feed(feed_server.url("/flux"))
    assert premiere.etag == '"v1"'

    seconde = fetch_feed(feed_server.url("/flux"), premiere.etag, "Thu, 22 Oct 2026 09:00:00 GMT")
    assert seconde.status == 304
    assert seconde.content is None
    assert seconde.etag == '"v1"'
    _, headers = feed_server.requests[-1]
    assert headers["If-None-Match"] == '"v1"'
    assert headers["If-Modified-Since"] == "Thu, 22 Oct 2026 09:00:00 GMT"
    assert headers["User-Agent"].startswith("LaGazetteBot/")
