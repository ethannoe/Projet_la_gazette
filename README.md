# La gazette

[![CI](https://github.com/ethannoe/Projet_la_gazette/actions/workflows/ci.yml/badge.svg)](https://github.com/ethannoe/Projet_la_gazette/actions/workflows/ci.yml)

Chaque matin à 7 h, une édition qui montre de quoi parle la presse française : les thèmes du jour,
les journaux qui les traitent et les liens pour lire la suite. On ne résume pas les articles, on les
regroupe par thèmes. Le besoin, le périmètre et la stack sont décrits dans
[docs/cadrage.md](docs/cadrage.md).

Où on en est (TD 5), toutes les 30 min :
- **collecte** : les flux RSS de [sources.csv](sources.csv) sont lus, et chaque nouvel article est
  écrit une seule fois dans `articles_bruts/` ;
- **nettoyage** : chaque article est normalisé et passe des règles d'exclusion (publi,
  horoscope, programme TV, doublons…), puis va dans la table `articles_propres` ou dans `rejets`,
  avec la règle qui l'a écarté ;
- **contrôles** : des contrôles de qualité vérifient les vraies données, et alertent l'équipe si un
  fait est faux ;
- **rapport** : un rapport de qualité dit, chaque jour, ce qui a été rejeté, par règle et par
  source (`rapports/qualite-AAAA-MM-JJ.md`) ;
- **thèmes** (une fois par jour, après 6 h 30) : les articles propres des dernières 24 h sont
  vectorisés, regroupés (HDBSCAN) et nommés par leurs mots-clés. Chaque run est tracé
  (données, paramètres, métriques, artefacts) : voir [docs/mlops.md](docs/mlops.md).

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
ladepeche     actif    2026-10-22 10:20 UTC  0       1 (0 en échec)  0         100
lemonde       actif    2026-10-22 10:08 UTC  0       8 (0 en échec)  0         19
lesechos      retirée  jamais                3       3 (3 en échec)  1         0
…
- lesechos : HTTP 403
```

Une source `SOMMEIL` a échoué 3 fois de suite et n'est plus interrogée ; une source
`retirée` n'est plus dans `sources.csv` mais garde son historique.

- Les articles bruts sont dans `articles_bruts/<source>/<id>.json`, les articles propres dans la
  table `articles_propres` (contrat et champs : [docs/donnees.md](docs/donnees.md)).
- Le rapport de qualité du jour : `rapports/qualite-AAAA-MM-JJ.md` (comment le lire :
  [docs/qualite.md](docs/qualite.md)).
- Les thèmes du jour : `docker compose run --rm collecteur themes-du-jour` ; les runs :
  `docker compose run --rm collecteur runs`.
- Pour brancher l'alerte sur le Discord ou le Slack de l'équipe, mettre
  `GAZETTE_ALERTE_WEBHOOK=…` dans un fichier `.env` (voir [docs/orchestration.md](docs/orchestration.md)).
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
  attente croissante, puis mise en sommeil au troisième passage en échec ;
- `test_nos_dix_pollueurs_sont_ecartes` et `test_de_vrais_articles_sont_gardes` : les règles
  d'exclusion, sur de vrais items ;
- `test_un_fait_faux_declenche_une_alerte_une_seule_fois` : les contrôles de qualité et leur alerte ;
- `test_vrai_modele_sur_dix_articles`, `test_meme_entree_memes_themes` : les embeddings et la
  reproductibilité des runs de regroupement.

## Arborescence

```
src/gazette/          le code (python -m gazette <commande>)
  cli.py                commandes : collecter, nettoyer, controler, rapport, tracer, etat…
  flows.py              orchestration Prefect : collecte → nettoyage → contrôles → rapport
  collecteur.py         un passage : chaque source active, compteurs, mise en sommeil
  fetch.py              requête polie : User-Agent, ETag / Last-Modified, timeouts, backoff
  parser.py             flux RSS / Atom → items bruts
  stockage.py           articles_bruts/<source>/<id>.json, sans doublon
  normalisation.py      une fonction pure par transformation (HTML, encodage, dates…)
  regles.py             règles d'exclusion R01…R15 et dédoublonnage
  nettoyage.py          brut → articles_propres / rejets
  controles.py          contrôles de qualité sur les vraies données, alerte (alertes.py)
  rapport.py            rapport de qualité du jour
  retention.py          purge selon les durées de conservation
  embeddings.py         titre + extrait → vecteur (fastembed), cache en base
  themes.py             regroupement HDBSCAN, nommage, runs tracés
  db.py                 PostgreSQL : migrations, tables sources, collectes
  migrations/           migrations SQL versionnées
tests/                tests pytest et flux enregistrés (fixtures/)
docs/                 cadrage, veille, données, flux, orchestration, qualité, CI/CD
infra/                infrastructure as code à venir
bin/                  dev et test : les deux seules commandes à connaître
Dockerfile            multi-étapes : builder → test → runtime (non root)
docker-compose.yml    PostgreSQL, Prefect, pipeline planifié, tests
sources.csv           les 9 flux retenus
regles.toml           motifs et seuils des règles d'exclusion
config/               paramètres du regroupement (clustering.yaml) et mots vides
```

## Intégration continue

Chaque push sur `main` lance [la CI](.github/workflows/ci.yml) : lint → tests → build de l'image
→ publication sur `ghcr.io/ethannoe/projet_la_gazette:<AAAAMMJJHHMMSS>-<sha>`. Sur une pull request,
les mêmes étapes tournent, mais l'image n'est pas publiée. La stratégie est détaillée dans
[docs/ci-cd.md](docs/ci-cd.md).

## Contribuer

Branches, format des commits, revue, qui merge : voir [CONTRIBUTING.md](CONTRIBUTING.md).
