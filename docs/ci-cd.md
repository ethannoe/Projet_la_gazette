# Stratégie CI/CD

1. **Outil** : GitHub Actions ([.github/workflows/ci.yml](../.github/workflows/ci.yml)), lancé à chaque push sur `main` et sur chaque pull request.
2. **Étapes**, chacune bloquante pour la suivante : lint (ruff) → tests (pytest, sans réseau, sur des flux enregistrés) → build de l'image Docker.
3. **Publication** : seulement depuis `main`, sur `ghcr.io/ethannoe/projet_la_gazette`.
4. **Tag** : `AAAAMMJJHHMMSS-sha` (heure UTC du build et 7 premiers caractères du commit). On sait quand l'image a été construite et à partir de quel code. Pas de `latest`.
5. **Pull request** : l'image est construite mais pas publiée, pour vérifier le Dockerfile avant le merge.
6. **Protection de `main`** : merge uniquement par PR, avec une CI verte et une relecture (voir [CONTRIBUTING.md](../CONTRIBUTING.md)).
7. **CI rouge** : on la répare avant tout le reste, et on ne désactive jamais un test pour la faire passer.
8. **Local = CI** : les mêmes commandes (`ruff check src tests`, `pytest`) tournent en local avec `bin/test` et dans la CI.
9. **Image** : multi-étapes, base `python:3.12-slim`, utilisateur non root, sans outils de dev ni tests.
10. **Hors périmètre pour l'instant** : déploiement automatique (TD 7), matrice de versions, cache de build.
