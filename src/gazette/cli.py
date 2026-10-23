"""Ligne de commande : python -m gazette <commande>.

migrer               applique les migrations en attente
collecter            un passage tout de suite (--source pour en viser une)
nettoyer             brut → articles_propres / rejets, puis rapport du jour
rejouer REGLE        après avoir modifié une règle : repasse ses rejets dans les règles
controler            contrôles de qualité sur les vraies données, alerte si un fait est faux
rapport              réécrit le rapport de qualité (--jour AAAA-MM-JJ)
purger               applique la rétention (docs/donnees.md)
themes               un run de regroupement tout de suite (--fin pour rejouer une fenêtre passée)
runs                 les derniers runs : données, paramètres, métriques
themes-du-jour       les thèmes du dernier run réussi
tracer ID|LIEN       d'un article, retrouver son sort, sa source et son item brut
planifier            tout ça toutes les GAZETTE_INTERVALLE_MIN minutes, via Prefect
etat                 état de chaque source : dernière réussite, échecs, sommeils, articles
reveiller SOURCE     sort une source du sommeil
"""

import argparse
from datetime import UTC, date, datetime, timedelta

from gazette import config, db, journal, pipeline
from gazette.collecteur import collect_all
from gazette.sources import load_sources
from gazette.stockage import count_items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gazette", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="commande", required=True)
    commands.add_parser("migrer", help="applique les migrations en attente")
    collecter = commands.add_parser("collecter", help="un passage tout de suite")
    collecter.add_argument("--source", action="append", help="id de sources.csv (répétable)")
    commands.add_parser("nettoyer", help="brut → articles_propres / rejets, puis rapport")
    rejouer = commands.add_parser("rejouer", help="repasse les rejets d'une règle modifiée")
    rejouer.add_argument("regle", help="ex. R07_media_seul")
    commands.add_parser("controler", help="contrôles de qualité et alerte")
    rapport = commands.add_parser("rapport", help="réécrit le rapport de qualité")
    rapport.add_argument("--jour", type=date.fromisoformat, help="AAAA-MM-JJ (UTC)")
    commands.add_parser("purger", help="applique la rétention")
    themes = commands.add_parser("themes", help="un run de regroupement tracé")
    themes.add_argument(
        "--fin",
        type=datetime.fromisoformat,
        help="fin de la fenêtre (ISO 8601) pour rejouer un run",
    )
    runs = commands.add_parser("runs", help="les derniers runs")
    runs.add_argument("-n", type=int, default=10)
    commands.add_parser("themes-du-jour", help="les thèmes du dernier run réussi")
    tracer = commands.add_parser("tracer", help="sort, source et item brut d'un article")
    tracer.add_argument("cle", metavar="ID|LIEN")
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
        elif args.commande == "nettoyer":
            bilan = pipeline.nettoyer(conn, cfg)
            path, _ = pipeline.rapporter(conn, cfg, bilan)
            print(f"{bilan.gardes} gardés, {bilan.rejetes} rejetés ; rapport : {path}")
        elif args.commande == "rejouer":
            oublies = db.forget_rejections(conn, args.regle)
            bilan = pipeline.nettoyer(conn, cfg)
            path, _ = pipeline.rapporter(conn, cfg, bilan)
            print(
                f"{oublies} rejets {args.regle} repassés : {bilan.gardes} gardés, "
                f"{bilan.rejetes} rejetés à nouveau ; rapport : {path}"
            )
        elif args.commande == "controler":
            resultats = pipeline.controler(conn, cfg)
            pipeline.rapporter(conn, cfg)
            return 0 if all(r.ok for r in resultats) else 1
        elif args.commande == "rapport":
            path, contenu = pipeline.rapporter(conn, cfg, jour=args.jour)
            print(contenu)
            print(f"(écrit dans {path})")
        elif args.commande == "themes":
            fin = args.fin.astimezone(UTC) if args.fin and args.fin.tzinfo else args.fin
            if fin is not None and fin.tzinfo is None:
                fin = fin.replace(tzinfo=UTC)
            run = pipeline.regrouper(conn, cfg, declencheur="manuel", fin=fin)
            print(f"run {run.run_id} : {run.metriques}")
            for theme in run.themes:
                print(f"  {theme['numero']:2} [{theme['taille']:2}] {theme['nom']}")
        elif args.commande == "runs":
            print_runs(conn, args.n)
        elif args.commande == "themes-du-jour":
            print_themes_du_jour(conn)
        elif args.commande == "purger":
            print(pipeline.retenir(conn, cfg))
        elif args.commande == "tracer":
            trace = pipeline.tracer(conn, cfg, args.cle)
            if trace is None:
                print(f"aucun article {args.cle!r} dans articles_propres ni dans rejets")
                return 1
            for cle, valeur in trace.items():
                if valeur is not None:
                    print(f"{cle:10} {valeur}")
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


def print_runs(conn, n: int) -> None:
    rows = conn.execute(
        "SELECT run_id, statut, declencheur, nb_articles, hash_entree, modele_version,"
        " hash_parametres, code_version, metriques FROM runs ORDER BY debut DESC LIMIT %s",
        (n,),
    ).fetchall()
    for run_id, statut, declencheur, nb, entree, version, params, code, m in rows:
        m = m or {}
        print(
            f"{run_id}  {statut:8} {declencheur:8} {nb:4} articles  entrée {entree}"
            f"  modèle @{version[:8]}  params {params}  code {code}"
        )
        if m:
            print(
                f"    {m.get('nb_themes')} thèmes, médiane {m.get('taille_mediane')},"
                f" bruit {m.get('part_bruit')}, silhouette {m.get('silhouette')}"
            )


def print_themes_du_jour(conn) -> None:
    rows = conn.execute(
        "SELECT run_id, numero, nom, taille, mots_cles FROM themes_du_jour ORDER BY numero"
    ).fetchall()
    if not rows:
        print("aucun run réussi pour l'instant")
        return
    print(f"thèmes du run {rows[0][0]} :")
    for _, numero, nom, taille, mots in rows:
        print(f"  {numero:2} [{taille:2}] {nom:40} {', '.join(mots[3:])}")
