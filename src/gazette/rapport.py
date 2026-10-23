"""Le rapport de qualité du jour : combien d'items entrés, gardés, rejetés par règle et
par source, les cinq rejets les plus fréquents, des exemples, et l'état des contrôles.

Réécrit après chaque passage dans rapports/qualite-AAAA-MM-JJ.md : un fichier par jour,
qui couvre toute la journée (UTC) et détaille le dernier passage.
"""

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import psycopg

from gazette.nettoyage import BilanNettoyage
from gazette.regles import Regles


def construire(
    conn: psycopg.Connection,
    jour: date,
    regles: Regles,
    dernier: BilanNettoyage | None = None,
) -> str:
    debut = datetime.combine(jour, time(), tzinfo=UTC)
    bornes = {"debut": debut, "fin": debut + timedelta(days=1)}
    descriptions = regles.descriptions
    seuil = regles.seuils.rejet_max_par_source

    gardes = dict(
        conn.execute(
            "SELECT source_id, count(*) FROM articles_propres"
            " WHERE passage >= %(debut)s AND passage < %(fin)s GROUP BY source_id",
            bornes,
        ).fetchall()
    )
    rejets = conn.execute(
        "SELECT source_id, regle, count(*) FROM rejets"
        " WHERE passage >= %(debut)s AND passage < %(fin)s GROUP BY source_id, regle",
        bornes,
    ).fetchall()
    par_regle: dict[str, int] = {}
    par_source_rejets: dict[str, dict[str, int]] = {}
    for source, regle, n in rejets:
        par_regle[regle] = par_regle.get(regle, 0) + n
        par_source_rejets.setdefault(source, {})[regle] = n
    total_gardes = sum(gardes.values())
    total_rejets = sum(par_regle.values())
    total = total_gardes + total_rejets

    lignes = [f"# Rapport de qualité du {jour.isoformat()}", ""]
    if dernier is not None:
        lignes += [
            f"**Dernier passage** ({dernier.passage:%H:%M} UTC) : {dernier.entres} items entrés, "
            f"{dernier.gardes} gardés, {dernier.rejetes} rejetés"
            + (
                " (" + ", ".join(f"{r} : {n}" for r, n in dernier.par_regle.most_common()) + ")."
                if dernier.par_regle
                else "."
            ),
            "",
        ]
    lignes += [
        f"**Sur la journée** : {total} items entrés, "
        f"{total_gardes} gardés ({_pct(total_gardes, total)}), "
        f"{total_rejets} rejetés ({_pct(total_rejets, total)}).",
        "",
        "## Rejets par règle",
        "",
        "| Règle | Ce qu'elle écarte | Rejets | Part des items entrés |",
        "|---|---|---|---|",
    ]
    for regle, n in sorted(par_regle.items(), key=lambda kv: -kv[1]):
        lignes.append(f"| `{regle}` | {descriptions.get(regle, '')} | {n} | {_pct(n, total)} |")
    if not par_regle:
        lignes.append("| – | aucun rejet | 0 | 0 % |")

    lignes += [
        "",
        "## Par source",
        "",
        f"Taux de rejet au-delà de {seuil:.0%} : ⚠️ (une règle est sans doute trop gourmande).",
        "",
        "| Source | Entrés | Gardés | Rejetés | Taux de rejet | Règle la plus fréquente |",
        "|---|---|---|---|---|---|",
    ]
    for source in sorted(set(gardes) | set(par_source_rejets)):
        g = gardes.get(source, 0)
        rs = par_source_rejets.get(source, {})
        r = sum(rs.values())
        taux = r / (g + r) if g + r else 0
        principale = max(rs.items(), key=lambda kv: kv[1], default=None)
        alerte = " ⚠️" if taux > seuil else ""
        lignes.append(
            f"| {source} | {g + r} | {g} | {r} | {taux:.0%}{alerte} | "
            + (f"`{principale[0]}` ({principale[1]})" if principale else "–")
            + " |"
        )

    lignes += [
        "",
        "## Les cinq rejets les plus fréquents",
        "",
        "| # | Règle | Source | Rejets |",
        "|---|---|---|---|",
    ]
    top = sorted(rejets, key=lambda row: -row[2])[:5]
    for i, (source, regle, n) in enumerate(top, 1):
        lignes.append(f"| {i} | `{regle}` | {source} | {n} |")

    exemples = conn.execute(
        """
        SELECT regle, source_id, titre, detail FROM (
            SELECT *, row_number() OVER (PARTITION BY regle ORDER BY passage DESC, item_id) AS rang
            FROM rejets WHERE passage >= %(debut)s AND passage < %(fin)s
        ) t WHERE rang <= 3 ORDER BY regle, rang
        """,
        bornes,
    ).fetchall()
    lignes += ["", "## Exemples de rejets (trois par règle)", ""]
    regle_courante = None
    for regle, source, titre, detail in exemples:
        if regle != regle_courante:
            lignes += ["", f"**`{regle}`**", ""]
            regle_courante = regle
        lignes.append(f"- {source} : « {titre or '(titre vide)'} » ({detail})")

    controles = conn.execute(
        "SELECT DISTINCT ON (controle) controle, ok, valeur, seuil, detail, passage"
        " FROM controles WHERE passage < %(fin)s ORDER BY controle, passage DESC, id DESC",
        bornes,
    ).fetchall()
    if controles:
        lignes += [
            "",
            f"## Contrôles de qualité (passage de {controles[0][5]:%H:%M} UTC)",
            "",
            "| Contrôle | État | Valeur | Seuil | Détail |",
            "|---|---|---|---|---|",
        ]
        for controle, ok, valeur, seuil_c, detail, _ in controles:
            etat = "✅ ok" if ok else "🔴 échec"
            lignes.append(f"| `{controle}` | {etat} | {valeur:g} | {seuil_c:g} | {detail or ''} |")
    return "\n".join(lignes) + "\n"


def ecrire(rapports_dir: str | Path, jour: date, contenu: str) -> Path:
    path = Path(rapports_dir) / f"qualite-{jour.isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contenu, encoding="utf-8")
    return path


def _pct(n: int, total: int) -> str:
    return f"{n / total:.0%}" if total else "0 %"
