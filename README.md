# La gazette

[![CI](https://github.com/ethannoe/Projet_la_gazette/actions/workflows/ci.yml/badge.svg)](https://github.com/ethannoe/Projet_la_gazette/actions/workflows/ci.yml)

Chaque matin à 7 h, une édition qui montre de quoi parle la presse française : les thèmes du jour,
les journaux qui les traitent et les liens pour lire la suite. On ne résume pas les articles, on les
regroupe par thèmes. Le besoin, le périmètre et la stack sont décrits dans
[docs/cadrage.md](docs/cadrage.md).

Pour l'instant (TD 2) : une source, Le Monde, est lue de bout en bout. Son flux RSS est téléchargé,
parsé, et les articles sont écrits en JSON.

## Lancer le projet

Prérequis : [Docker](https://docs.docker.com/get-docker/) avec Compose v2, et git. Sous Windows,
passer par WSL.

```bash
git clone https://github.com/ethannoe/Projet_la_gazette.git && cd Projet_la_gazette
bin/dev
```

`bin/dev` construit l'image, démarre PostgreSQL, puis collecte le flux du Monde. Le résultat est
dans `data/raw/AAAA-MM-JJ/lemonde-<horodatage>.json` :

```json
{
  "source": "Le Monde",
  "feed_url": "https://www.lemonde.fr/rss/une.xml",
  "fetched_at": "2026-10-22T09:12:50+00:00",
  "count": 16,
  "items": [
    {
      "source": "Le Monde",
      "title": "…",
      "summary": "…",
      "url": "https://www.lemonde.fr/…",
      "published_at": "2026-10-22T07:45:09+00:00"
    }
  ]
}
```

- Une autre source : `bin/dev --source liberation` (les `id` sont dans [sources.csv](sources.csv)).
- Tout arrêter : `docker compose down` (ajouter `-v` pour effacer aussi la base).

## Tester

```bash
bin/test
```

Lint (ruff) et tests (pytest) dans un conteneur : rien à installer à part Docker. Les tests ne
touchent pas au réseau, ils utilisent des flux enregistrés dans `tests/fixtures/`.

Sans Docker, avec Python 3.11 ou plus :

```bash
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
ruff check src tests && pytest
```

## Arborescence

```
src/gazette/        le code
  sources.py          lecture de sources.csv
  parser.py           flux RSS/Atom → items (titre, extrait, lien, date, source)
  collect.py          télécharge une source et écrit le JSON (python -m gazette.collect)
tests/              tests pytest
  fixtures/           flux enregistrés pour les tests
docs/               cadrage, veille, stratégie CI/CD
infra/              infrastructure as code à venir (Prefect, déploiement, supervision)
bin/                dev et test : les deux seules commandes à connaître
Dockerfile          multi-étapes : builder → test → runtime (non root)
docker-compose.yml  l'environnement de dev : collecte + PostgreSQL
sources.csv         les 9 flux retenus
```

## Intégration continue

Chaque push sur `main` lance [la CI](.github/workflows/ci.yml) : lint → tests → build de l'image
→ publication sur `ghcr.io/ethannoe/projet_la_gazette:<AAAAMMJJHHMMSS>-<sha>`. Sur une pull request,
les mêmes étapes tournent, mais l'image n'est pas publiée. La stratégie est détaillée dans
[docs/ci-cd.md](docs/ci-cd.md).

```bash
docker run --rm -v "$PWD/data:/data" ghcr.io/ethannoe/projet_la_gazette:<tag>
```

## Contribuer

Branches, format des commits, revue, qui merge : voir [CONTRIBUTING.md](CONTRIBUTING.md).
