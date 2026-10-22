"""Lecture de sources.csv : la liste des flux que l'on a le droit de lire."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    kind: str  # PQN (presse nationale) ou PQR (presse régionale)
    region: str
    url: str


def load_sources(path: str | Path) -> list[Source]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            Source(
                id=row["id"],
                name=row["nom"],
                kind=row["type"],
                region=row["region"],
                url=row["acces"],
            )
            for row in csv.DictReader(f)
        ]


def get_source(sources: list[Source], source_id: str) -> Source:
    for source in sources:
        if source.id == source_id:
            return source
    known = ", ".join(s.id for s in sources)
    raise KeyError(f"source inconnue : {source_id!r} (sources connues : {known})")
