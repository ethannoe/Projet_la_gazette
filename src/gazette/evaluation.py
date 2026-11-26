"""Évaluation bornée des thèmes et surveillance de dérive."""

from datetime import timedelta
from pathlib import Path

import psycopg
import yaml
from psycopg.types.json import Jsonb


def charger(path: str | Path) -> dict:
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not {"seuils", "echantillon", "derive"} <= config.keys():
        raise ValueError("evaluation.yaml doit définir seuils, echantillon et derive")
    return config


def evaluer(
    conn: psycopg.Connection,
    run_id: str,
    metriques: dict,
    articles: list[dict],
    etiquettes,
    config: dict,
) -> tuple[str, dict]:
    """Renvoie (verdict, détail). Un verdict revue bloque la promotion jusqu'à relecture."""
    seuils = config["seuils"]
    n = metriques["nb_articles"]
    taille_geante = metriques["taille_max"] / n if n else 0.0
    mesures = dict(metriques) | {"part_theme_geant": round(taille_geante, 4)}
    controles = {
        "silhouette": mesures["silhouette"] is not None
        and mesures["silhouette"] >= seuils["silhouette_min"],
        "part_bruit": mesures["part_bruit"] <= seuils["part_bruit_max"],
        "part_theme_geant": taille_geante <= seuils["part_theme_geant_max"],
        "themes_min": mesures["nb_themes"] >= seuils["themes_min"],
    }
    taille = int(config["echantillon"]["taille"])
    if taille < 1:
        raise ValueError("echantillon.taille doit être supérieur à zéro")
    echantillon = [
        {"item_id": a["item_id"], "titre": a["titre"], "theme": int(etiquettes[i])}
        for i, a in enumerate(articles)
    ]
    echantillon.sort(key=lambda a: a["item_id"])
    if len(echantillon) > taille:
        # Échantillon déterministe et réparti, y compris des articles classés comme bruit.
        indices = (
            [round(i * (len(echantillon) - 1) / (taille - 1)) for i in range(taille)]
            if taille > 1 else [0]
        )
        echantillon = [echantillon[i] for i in indices]

    drift = _derive(conn, run_id, mesures, config["derive"])
    ok = all(controles.values())
    verdict = "recale" if not ok else ("revue" if drift["declenchee"] else "candidat")
    details = {
        "verdict": verdict,
        "mesures": mesures,
        "seuils": seuils,
        "controles": controles,
        "derive": drift,
        "echantillon": echantillon,
        "relecture": None,
    }
    conn.execute(
        "UPDATE runs SET evaluation = %s, verdict = %s WHERE run_id = %s",
        (Jsonb(details), verdict, run_id),
    )
    return verdict, details


def _derive(conn: psycopg.Connection, run_id: str, mesures: dict, params: dict) -> dict:
    (jour_courant,) = conn.execute(
        "SELECT (debut AT TIME ZONE 'UTC')::date FROM runs WHERE run_id = %s", (run_id,)
    ).fetchone()
    rows = conn.execute(
        "SELECT (debut AT TIME ZONE 'UTC')::date, metriques FROM runs"
        " WHERE (debut AT TIME ZONE 'UTC')::date < %s"
        " AND declencheur = 'pipeline' AND metriques IS NOT NULL AND statut = 'ok'"
        " ORDER BY debut DESC LIMIT 10",
        (jour_courant,),
    ).fetchall()
    daily = {}
    for jour, anciennes in rows:
        daily.setdefault(jour, anciennes)
    jours = list(daily.items())

    def derive(a, b):
        if a is None or b is None:
            return False
        bruit = float(a.get("part_bruit", 0)) - float(b.get("part_bruit", 0))
        sa, sb = a.get("silhouette"), b.get("silhouette")
        baisse = float(sb) - float(sa) if sa is not None and sb is not None else 0.0
        return bruit >= params["hausse_bruit"] or baisse >= params["baisse_silhouette"]

    jour_precedent, metriques_precedentes = jours[0] if jours else (None, None)
    courant_derives = (
        derive(mesures, metriques_precedentes)
        if jour_precedent == jour_courant - timedelta(days=1)
        else False
    )
    consecutifs = int(courant_derives)
    for index in range(len(jours) - 1):
        jour, mesures_jour = jours[index]
        jour_avant, mesures_avant = jours[index + 1]
        if jour_avant != jour - timedelta(days=1) or not derive(mesures_jour, mesures_avant):
            break
        consecutifs += 1
    return {
        "declenchee": consecutifs >= int(params["jours_consecutifs"]),
        "jours_consecutifs": consecutifs,
        "seuil_jours": params["jours_consecutifs"],
    }


def enregistrer_relecture(
    conn: psycopg.Connection,
    run_id: str,
    decision: str,
    commentaire: str,
    par_qui: str,
) -> str:
    if decision not in ("approuve", "recale"):
        raise ValueError("la décision doit être approuve ou recale")
    with conn.transaction():
        row = conn.execute(
            "SELECT evaluation, verdict, statut FROM runs WHERE run_id = %s FOR UPDATE", (run_id,)
        ).fetchone()
        if row is None or row[0] is None:
            raise ValueError(f"run sans évaluation : {run_id}")
        evaluation, verdict, statut = row
        if statut != "ok":
            raise ValueError(f"run non terminé avec succès : {run_id} ({statut})")
        if verdict == "recale":
            raise ValueError("un run recalé par les seuils ne peut pas être promu")
        resultat = {"decision": decision, "commentaire": commentaire, "par_qui": par_qui}
        evaluation["relecture"] = resultat
        if decision == "recale":
            verdict_final = "recale"
        else:
            verdict_final = "candidat"
        evaluation["verdict"] = verdict_final
        conn.execute(
            "INSERT INTO relectures_modeles (run_id, decision, echantillon, commentaire, par_qui)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (run_id) DO UPDATE SET"
            " decision=EXCLUDED.decision, echantillon=EXCLUDED.echantillon,"
            " commentaire=EXCLUDED.commentaire, par_qui=EXCLUDED.par_qui, relu_le=now()",
            (run_id, decision, Jsonb(evaluation["echantillon"]), commentaire, par_qui),
        )
        conn.execute(
            "UPDATE runs SET evaluation=%s, verdict=%s WHERE run_id=%s",
            (Jsonb(evaluation), verdict_final, run_id),
        )
        if verdict_final == "recale":
            conn.execute("UPDATE versions_modele SET statut='archivee' WHERE run_id=%s", (run_id,))
            conn.execute("DELETE FROM themes WHERE run_id=%s", (run_id,))
    return verdict_final
