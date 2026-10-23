"""Contrôles de qualité, métriques et alerte, avec une vraie base et un faux webhook."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gazette import db, retention
from gazette.controles import controler
from gazette.regles import charger
from gazette.sources import Source

SEUILS = charger(Path(__file__).parents[1] / "regles.toml").seuils
MAINTENANT = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def base_saine(conn):
    db.migrate(conn)
    db.sync_sources(
        conn, [Source("lemonde", "Le Monde", "PQN", "National", "https://lemonde.test/rss")]
    )
    db.record_success(conn, "lemonde", MAINTENANT - timedelta(minutes=20), None, None)
    ajouter_propre(conn, "a1", "Un article tout à fait normal", MAINTENANT - timedelta(hours=2))


def ajouter_propre(conn, item_id, titre, publie_le):
    conn.execute(
        "INSERT INTO articles_propres (item_id, source_id, lien, titre, extrait, publie_le,"
        " recupere_le, titre_cle, passage)"
        " VALUES (%s, 'lemonde', %s, %s, 'Extrait.', %s, %s, %s, %s)",
        (
            item_id,
            f"https://lemonde.test/{item_id}",
            titre,
            publie_le,
            MAINTENANT,
            titre.lower(),
            MAINTENANT,
        ),
    )


def etat(resultats) -> dict[str, bool]:
    return {r.controle: r.ok for r in resultats}


def test_base_saine_tous_les_controles_passent(conn, feed_server):
    base_saine(conn)
    resultats = controler(conn, SEUILS, ["lemonde"], feed_server.url("/webhook"), MAINTENANT)
    assert all(etat(resultats).values()), [r for r in resultats if not r.ok]
    assert feed_server.posts == []  # rien à signaler
    assert conn.execute("SELECT count(*) FROM controles").fetchone()[0] == len(resultats)


def test_un_fait_faux_declenche_une_alerte_une_seule_fois(conn, feed_server):
    base_saine(conn)
    controler(conn, SEUILS, ["lemonde"], feed_server.url("/webhook"), MAINTENANT)
    ajouter_propre(
        conn, "futur", "Un article publié dans trois heures", MAINTENANT + timedelta(hours=3)
    )

    resultats = controler(conn, SEUILS, ["lemonde"], feed_server.url("/webhook"), MAINTENANT)
    assert etat(resultats)["C01_aucune_date_future"] is False
    [(_, corps)] = feed_server.posts
    message = json.loads(corps)["content"]
    assert "C01_aucune_date_future" in message

    controler(conn, SEUILS, ["lemonde"], feed_server.url("/webhook"), MAINTENANT)
    assert len(feed_server.posts) == 1  # toujours faux : pas de nouvelle alerte

    conn.execute("DELETE FROM articles_propres WHERE item_id = 'futur'")
    controler(conn, SEUILS, ["lemonde"], feed_server.url("/webhook"), MAINTENANT)
    assert len(feed_server.posts) == 2
    assert "rétabli" in json.loads(feed_server.posts[-1][1])["content"]


def test_taux_de_rejet_et_fraicheur(conn, feed_server):
    base_saine(conn)
    for i in range(12):  # 12 rejets pour 1 article gardé : 92 % de rejet
        conn.execute(
            "INSERT INTO rejets (item_id, source_id, regle, titre, lien, passage)"
            " VALUES (%s, 'lemonde', 'R02_horoscope', 'x', %s, %s)",
            (f"r{i}", f"https://lemonde.test/r{i}", MAINTENANT),
        )
    db.record_success(conn, "lemonde", MAINTENANT - timedelta(hours=5), None, None)

    resultats = {r.controle: r for r in controler(conn, SEUILS, ["lemonde"], None, MAINTENANT)}

    assert resultats["C03_taux_rejet_par_source"].ok is False
    assert "lemonde 92%" in resultats["C03_taux_rejet_par_source"].detail
    assert resultats["C04_fraicheur_collecte"].ok is False
    assert resultats["C04_fraicheur_collecte"].valeur == 5.0


def test_retention(conn, tmp_path):
    base_saine(conn)
    brut = tmp_path / "articles_bruts" / "lemonde"
    brut.mkdir(parents=True)
    vieux, recent = brut / "vieux.json", brut / "recent.json"
    for f in (vieux, recent):
        f.write_text("{}")
    il_y_a_100_jours = (MAINTENANT - timedelta(days=100)).timestamp()
    os.utime(vieux, (il_y_a_100_jours, il_y_a_100_jours))
    conn.execute(
        "INSERT INTO rejets (item_id, source_id, regle, titre, lien, passage)"
        " VALUES ('ancien', 'lemonde', 'R02_horoscope', 'x', 'u', %s)",
        (MAINTENANT - timedelta(days=100),),
    )

    supprimes = retention.purger(
        conn, tmp_path / "articles_bruts", tmp_path / "rapports", MAINTENANT
    )

    assert supprimes["brut"] == 1 and not vieux.exists() and recent.exists()
    assert supprimes["rejets"] == 1
    assert conn.execute("SELECT count(*) FROM articles_propres").fetchone()[0] == 1
