"""Du brut au propre, de bout en bout avec une vraie base (bin/test)."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from gazette import config, db, rapport
from gazette.nettoyage import nettoyer
from gazette.pipeline import tracer
from gazette.regles import charger
from gazette.sources import Source
from gazette.stockage import build_item, write_item

REGLES = charger(Path(__file__).parents[1] / "regles.toml")
MAINTENANT = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def preparer(conn, tmp_path, items: list[tuple[str, str, str]]) -> Path:
    """items : (source, titre, publie_le) → fichiers bruts + sources en base."""
    db.migrate(conn)
    sources = sorted({s for s, _, _ in items})
    db.sync_sources(
        conn,
        [Source(s, s.capitalize(), "PQN", "National", f"https://{s}.test/rss") for s in sources],
    )
    brut = tmp_path / "articles_bruts"
    for i, (source, titre, publie_le) in enumerate(items):
        parsed = {
            "lien": f"https://{source}.test/societe/article-{i}",
            "titre": titre,
            "resume": f"Extrait de l'article {i}.",
            "publie_le": publie_le,
            "rubrique": "societe",
            "payload": {},
        }
        write_item(brut, build_item(parsed, source, "2026-10-23T11:00:00+00:00"))
    return brut


ITEMS = [
    (
        "lemonde",
        "Le virus Shamonda détecté pour la première fois chez un humain",
        "2026-10-23T08:00:00+00:00",
    ),
    (
        "liberation",
        "Le virus Shamonda détecté pour la première fois chez un humain",
        "2026-10-23T08:30:00+00:00",
    ),
    (
        "lemonde",
        "Horoscope du jour : ce que les astres vous réservent",
        "2026-10-23T06:00:00+00:00",
    ),
    (
        "liberation",
        "Budget 2027 : les députés adoptent la partie recettes",
        "2026-10-23T09:00:00+00:00",
    ),
    ("liberation", "", "2026-10-23T09:00:00+00:00"),
    ("lemonde", "Un article qui arrive de demain, selon son éditeur", "2026-10-24T09:00:00+00:00"),
]


def test_nettoyage_remplit_propres_et_rejets(conn, tmp_path):
    brut = preparer(conn, tmp_path, ITEMS)

    bilan = nettoyer(conn, brut, REGLES, MAINTENANT)

    assert (bilan.entres, bilan.gardes, bilan.rejetes) == (6, 2, 4)
    assert dict(bilan.par_regle) == {
        "R02_horoscope": 1,
        "R10_titre_vide": 1,
        "R11_date_future": 1,
        "R14_doublon_exact": 1,
    }
    propres = conn.execute(
        "SELECT source_id, titre FROM articles_propres ORDER BY publie_le"
    ).fetchall()
    assert propres == [
        (
            "lemonde",
            "Le virus Shamonda détecté pour la première fois chez un humain",
        ),  # le plus ancien
        ("liberation", "Budget 2027 : les députés adoptent la partie recettes"),
    ]
    regle, detail = conn.execute(
        "SELECT regle, detail FROM rejets WHERE source_id = 'liberation' AND regle LIKE 'R14%'"
    ).fetchone()
    assert regle == "R14_doublon_exact"
    assert "(lemonde)" in detail  # on sait quel article a été gardé à sa place


def test_deux_nettoyages_ne_traitent_rien_deux_fois(conn, tmp_path):
    brut = preparer(conn, tmp_path, ITEMS)
    nettoyer(conn, brut, REGLES, MAINTENANT)

    second = nettoyer(conn, brut, REGLES, MAINTENANT)

    assert second.entres == 0
    total = conn.execute(
        "SELECT (SELECT count(*) FROM articles_propres) + (SELECT count(*) FROM rejets)"
    ).fetchone()[0]
    assert total == len(ITEMS)


def test_doublon_avec_un_article_d_un_passage_precedent(conn, tmp_path):
    brut = preparer(conn, tmp_path, ITEMS[:1])
    nettoyer(conn, brut, REGLES, MAINTENANT)
    brut = preparer(conn, tmp_path, ITEMS[:2])  # la reprise arrive au passage suivant

    bilan = nettoyer(conn, brut, REGLES, MAINTENANT)

    assert dict(bilan.par_regle) == {"R14_doublon_exact": 1}


def test_tracabilite(conn, tmp_path):
    brut = preparer(conn, tmp_path, ITEMS)
    nettoyer(conn, brut, REGLES, MAINTENANT)
    cfg = replace(config.load(), articles_dir=str(brut))
    item_id = conn.execute("SELECT item_id FROM articles_propres LIMIT 1").fetchone()[0]

    trace = tracer(conn, cfg, item_id)
    assert trace["sort"] == "gardé"
    assert Path(trace["item_brut"]).exists()
    assert trace["source"].startswith("Lemonde (lemonde)") or trace["source"].startswith(
        "Liberation"
    )

    lien = conn.execute("SELECT lien FROM rejets WHERE regle = 'R02_horoscope'").fetchone()[0]
    trace = tracer(conn, cfg, lien)
    assert (trace["sort"], trace["regle"]) == ("rejeté", "R02_horoscope")


def test_rapport_du_jour(conn, tmp_path):
    brut = preparer(conn, tmp_path, ITEMS)
    bilan = nettoyer(conn, brut, REGLES, MAINTENANT)

    contenu = rapport.construire(conn, MAINTENANT.date(), REGLES, bilan)

    assert "# Rapport de qualité du 2026-10-23" in contenu
    assert "6 items entrés, 2 gardés" in contenu
    assert "| `R02_horoscope` |" in contenu
    assert "## Par source" in contenu
    assert "## Les cinq rejets les plus fréquents" in contenu
    assert "Horoscope du jour" in contenu  # un exemple de rejet
    path = rapport.ecrire(tmp_path / "rapports", MAINTENANT.date(), contenu)
    assert path.name == "qualite-2026-10-23.md"
