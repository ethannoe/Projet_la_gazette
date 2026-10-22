# Contribuer à La gazette

## La règle

`main` est toujours déployable. On n'y pousse rien directement : tout passe par une pull request
dont la CI est verte et qui a été relue.

## Branches

- Une branche par sujet, partie d'un `main` à jour, qui vit quelques jours au plus.
- Nom : `type/sujet-court`, en minuscules et avec des tirets. Exemples : `feat/collecte-figaro`,
  `fix/date-sans-fuseau`, `docs/readme-windows`, `ci/push-image`, `infra/prefect`.

## Commits

Format [Conventional Commits](https://www.conventionalcommits.org/fr/), en français, à l'impératif :

```
type(portée): ce que fait le commit
```

- `type` : `feat`, `fix`, `test`, `docs`, `ci`, `build`, `refactor`, `chore`.
- `portée` (facultative) : `collecte`, `parseur`, `stockage`, `themes`, `livraison`, `infra`…
- Exemples : `feat(collecte): lire le flux de Libération`,
  `fix(parseur): rejeter les articles sans date`.

Un commit correspond à un seul changement. Si le pourquoi n'est pas évident, on l'écrit dans le corps
du message.

## Pull requests

1. Avant de pousser : `bin/test` passe en local.
2. On ouvre une PR vers `main` qui dit ce qui change et comment le vérifier.
3. La CI doit être verte (`lint`, `test`, `image`). Une CI rouge bloque le merge.
4. Une autre personne de l'équipe relit, même rapidement : elle lit le diff, lance `bin/test`, et
   `bin/dev` si le comportement change.
5. **Qui merge** : l'auteur·e de la PR, une fois la revue approuvée, avec « Squash and merge ». Le
   titre de la PR, au format des commits, devient le message du commit sur `main`.
6. On supprime la branche après le merge.

## Règles du projet

- **Infrastructure en code** : rien de ce qui tourne n'est installé ni configuré à la main sans
  être décrit dans le dépôt (Dockerfile, `docker-compose.yml`, puis `infra/`).
- **Pas de secret dans le dépôt** : les mots de passe vont dans un `.env`, qui est ignoré par git.
- **Pas de données dans le dépôt** : `data/` est ignoré. On ne stocke jamais le texte intégral
  d'un article ni de donnée personnelle (voir [docs/cadrage.md](docs/cadrage.md)).
- **Nouvelle source** : on vérifie d'abord ses CGU, son `robots.txt` et son
  `/.well-known/tdmrep.json`. Ensuite, on l'ajoute à `sources.csv`, avec un flux enregistré dans
  `tests/fixtures/` (réduit à quelques articles) et un test.
- **Schéma de la base** : tout changement passe par une nouvelle migration
  (`src/gazette/migrations/NNN_sujet.sql`). On ne modifie jamais une migration déjà sur
  `main`, et on met à jour [docs/donnees.md](docs/donnees.md) dans la même PR.
- **Une CI rouge se répare en priorité.** On ne désactive pas un test pour la faire passer.

## Protection de `main` (à régler une fois, par l'admin du dépôt)

Dans GitHub : *Settings → Branches → Add branch protection rule* (ou *Rulesets*), sur `main` :

- *Require a pull request before merging*, avec 1 approbation ;
- *Require status checks to pass before merging*, en cochant `lint`, `test` et `image` ;
- *Do not allow bypassing the above settings* et *Block force pushes*.
