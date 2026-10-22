# Orchestration : la collecte tourne seule

## Le choix : Prefect, auto-hébergé

C'est le choix du [cadrage](cadrage.md). Ce qu'il nous apporte pour la collecte :

- **La planification** : un passage toutes les 30 min, sans personne pour appuyer.
- **L'historique** : chaque passage, son état, sa durée et ses journaux sont visibles dans
  l'interface (http://localhost:4200). On voit ce qui a échoué et quand.
- **La reprise** : un passage qui plante en entier (base injoignable…) est relancé une
  fois 5 min plus tard. Les erreurs d'une source (503, timeout) sont réessayées par le
  collecteur lui-même, avec une attente croissante.
- **Pas de rafale** : un seul passage à la fois. Si la machine sort de veille avec des
  passages en retard, ils s'enchaînent, mais seul le premier interroge les éditeurs : une
  source n'est jamais interrogée deux fois en moins de 10 min (`GAZETTE_DELAI_MIN`), donc
  les suivants sont vides.
  On n'utilise pas la limite globale de Prefect (`global_limit`), testée puis écartée :
  un passage resté bloqué après un redémarrage du conteneur gardait la place, et Prefect
  annulait tous les passages suivants.

Écartés : **cron** (ni historique, ni relance, ni interface : il faudrait tout
reconstruire), **Airflow** (scheduler, serveur web et base en plus, trop lourd pour
9 flux), **GitHub Actions** (l'horaire planifié n'est pas garanti, et ça ne tournera pas
sur l'infrastructure fournie).

Le collecteur ne dépend pas de Prefect : `python -m gazette collecter` fait un passage
complet sans lui. Changer d'orchestrateur ne toucherait que `src/gazette/flows.py`.

## Comment c'est décrit

Tout est dans [docker-compose.yml](../docker-compose.yml) :

| Service | Rôle |
|---|---|
| `db` | PostgreSQL : tables `sources` et `collectes` |
| `prefect` | Serveur Prefect : planning, historique, interface sur le port 4200 |
| `collecteur` | `python -m gazette planifier` : enregistre le déploiement `collecte/planifiee` et exécute les passages prévus |

Tous les services ont `restart: unless-stopped` : ils repartent seuls après un
redémarrage de Docker, tant qu'on ne les a pas arrêtés avec `docker compose down`.

## Au quotidien

```bash
bin/dev                                                # tout démarrer + un premier passage
docker compose logs -f collecteur                      # suivre les journaux (JSON)
docker compose run --rm collecteur etat                # état des sources, articles par source
docker compose run --rm collecteur reveiller lemonde   # sortir une source du sommeil
docker compose down                                    # tout arrêter (les données restent)
```

- **Changer la fréquence** : `GAZETTE_INTERVALLE_MIN=60 bin/dev`. Le délai minimal entre
  deux requêtes à une même source se règle avec `GAZETTE_DELAI_MIN` (10 min par défaut).
- **Lancer un passage tout de suite** : dans l'interface, sur le déploiement
  `collecte/planifiee`, cliquer sur *Run*. Ou bien, sans Prefect :
  `docker compose run --rm collecteur collecter`.

## La laisser tourner jusqu'à la prochaine séance

Sur la machine d'un·e membre, en attendant l'infrastructure fournie :

1. `bin/dev`, puis vérifier dans l'interface que le déploiement `collecte/planifiee`
   existe et qu'un prochain passage est prévu.
2. Empêcher la mise en veille : branché sur secteur, et sur macOS `caffeinate -dims`
   dans un terminal laissé ouvert. Docker Desktop doit rester lancé.
3. Chaque jour, `docker compose run --rm collecteur etat` : une source en `SOMMEIL` doit
   être vue et traitée (réveil, nouvelle adresse, ou retrait de `sources.csv`).
