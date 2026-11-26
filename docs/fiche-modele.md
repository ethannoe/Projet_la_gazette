# Fiche modèle — regroupement des thèmes de presse

## Identification

- **Usage :** regrouper les titres et courts extraits de presse française publiés dans une
  fenêtre de 24 heures, afin de faire ressortir les sujets couverts par plusieurs journaux.
- **Type :** embeddings multilingues, regroupement non supervisé HDBSCAN, nommage TF-IDF.
- **Modèle d'embeddings :** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
  révision effective consignée avec chaque run.
- **Paramètres :** [`config/clustering.yaml`](../config/clustering.yaml), versions applicables
  consignées dans `versions_modele`.
- **Responsable de la décision :** l'équipe La Gazette. La CI réalise les contrôles et écrit
  les promotions après validation de l'environnement `production`.

## Données

Les entrées sont les titres et extraits courts des articles propres, les liens, les sources et
les dates. Elles viennent des flux RSS/Atom configurés dans `sources.csv`. Le pipeline n'a pas
besoin du texte intégral. Chaque run garde l'empreinte de ses entrées, sa fenêtre temporelle,
la révision exacte du modèle, les paramètres, les métriques, les rattachements et un échantillon
de dix articles destiné à la relecture.

## Évaluation et décision

Les seuils sont configurés dans [`config/evaluation.yaml`](../config/evaluation.yaml). Ils
portent sur la silhouette, la part de bruit, la taille du groupe le plus important et le nombre
de thèmes. La hausse de bruit ou la baisse de silhouette sur deux jours consécutifs demande une
revue. L'échantillon est déterministe ; une personne consigne `approuve` ou `recale`, son nom et
un commentaire avant qu'un run admissible puisse devenir candidat.

Un verdict `recale` ne modifie pas les thèmes consultés. Un verdict `revue` bloque la promotion.
Seul un run évalué, relu favorablement et sans dérive persistante peut être promu.

## Limites connues

- Il n'existe pas de vérité terrain annotée : silhouette et autres métriques décrivent la
  géométrie des vecteurs, pas la pertinence journalistique des thèmes.
- Les thèmes dépendent des flux disponibles et des formulations des titres ; deux sujets
  différents peuvent se rapprocher, et un sujet couvert par peu de sources peut rester du bruit.
- Le nommage TF-IDF peut produire des mots-clés peu lisibles ou des noms incomplets.
- Les seuils sont des garde-fous initiaux ; l'équipe doit les ajuster sur plusieurs relectures.
- Pas de recherche automatique d'hyperparamètres et pas d'expérience A/B.

## Promotion et retour arrière

Le registre PostgreSQL `versions_modele` répond à « quelle configuration est en production ? ».
Le circuit de PR, l'évaluation CI et les commandes de promotion/retour arrière sont décrits dans
[`mlops.md`](mlops.md). Toute promotion ou restauration garde la version précédente, l'heure et
l'identité déclarée de l'opérateur dans `historique_promotions`.
