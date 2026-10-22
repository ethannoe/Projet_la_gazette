"""Tests de bout en bout : vrai serveur HTTP local, vraie base PostgreSQL (bin/test)."""

import csv
import json
from datetime import timedelta
from functools import partial

import pytest
from conftest import FIXTURES

from gazette import db
from gazette.cli import print_report
from gazette.collecteur import collect_all
from gazette.fetch import fetch_feed

LEMONDE = (FIXTURES / "lemonde_une.xml").read_bytes()


@pytest.fixture
def attentes():
    return []


@pytest.fixture
def fetch(attentes):
    return partial(fetch_feed, sleep=attentes.append)  # backoff enregistré, pas attendu


def sources_csv(tmp_path, server, *routes: str):
    path = tmp_path / "sources.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "nom", "type", "region", "acces"])
        for route in routes:
            writer.writerow([route, route.capitalize(), "PQN", "National", server.url(f"/{route}")])
    return path


def etat(conn, source: str) -> dict:
    cur = conn.execute("SELECT * FROM sources WHERE id = %s", (source,))
    return dict(zip([c.name for c in cur.description], cur.fetchone(), strict=True))


def by_source(bilans):
    return {b.source: b for b in bilans}


def test_deux_passages_zero_doublon(conn, feed_server, tmp_path, fetch):
    feed_server.route("/monde", body=LEMONDE)  # pas d'ETag : le flux est retéléchargé
    sources = sources_csv(tmp_path, feed_server, "monde")
    articles = tmp_path / "articles_bruts"

    [premier] = collect_all(conn, sources, articles, fetch=fetch)
    [second] = collect_all(conn, sources, articles, fetch=fetch)

    assert (premier.recus, premier.ecrits, premier.ignores) == (3, 3, 0)
    assert (second.recus, second.ecrits, second.ignores) == (3, 0, 3)
    assert feed_server.hits("/monde") == 2
    fichiers = sorted((articles / "monde").glob("*.json"))
    assert len(fichiers) == 3
    item = json.loads(fichiers[0].read_text(encoding="utf-8"))
    assert list(item) == [
        "id", "source", "lien", "titre", "resume", "publie_le", "recupere_le", "rubrique", "payload"
    ]  # fmt: skip
    assert conn.execute("SELECT count(*) FROM collectes").fetchone()[0] == 2


def test_doublon_dans_un_meme_flux(conn, feed_server, tmp_path, fetch):
    feed_server.route("/limites", body=(FIXTURES / "cas_limites.xml").read_bytes())
    sources = sources_csv(tmp_path, feed_server, "limites")

    [bilan] = collect_all(conn, sources, tmp_path, fetch=fetch)

    assert bilan.recus == 8  # 9 items, dont un sans lien
    assert bilan.ecrits == 7  # le lien avec utm_* est le même article
    assert bilan.ignores == 1


def test_etag_evite_de_retelecharger(conn, feed_server, tmp_path, fetch):
    feed_server.route("/monde", body=LEMONDE, etag='"v1"')
    sources = sources_csv(tmp_path, feed_server, "monde")

    collect_all(conn, sources, tmp_path, fetch=fetch)
    assert etat(conn, "monde")["etag"] == '"v1"'
    [second] = collect_all(conn, sources, tmp_path, fetch=fetch)

    assert second.statut == "inchange"
    assert second.http == 304
    assert second.recus == 0
    assert feed_server.requests[-1][1]["If-None-Match"] == '"v1"'
    assert etat(conn, "monde")["derniere_reussite"] is not None


def test_source_en_panne_mise_en_sommeil(conn, feed_server, tmp_path, fetch, attentes):
    feed_server.route("/panne", statuses=[503])
    feed_server.route("/monde", body=LEMONDE)
    sources = sources_csv(tmp_path, feed_server, "monde", "panne")

    for passage in (1, 2, 3):
        bilans = by_source(collect_all(conn, sources, tmp_path, fetch=fetch))
        assert bilans["panne"].statut == "echec"
        assert bilans["panne"].echecs_consecutifs == passage
        assert bilans["monde"].statut == "ok"  # une source en panne n'arrête pas les autres

    assert bilans["panne"].mise_en_sommeil
    assert attentes == [2.0, 4.0] * 3  # backoff à chaque passage
    assert feed_server.hits("/panne") == 9  # 3 passages × 3 tentatives
    panne = etat(conn, "panne")
    assert panne["actif"] is False
    assert panne["echecs_consecutifs"] == 3
    assert panne["mise_en_sommeil_le"] is not None
    assert panne["derniere_erreur"] == "HTTP 503"

    # En sommeil, la source n'est plus interrogée
    bilans = collect_all(conn, sources, tmp_path, fetch=fetch)
    assert [b.source for b in bilans] == ["monde"]
    assert feed_server.hits("/panne") == 9

    # Réveillée (et réparée), elle repart avec un compteur à zéro
    feed_server.route("/panne", body=LEMONDE)
    assert db.wake_up(conn, "panne")
    bilans = by_source(collect_all(conn, sources, tmp_path, fetch=fetch))
    assert bilans["panne"].statut == "ok"
    assert etat(conn, "panne")["echecs_consecutifs"] == 0


def test_404_et_flux_casse_comptent_sans_backoff(conn, feed_server, tmp_path, fetch, attentes):
    feed_server.route("/casse", body=b"<html><body>Pas un flux</body></html>")
    sources = sources_csv(tmp_path, feed_server, "absente", "casse")

    bilans = by_source(collect_all(conn, sources, tmp_path, fetch=fetch))

    assert bilans["absente"].erreur == "HTTP 404"
    assert bilans["casse"].http == 200
    assert bilans["casse"].erreur.startswith("flux illisible")
    assert attentes == []
    assert etat(conn, "casse")["echecs_consecutifs"] == 1


def test_une_reussite_remet_le_compteur_a_zero(conn, feed_server, tmp_path, fetch):
    feed_server.route("/monde", body=LEMONDE, statuses=[503, 503, 503, 200])
    sources = sources_csv(tmp_path, feed_server, "monde")

    [premier] = collect_all(conn, sources, tmp_path, fetch=fetch)
    assert premier.echecs_consecutifs == 1
    [second] = collect_all(conn, sources, tmp_path, fetch=fetch)
    assert second.statut == "ok"
    assert etat(conn, "monde")["echecs_consecutifs"] == 0


def test_sources_csv_fait_foi(conn, feed_server, tmp_path, fetch):
    feed_server.route("/monde", body=LEMONDE)
    feed_server.route("/autre", body=LEMONDE)
    collect_all(conn, sources_csv(tmp_path, feed_server, "monde", "autre"), tmp_path, fetch=fetch)

    # retirée du CSV : plus collectée, mais son historique reste
    bilans = collect_all(conn, sources_csv(tmp_path, feed_server, "monde"), tmp_path, fetch=fetch)
    assert [b.source for b in bilans] == ["monde"]
    assert etat(conn, "autre")["derniere_reussite"] is not None


def test_nouvelle_adresse_reveille_la_source(conn, feed_server, tmp_path, fetch):
    feed_server.route("/monde", statuses=[404])
    sources = sources_csv(tmp_path, feed_server, "monde")
    for _ in range(3):
        collect_all(conn, sources, tmp_path, fetch=fetch)
    assert etat(conn, "monde")["actif"] is False

    feed_server.route("/nouvelle", body=LEMONDE)
    sources.write_text(sources.read_text().replace("/monde", "/nouvelle"))
    [bilan] = collect_all(conn, sources, tmp_path, fetch=fetch)
    assert bilan.statut == "ok"


def test_rapport_etat(conn, feed_server, tmp_path, fetch, capsys):
    feed_server.route("/monde", body=LEMONDE)
    sources = sources_csv(tmp_path, feed_server, "monde", "panne")
    for _ in range(3):
        collect_all(conn, sources, tmp_path, fetch=fetch)

    rows = {r["id"]: r for r in db.report(conn)}
    assert (rows["monde"]["passages"], rows["monde"]["ecrits"]) == (3, 3)
    assert (rows["panne"]["echecs"], rows["panne"]["sommeils"]) == (3, 1)

    print_report(list(rows.values()), str(tmp_path))
    sortie = capsys.readouterr().out
    assert "SOMMEIL" in sortie
    assert "- panne : HTTP 404" in sortie


def test_delai_minimal_entre_deux_requetes(conn, feed_server, tmp_path, fetch):
    feed_server.route("/monde", body=LEMONDE)
    sources = sources_csv(tmp_path, feed_server, "monde")

    collect_all(conn, sources, tmp_path, fetch=fetch, delai=timedelta(minutes=10))
    trop_tot = collect_all(conn, sources, tmp_path, fetch=fetch, delai=timedelta(minutes=10))

    assert trop_tot == []
    assert feed_server.hits("/monde") == 1
