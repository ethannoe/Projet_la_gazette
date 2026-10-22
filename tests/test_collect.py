import json
from pathlib import Path

from gazette import collect

ROOT = Path(__file__).parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "lemonde_une.xml"


def test_collecte_ecrit_un_fichier_json(tmp_path, monkeypatch):
    # Pas de réseau en test : le flux enregistré remplace la requête HTTP.
    monkeypatch.setattr(collect, "fetch", lambda url: FIXTURE.read_bytes())

    code = collect.main(
        ["--source", "lemonde", "--sources-file", str(ROOT / "sources.csv"), "--out", str(tmp_path)]
    )

    assert code == 0
    [path] = tmp_path.glob("*/lemonde-*.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source"] == "Le Monde"
    assert payload["feed_url"] == "https://www.lemonde.fr/rss/une.xml"
    assert payload["count"] == len(payload["items"]) == 3
