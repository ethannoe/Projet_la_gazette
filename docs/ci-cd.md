# Stratégie CI/CD

1. **Outil** : GitHub Actions ([.github/workflows/ci.yml](../.github/workflows/ci.yml)), lancé à chaque push sur `main` et sur chaque pull request.
2. **Étapes** : lint (ruff) → tests (pytest, avec flux enregistrés et vraie base PostgreSQL) → build de l'image Docker ; les PR internes évaluent aussi le candidat sur les données réelles de la veille.
3. **Publication** : seulement depuis `main`, sur `ghcr.io/ethannoe/projet_la_gazette`.
4. **Tag** : `AAAAMMJJHHMMSS-sha` (heure UTC du build et 7 premiers caractères du commit). On sait quand l'image a été construite et à partir de quel code. Pas de `latest`.
5. **Pull request** : l'image est construite mais pas publiée, pour vérifier le Dockerfile avant le merge.
6. **Protection de `main`** : merge uniquement par PR, avec une CI verte et une relecture (voir [CONTRIBUTING.md](../CONTRIBUTING.md)).
7. **CI rouge** : on la répare avant tout le reste, et on ne désactive jamais un test pour la faire passer.
8. **Local = CI** : les mêmes commandes (`ruff check src tests`, `pytest`) tournent en local avec `bin/test` et dans la CI, avec la même version de PostgreSQL.
9. **Image** : multi-étapes, base `python:3.12-slim`, utilisateur non root, sans outils de dev ni tests.
10. **Hors périmètre pour l'instant** : déploiement automatique (TD 7), matrice de versions, cache de build.

## Évaluation et promotion du modèle (TD 6)

Pour une PR interne, un job supplémentaire évalue `config/clustering.yaml` sur les articles
de la journée précédente dans la base accessible par le secret `GAZETTE_DATABASE_URL`. Il
produit `evaluation.json` (métriques, verdict, dérive et échantillon à relire) dans l'artifact
`evaluation-candidat`. La CI ne modifie pas les thèmes utilisés ni la version `production`.

Une personne examine les dix titres et enregistre son avis avec la commande `relire` dans
[`docs/mlops.md`](mlops.md). La fusion sur `main` déclenche le job de promotion après la
construction de l'image. Il cherche la dernière évaluation CI correspondant à l'empreinte
des paramètres fusionnés et à la tête de la PR, et la promeut uniquement si les seuils et la
relecture passent. Configurez `evaluer-candidat` comme contrôle requis de la branche `main`.
La promotion écrit `historique_promotions`; les conteneurs lisent ensuite la configuration
active depuis la table `versions_modele`. Si l'évaluation ou la relecture échoue, le job de
promotion échoue et la version en service reste la même.

Le compte de base de données du secret doit pouvoir lire les articles propres et écrire les
runs, évaluations, relectures et changements de registre. Les PR externes n'ont pas accès au
secret, donc l'évaluation sur les données réelles est réservée aux PR internes.
