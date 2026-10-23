# Données : contrat et dictionnaire

Ce que la gazette stocke, champ par champ, et les engagements qui vont avec. À tenir à
jour à chaque migration ou nouveau champ.

## Le contrat de données

**Ce qu'on stocke**, c'est-à-dire seulement ce qu'on a le droit de republier : titre,
extrait court (300 caractères au plus dans `articles_propres`), lien, date, source, rubrique.

**Ce qu'on ne stocke jamais** :
- le texte intégral (`content:encoded`, `<content>` Atom) ;
- les images et médias ;
- les auteurs ;
- les commentaires ;
- aucune donnée personnelle.

Les noms qui apparaissent dans les titres sont ceux de l'actualité publiée par les journaux.

**Le schéma** : les tables et fichiers décrits plus bas, créés par des migrations
versionnées. Un changement de schéma passe par une nouvelle migration et une mise à jour de
ce document dans la même pull request.

**La fraîcheur** :
- chaque source est interrogée toutes les 30 min ;
- un article publié est dans `articles_propres` moins d'une heure plus tard ;
- le contrôle `C04_fraicheur_collecte` alerte si une source n'a pas réussi de collecte depuis
  2 h, et `C08` alerte s'il n'y a aucun article propre des dernières 24 h.

**La qualité** : les règles d'exclusion et les contrôles sont décrits dans
[qualite.md](qualite.md). Chaque rejet garde sa règle, et un rapport est produit à chaque
passage.

**La rétention** : `python -m gazette purger`, appliquée aussi à chaque passage.

| Donnée | Durée | Après |
|---|---|---|
| Items bruts (`articles_bruts/`) | 90 jours | Supprimés : de quoi rejouer le nettoyage sur un trimestre |
| `rejets` | 90 jours | Supprimés, comme le brut dont ils viennent |
| `articles_propres` | 1 an (selon `publie_le`) | Supprimés |
| `collectes`, `controles`, `rapports/` | 1 an | Supprimés |
| Éditions HTML (à partir du TD 7) | 1 mois en ligne | Déplacées vers un stockage froid (archive compressée hors du serveur web), gardées 1 an |

**La traçabilité** : à partir d'un article propre ou rejeté, on retrouve son item brut
(`articles_bruts/<source_id>/<item_id>.json`, qui contient le `payload` tel que reçu) et sa
source (table `sources`) :

```bash
docker compose run --rm collecteur tracer <item_id ou lien>
```

Après 90 jours, l'item brut est purgé : la traçabilité s'arrête alors à la source et au lien.

## Items bruts : `articles_bruts/<source>/<id>.json`

Un fichier par article et par source, écrit au premier passage qui le voit et plus
jamais réécrit : la clé naturelle est `(source, lien)`, et `id` en est dérivé.
C'est la couche « telle que reçue » : on n'y filtre rien (titres vides, dates
manquantes, programme TV…), le tri se fera au nettoyage (TD 4).

| Champ | Type | Description |
|---|---|---|
| `id` | texte, 16 caractères hexadécimaux | `sha256(source + "\n" + lien)` tronqué : identifiant stable de la clé `(source, lien)`, et nom du fichier |
| `source` | texte | `id` de la source dans `sources.csv` (ex. `lemonde`) |
| `lien` | URL | Lien de l'article, normalisé : sans fragment (`#…`), sans paramètres de suivi (`utm_*`, `xtor`), domaine en minuscules. Un item sans lien est rejeté |
| `titre` | texte | Titre sans balises HTML ni entités ; peut être vide |
| `resume` | texte | Extrait sans HTML, tronqué à 500 caractères. Vide si le flux n'a pas de `<description>` ou de `<summary>`. Jamais le texte intégral |
| `publie_le` | date ISO 8601 en UTC, ou `null` | `pubDate` / `published` (ou `dc:date`), sinon `updated`. `null` si absente ou illisible : la valeur reçue reste dans `payload` |
| `recupere_le` | date ISO 8601 en UTC | Heure du passage qui a écrit l'item pour la première fois |
| `rubrique` | texte ou `null` | Première `<category>` du flux, sinon premier segment parlant du chemin de l'URL (`/societe/…` → `societe`), en sautant les dates, le titre de l'article et `article` |
| `payload` | objet | Les champs autorisés tels que reçus, avant nettoyage : `id` (le `guid` ou l'`id` Atom), `title`, `link`, `published`, `updated`, `summary` (1 000 caractères au plus), `tags` |

Exemple :

```json
{
  "id": "9c1e0f3b2a7d4e85",
  "source": "lemonde",
  "lien": "https://www.lemonde.fr/societe/article/2026/10/22/..._6798586_3224.html",
  "titre": "Interpellés devant leurs lycées début octobre, des élèves racontent…",
  "resume": "Leïla, Inès et Nino ont 17, 16 et 15 ans. Début octobre, …",
  "publie_le": "2026-10-22T07:45:09+00:00",
  "recupere_le": "2026-10-22T09:46:23+00:00",
  "rubrique": "societe",
  "payload": {
    "id": "https://www.lemonde.fr/societe/article/2026/10/22/..._6798586_3224.html",
    "title": "Interpellés devant leurs lycées début octobre, …",
    "link": "https://www.lemonde.fr/societe/article/2026/10/22/..._6798586_3224.html",
    "published": "Thu, 22 Oct 2026 09:45:09 +0200",
    "summary": "Leïla, Inès et Nino ont 17, 16 et 15 ans. …"
  }
}
```

### D'où vient chaque champ : RSS 2.0 et Atom

| Notre champ | RSS 2.0 | Atom |
|---|---|---|
| `lien` | `<link>` | `<link rel="alternate" href="…">` |
| `titre` | `<title>` | `<title>` |
| `resume` | `<description>` | `<summary>` |
| `publie_le` | `<pubDate>` ou `<dc:date>` | `<published>`, sinon `<updated>` |
| `rubrique` | `<category>` | `<category term="…">` |
| `payload.id` | `<guid>` | `<id>` |
| *(ignoré)* | `<content:encoded>`, `<media:*>`, `<author>` | `<content>`, `<author>` |

## Base PostgreSQL

Le schéma est créé par des migrations versionnées
([src/gazette/migrations/](../src/gazette/migrations/)), appliquées dans l'ordre au
début de chaque passage (`python -m gazette migrer` pour les lancer seules).

### Table `sources` : l'état de chaque source

Une ligne par source de `sources.csv`, recopiée à chaque passage. L'état (colonnes
après `url_flux`) n'est jamais écrasé par cette copie, sauf si l'adresse du flux
change : la source repart alors de zéro.

| Colonne | Type | Description |
|---|---|---|
| `id` | text, clé primaire | `id` dans `sources.csv` |
| `nom` | text | Nom affiché (ex. « Le Monde ») |
| `type` | text, `PQN` ou `PQR` | Presse nationale ou régionale |
| `url_flux` | text | Adresse du flux RSS ou Atom |
| `actif` | boolean | `false` = en sommeil : la source n'est plus interrogée |
| `derniere_reussite` | timestamptz | Dernier passage réussi (200 ou 304) |
| `echecs_consecutifs` | integer | Remis à 0 à chaque réussite ; à 3, la source s'endort |
| `etag` | text | Dernier `ETag` reçu, renvoyé en `If-None-Match` |
| `last_modified` | text | Dernier `Last-Modified` reçu, renvoyé en `If-Modified-Since` |
| `derniere_erreur` | text | Message du dernier échec (ex. `HTTP 403`) ; vidé à la réussite suivante |
| `mise_en_sommeil_le` | timestamptz | Date de la dernière mise en sommeil |

### Table `collectes` : une ligne par source et par passage

Les compteurs de la collecte, base des tableaux de bord du TD 8.

| Colonne | Type | Description |
|---|---|---|
| `id` | bigint, clé primaire | |
| `source_id` | text → `sources.id` | |
| `debut` | timestamptz | Début de la requête |
| `duree_ms` | integer | Durée totale : requêtes, nouveaux essais et écriture |
| `statut` | text | `ok` (200), `inchange` (304) ou `echec` |
| `http_status` | integer | Dernier code HTTP reçu (`null` si pas de réponse) |
| `tentatives` | integer | Nombre de requêtes (1 + nouveaux essais) |
| `recus` | integer | Items du flux qui ont un lien |
| `ecrits` | integer | Items nouveaux, écrits dans `articles_bruts/` |
| `ignores` | integer | Items déjà connus (`recus - ecrits`) |
| `erreur` | text | Message d'erreur si `echec` |
| `mise_en_sommeil` | boolean | `true` si ce passage a endormi la source |

### Table `articles_propres` : la matière de la gazette

Les articles qui ont passé toutes les règles (migration `003_articles_propres.sql`).

| Colonne | Type | Description |
|---|---|---|
| `item_id` | text, clé primaire | Le même `id` que l'item brut : `articles_bruts/<source_id>/<item_id>.json` |
| `source_id` | text → `sources.id` | |
| `lien` | text | Lien normalisé ; `(source_id, lien)` est unique |
| `titre` | text | Normalisé (HTML, entités, encodage, espaces) |
| `extrait` | text | Normalisé, 300 caractères au plus |
| `publie_le` | timestamptz | En UTC, jamais vide, jamais dans le futur |
| `recupere_le` | timestamptz | Premier passage de collecte qui l'a vu |
| `rubrique` | text | Peut être vide |
| `titre_cle` | text | Titre sans casse, accents ni ponctuation : sert au dédoublonnage |
| `passage` | timestamptz | Le passage de nettoyage qui l'a gardé |

### Table `rejets` : les items écartés, avec leur raison

| Colonne | Type | Description |
|---|---|---|
| `item_id` | text, clé primaire | Comme dans `articles_propres` |
| `source_id` | text → `sources.id` | |
| `regle` | text | La règle qui l'a écarté, ex. `R02_horoscope` (voir [qualite.md](qualite.md)) |
| `detail` | text | Ce qui l'a déclenchée : le motif trouvé, ou l'article gardé à sa place pour un doublon |
| `titre`, `lien` | text | Pour lire le rapport sans rouvrir le brut |
| `passage` | timestamptz | Le passage de nettoyage qui l'a écarté |

### Table `controles` : les métriques de qualité

Une ligne par contrôle et par passage (migration `004_controles.sql`).

| Colonne | Type | Description |
|---|---|---|
| `passage` | timestamptz | |
| `controle` | text | Ex. `C01_aucune_date_future` |
| `ok` | boolean | Le fait est-il vrai ? |
| `valeur`, `seuil` | double precision | La mesure et sa limite |
| `detail` | text | Ex. les sources concernées |

### Table `schema_migrations`

| Colonne | Type | Description |
|---|---|---|
| `version` | text, clé primaire | Nom du fichier de migration sans `.sql` (ex. `001_sources`) |
| `appliquee_le` | timestamptz | |
