# Les flux de nos sources : ce qu'ils publient, leurs pièges

Relevé du 22/10/2026 (une requête par flux, avec notre User-Agent). À refaire de
temps en temps : les éditeurs changent leurs flux sans prévenir.

## Ce que renvoie chaque source

| Source | Réponse | Format | Items | `ETag` / `Last-Modified` | `<category>` | Texte intégral | `tdmrep.json` |
|---|---|---|---|---|---|---|---|
| Le Monde | 200 | RSS 2.0 | 16 | aucun (`max-age=0`) | non | non | absent (404) |
| Le Figaro | 200 | RSS 2.0 | 19 | aucun (`max-age=600`) | oui (« Société ») | **oui**, `content:encoded` | **`tdm-reservation: 1`** |
| Libération | 200 | RSS 2.0 | 50 | `ETag` faible + `Last-Modified` | non | non | refusé (403) |
| La Croix | 200, après redirection | RSS 2.0 | 50 | `ETag` + `Last-Modified` | non | non | absent (404) |
| Les Échos | **403** | – | – | – | – | – | – |
| Ouest-France | 200, après redirection | RSS 2.0 | 10 | aucun (`no-store`) | non | **oui**, `content:encoded` | **`tdm-reservation: 1`** |
| Le Télégramme | **403** (défi Cloudflare) | – | – | – | – | – | – |
| Sud Ouest | 200 | RSS 2.0 | 20 | aucun (`max-age=600`) | non | non | **`tdm-reservation: 1`** |
| Le Progrès | 200 | RSS 2.0 | 20 | aucun | oui, mais géographiques (« Rhône ») | non | absent (404) |

## Les pièges, et ce que fait le code

1. **Deux formats, deux vocabulaires.** RSS 2.0 dit `pubDate`, `description` et `guid` ;
   Atom dit `published` / `updated`, `summary` et `id`. Nos 7 flux lisibles sont tous en
   RSS 2.0 aujourd'hui, mais un flux peut passer en Atom. On s'appuie sur feedparser, un
   parseur éprouvé, et un test vérifie un flux Atom (`tests/fixtures/atom.xml`).
2. **Les dates arrivent dans tous les formats** : `+0200`, `+0000`, `GMT`, sans jour de
   la semaine, en ISO 8601 dans `dc:date`… Tout est converti en UTC. Une date illisible
   donne `publie_le: null`, et la valeur reçue reste dans `payload`
   (`tests/fixtures/latin1.xml`).
3. **Les encodages** : tous nos flux sont en UTF-8, mais un flux régional en ISO-8859-1
   n'est pas rare. feedparser lit la déclaration XML, et un test le vérifie.
4. **Le texte intégral se cache.** Le Figaro et Ouest-France envoient l'article entier
   dans `content:encoded`. Piège de feedparser : sans `<description>`, `entry.summary`
   renvoie ce texte intégral. On ne lit que `summary_detail`, qui n'existe que pour un
   vrai extrait.
5. **feedparser invente des champs.** Si `updated` est absent, il renvoie `published` à
   sa place, et inversement. Le payload est lu sans passer par ce mécanisme, pour rester
   « tel que reçu ».
6. **Des paramètres de suivi dans les liens.** Ouest-France ajoute
   `?utm_source=fluxpublicactu&utm_medium=fluxrss…`. S'ils changent, le même article
   aurait l'air nouveau. On les retire avant de calculer la clé `(source, lien)`.
7. **Des adresses qui redirigent.** La Croix (`/RSS` → `/feeds/rss/site.xml`) et
   Ouest-France (`/rss-en-continu.xml` → `/rss/une`) : `sources.csv` pointe maintenant
   vers l'adresse finale, ce qui évite une requête de plus à chaque passage.
8. **Des pages HTML à la place du flux.** Une page de consentement ou un défi
   anti-robot peut être servi avec un code 200. Un document qui n'est ni RSS ni Atom
   compte comme un échec, sinon une source bloquée passerait pour un flux vide.
9. **Des sources qui nous bloquent.** Les Échos et Le Télégramme répondent 403 à notre
   User-Agent. On ne se fait pas passer pour un navigateur : elles s'endorment au bout de
   3 échecs. **À décider en équipe** : demander l'accès, trouver un autre flux, ou les
   remplacer (cf. risques du cadrage).
10. **Les requêtes conditionnelles sont rares et partielles.** Seuls Libération et La
    Croix envoient un `ETag` ou un `Last-Modified`. Libération ignore `If-None-Match`
    mais répond 304 à `If-Modified-Since`. On envoie donc les deux.
11. **Des rubriques hétérogènes.** Seuls Le Figaro et Le Progrès ont des `<category>`,
    et celles du Progrès sont des lieux. Ailleurs, la rubrique vient de l'URL. À revoir
    au nettoyage (TD 4).
12. **Pas que de l'actualité.** Le flux « une » d'Ouest-France contient des liens vers
    `programmetv.ouest-france.fr` : un premier candidat pour `docs/qualite.md`.

## Conditions des éditeurs

- **Le Figaro, Ouest-France et Sud Ouest déclarent `tdm-reservation: 1`** dans
  `/.well-known/tdmrep.json`, c'est-à-dire qu'ils s'opposent à la fouille de textes
  (art. L.122-5-3 du CPI). Le cadrage note que regrouper des titres par thèmes en est
  une.
- Le flux du Monde précise que son usage est « réservé à un usage strictement personnel,
  non professionnel et non collectif ».
- Pour retirer une source, il suffit de supprimer sa ligne de `sources.csv` : elle n'est
  plus collectée au passage suivant, et son historique reste en base.

## Politesse

- Un User-Agent qui dit qui nous sommes : `LaGazetteBot/<version> (+<url du dépôt>)`.
- `If-None-Match` et `If-Modified-Since` dès que la source envoie un `ETag` ou un
  `Last-Modified`.
- Des timeouts : 5 s pour se connecter, 20 s pour lire.
- Une requête par source et par passage, les sources l'une après l'autre, jamais en
  parallèle.
- Un passage toutes les 30 min, et jamais deux requêtes à une même source à moins de
  10 min d'écart, même si l'orchestrateur rattrape des passages manqués.
- Sur un 429 ou un 5xx : 3 tentatives au plus, avec une attente croissante (2 s, puis
  4 s) ou la durée demandée par `Retry-After`.
- Sur un 404, un 403 ou un flux cassé : pas de nouvel essai. Au troisième échec de
  suite, la source s'endort.
