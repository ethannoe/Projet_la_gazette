"""Collecte une source : télécharge son flux, le parse, écrit les items en JSON.

Usage : python -m gazette.collect --source lemonde --out data/raw
"""

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import requests

from gazette import __version__
from gazette.parser import parse_feed
from gazette.sources import Source, get_source, load_sources

USER_AGENT = f"LaGazetteBot/{__version__} (+https://github.com/ethannoe/Projet_la_gazette)"
TIMEOUT = 20  # secondes

log = logging.getLogger("gazette.collect")


def fetch(url: str) -> bytes:
    """Une seule requête par flux, avec un User-Agent qui nous identifie."""
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.content


def write_items(
    items: list[dict], source: Source, out_dir: str | Path, fetched_at: datetime
) -> Path:
    """Écrit un fichier par passage : <out>/<AAAA-MM-JJ>/<source>-<horodatage>.json."""
    day_dir = Path(out_dir) / fetched_at.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{source.id}-{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    payload = {
        "source": source.name,
        "feed_url": source.url,
        "fetched_at": fetched_at.isoformat(),
        "count": len(items),
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collecte une source de sources.csv en JSON.")
    parser.add_argument("--source", default="lemonde", help="id de la source dans sources.csv")
    parser.add_argument("--sources-file", default="sources.csv")
    parser.add_argument("--out", default="data/raw", help="dossier des fichiers bruts")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    source = get_source(load_sources(args.sources_file), args.source)
    fetched_at = datetime.now(UTC).replace(microsecond=0)
    items = parse_feed(fetch(source.url), source.name)
    path = write_items(items, source, args.out, fetched_at)
    log.info("%s : %d items écrits dans %s", source.name, len(items), path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
