# La gazette

[![CI](https://github.com/ethannoe/Projet_la_gazette/actions/workflows/ci.yml/badge.svg)](https://github.com/ethannoe/Projet_la_gazette/actions/workflows/ci.yml)

Chaque matin à 7 h, une édition qui montre de quoi parle la presse française : les thèmes du jour,
les journaux qui les traitent et les liens pour lire la suite. On ne résume pas les articles, on les
regroupe par thèmes. Le besoin, le périmètre et la stack sont décrits dans
[docs/cadrage.md](docs/cadrage.md).

Où on en est (TD 3) : la collecte tourne seule. Toutes les 30 min, les flux RSS des sources de
[sources.csv](sources.csv) sont lus, et chaque nouvel article est écrit une seule fois dans
`articles_bruts/`. La table `sources` garde l'état de chaque source, et une source qui échoue trois
fois de suite est mise en sommeil.

## Lancer le projet

Prérequis : [Docker](https://docs.docker.com/get-docker/) avec Compose v2, et git. Sous Windows,
passer par WSL.

```bash
git clone https://github.com/ethannoe/Projet_la_gazette.git && cd Projet_la_gazette
bin/dev
```

`bin/dev` démarre PostgreSQL, le serveur Prefect et la collecte planifiée, fait un premier passage
tout de suite, puis affiche l'état des sources :

```
source        état     dernière réussite     échecs  passages        sommeils  articles
lemonde       actif    2026-10-22 09:46 UTC  0       1 (0 en échec)  0         16
lesechos      actif    jamais                1       1 (1 en échec)  0         0
…
- lesechos : HTTP 403
```

- Les articles bruts sont dans `articles_bruts/<source>/<id>.json` (champs décrits dans
  [docs/donnees.md](docs/donnees.md)).
- L'interface Prefect, avec l'historique des passages, est sur http://localhost:4200.
- Les journaux, une ligne JSON par source et par passage :
  `docker compose logs -f collecteur`.
- Tout arrêter : `docker compose down` (ajouter `-v` pour effacer aussi la base).

Les commandes du quotidien (état, réveil d'une source, fréquence) sont dans
[docs/orchestration.md](docs/orchestration.md).

## Tester

```bash
bin/test
```

Lint (ruff) et tests (pytest) dans un conteneur, avec une vraie base PostgreSQL : rien à installer à
part Docker. Les tests n'utilisent jamais Internet : flux enregistrés dans `tests/fixtures/`, et un
serveur HTTP local qui joue l'éditeur (503, 404, ETag…). Parmi eux :

- `test_deux_passages_zero_doublon` : deux passages de suite n'écrivent aucun doublon ;
- `test_source_en_panne_mise_en_sommeil` : une source qui répond 503 est réessayée avec une
  attente croissante, puis mise en sommeil au troisième passage en échec.

## Arborescence

```
src/gazette/          le code (python -m gazette <commande>)
  cli.py                commandes : migrer, collecter, planifier, etat, reveiller
  flows.py              orchestration Prefect : un passage toutes les 30 min
  collecteur.py         un passage : chaque source active, compteurs, mise en sommeil
  fetch.py              requête polie : User-Agent, ETag / Last-Modified, timeouts, backoff
  parser.py             flux RSS / Atom → items bruts
  stockage.py           articles_bruts/<source>/<id>.json, sans doublon
  db.py                 PostgreSQL : migrations, table sources, table collectes
  migrations/           migrations SQL versionnées
tests/                tests pytest et flux enregistrés (fixtures/)
docs/                 cadrage, veille, données, flux, orchestration, qualité, CI/CD
infra/                infrastructure as code à venir
bin/                  dev et test : les deux seules commandes à connaître
Dockerfile            multi-étapes : builder → test → runtime (non root)
docker-compose.yml    PostgreSQL, Prefect, collecte planifiée, tests
sources.csv           les 9 flux retenus
```

## Intégration continue

Chaque push sur `main` lance [la CI](.github/workflows/ci.yml) : lint → tests → build de l'image
→ publication sur `ghcr.io/ethannoe/projet_la_gazette:<AAAAMMJJHHMMSS>-<sha>`. Sur une pull request,
les mêmes étapes tournent, mais l'image n'est pas publiée. La stratégie est détaillée dans
[docs/ci-cd.md](docs/ci-cd.md).

## Contribuer

Branches, format des commits, revue, qui merge : voir [CONTRIBUTING.md](CONTRIBUTING.md).
