import json

from gazette.stockage import CHAMPS, build_item, count_items, item_id, write_item

PARSED = {
    "lien": "https://exemple.test/a",
    "titre": "Titre",
    "resume": "Extrait",
    "publie_le": "2026-10-22T06:00:00+00:00",
    "rubrique": "societe",
    "payload": {"title": "Titre"},
}


def test_id_stable_et_propre_a_la_source():
    assert item_id("lemonde", PARSED["lien"]) == item_id("lemonde", PARSED["lien"])
    assert item_id("lemonde", PARSED["lien"]) != item_id("lefigaro", PARSED["lien"])


def test_item_a_les_champs_du_dictionnaire_de_donnees():
    item = build_item(PARSED, "lemonde", "2026-10-22T09:00:00+00:00")
    assert tuple(item) == CHAMPS
    assert item["source"] == "lemonde"
    assert item["recupere_le"] == "2026-10-22T09:00:00+00:00"


def test_un_item_ne_s_ecrit_qu_une_fois(tmp_path):
    item = build_item(PARSED, "lemonde", "2026-10-22T09:00:00+00:00")
    assert write_item(tmp_path, item) is True
    plus_tard = build_item(PARSED, "lemonde", "2026-10-22T09:30:00+00:00")
    assert write_item(tmp_path, plus_tard) is False

    [path] = (tmp_path / "lemonde").glob("*.json")
    assert path.name == f"{item['id']}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["recupere_le"] == item["recupere_le"]
    assert count_items(tmp_path, "lemonde") == 1
    assert count_items(tmp_path, "inconnue") == 0
