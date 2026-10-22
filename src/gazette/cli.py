"""Ligne de commande : python -m gazette <commande>.

migrer               applique les migrations en attente
collecter            un passage tout de suite (--source pour en viser une)
planifier            un passage toutes les GAZETTE_INTERVALLE_MIN minutes, via Prefect
etat                 état de chaque source : dernière réussite, échecs, sommeils, articles
reveiller SOURCE     sort une source du sommeil
"""

import argparse
from datetime import timedelta

from gazette import config, db, journal
from gazette.collecteur import collect_all
from gazette.sources import load_sources
from gazette.stockage import count_items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gazette", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="commande", required=True)
    commands.add_parser("migrer", help="applique les migrations en attente")
    collecter = commands.add_parser("collecter", help="un passage tout de suite")
    collecter.add_argument("--source", action="append", help="id de sources.csv (répétable)")
    commands.add_parser("planifier", help="collecte planifiée par Prefect")
    commands.add_parser("etat", help="état de chaque source")
    reveiller = commands.add_parser("reveiller", help="sort une source du sommeil")
    reveiller.add_argument("source")
    args = parser.parse_args(argv)

    journal.configure()
    cfg = config.load()

    if args.commande == "planifier":
        from gazette.flows import planifier  # Prefect n'est chargé que si on en a besoin

        planifier(cfg.intervalle_min)
        return 0

    with db.connect(cfg.database_url) as conn:
        if args.commande == "migrer":
            applied = db.migrate(conn)
            print("migrations appliquées :", ", ".join(applied) or "aucune, la base est à jour")
        elif args.commande == "collecter":
            bilans = collect_all(
                conn,
                cfg.sources_file,
                cfg.articles_dir,
                only=args.source,
                delai=timedelta(minutes=cfg.delai_min),
            )
            return 1 if bilans and all(b.statut == "echec" for b in bilans) else 0
        elif args.commande == "etat":
            db.migrate(conn)
            en_service = {s.id for s in load_sources(cfg.sources_file)}
            print_report(db.report(conn), cfg.articles_dir, en_service)
        elif args.commande == "reveiller":
            if not db.wake_up(conn, args.source):
                print(f"source inconnue : {args.source}")
                return 1
            print(f"{args.source} réveillée : elle sera collectée au prochain passage")
    return 0


def print_report(rows: list[dict], articles_dir: str, en_service: set[str] | None = None) -> None:
    """Une ligne par source ; celles retirées de sources.csv restent, avec leur historique."""
    header = ("source", "état", "dernière réussite", "échecs", "passages", "sommeils", "articles")
    lines = [header]
    for r in rows:
        reussite = r["derniere_reussite"]
        lines.append(
            (
                r["id"],
                _etat(r, en_service),
                reussite.strftime("%Y-%m-%d %H:%M UTC") if reussite else "jamais",
                str(r["echecs_consecutifs"]),
                f"{r['passages']} ({r['echecs']} en échec)",
                str(r["sommeils"]),
                str(count_items(articles_dir, r["id"])),
            )
        )
    widths = [max(len(line[i]) for line in lines) for i in range(len(header))]
    for line in lines:
        print("  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)))
    for r in rows:
        if r["derniere_erreur"]:
            print(f"- {r['id']} : {r['derniere_erreur']}")


def _etat(row: dict, en_service: set[str] | None) -> str:
    if en_service is not None and row["id"] not in en_service:
        return "retirée"
    return "actif" if row["actif"] else "SOMMEIL"
