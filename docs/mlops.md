# MLOps : les thèmes du jour

À partir des articles propres des dernières 24 h, le pipeline :
1. vectorise chaque article ;
2. regroupe les articles proches ;
3. nomme chaque groupe ;
4. stocke les thèmes avec les articles qui s'y rattachent.

**Chaque exécution est un run tracé** : ses données, ses paramètres, ses métriques et ses
artefacts. On sait donc toujours quel run a produit les thèmes qui sont en base.

```
articles_propres (24 h) ─▶ embeddings (cache) ─▶ HDBSCAN ─▶ mots-clés ─▶ themes + articles_themes
                                                                    └─▶ runs (traçage) + runs/<run_id>/
```

Le code : `src/gazette/embeddings.py` et `src/gazette/themes.py`. Les paramètres :
[`config/clustering.yaml`](../config/clustering.yaml).

## Où regarder

| Je veux… | Où |
|---|---|
| Les thèmes du jour | `docker compose run --rm collecteur themes-du-jour`, ou la vue SQL `themes_du_jour` |
| Les derniers runs (données, paramètres, métriques) | `docker compose run --rm collecteur runs` |
| Le détail d'un run | Table `runs` (requête ci-dessous) et dossier `runs/<run_id>/` |
| Les thèmes d'un run précis | `SELECT * FROM themes WHERE run_id = '…'` |
| Les articles d'un thème | `articles_themes JOIN articles_propres USING (item_id)` |
| Le run dans l'orchestrateur | Prefect (http://localhost:4200) : tâche `themes`, artifact `themes-du-jour` |

```sql
-- Les derniers runs, avec leur entrée, leurs paramètres et leurs métriques
SELECT run_id, declencheur, statut, nb_articles, hash_entree, modele_version,
       hash_parametres, code_version, metriques
FROM runs ORDER BY debut DESC LIMIT 5;
```

Chaque run écrit dans `runs/<run_id>/` :
- `parametres.yaml` : la configuration exacte du run ;
- `metriques.json` ;
- `themes.json` : les thèmes nommés, avec les titres de leurs articles ;
- `affectations.json` : le thème de chaque article, et la force du rattachement.

## Le modèle d'embeddings

| | |
|---|---|
| Modèle | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Version tracée | Révision Hugging Face `faf4aa4225822f3bc6376869cb1164e8e3feedd0` (dépôt `Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`, ONNX quantifié) |
| Bibliothèque | fastembed 0.9.0 (ONNX Runtime, **sans PyTorch**), version figée dans `pyproject.toml` |
| Entrée | « titre. extrait » (extrait de 300 caractères au plus) |
| Sortie | Un vecteur de 384 nombres |
| Coût | 220 Mo téléchargés une fois dans `modeles/`, environ 8 s pour 336 articles sur le CPU du Mac. Pas de clé, pas d'API payante |

**Pourquoi ce modèle** : il est multilingue (les titres sont en français), assez léger pour un
CPU, et entraîné pour rapprocher des phrases de même sens. Sur nos 10 articles de test,
deux articles du même sujet se ressemblent nettement plus que deux articles de sujets
différents (`test_vrai_modele_sur_dix_articles`, lancé aussi en CI).

**Le cache** : la table `embeddings` garde un vecteur par article et par `modèle@révision`.
Un run ne calcule que les nouveaux articles : rejouer une fenêtre déjà vue prend 0,2 s. Si le
modèle change de révision, la clé change, et tout est recalculé.

## Le regroupement : HDBSCAN

Les paramètres, dans `config/clustering.yaml` :
- `min_cluster_size: 3` : un thème regroupe au moins 3 articles ;
- `min_samples: 2` ;
- `cluster_selection_method: leaf`.

Les vecteurs sont normalisés : la distance euclidienne suit alors la distance cosinus.

**Les trois approches, essayées sur les 336 articles propres du 23/10/2026 :**

| Approche | Résultat | Ce qu'on en retient |
|---|---|---|
| **Il faut donner le nombre de groupes** : k-means, k choisi par la silhouette | k = 55, 0 % de bruit, silhouette 0,09 | Chaque article est forcé dans un groupe : une critique de livre se retrouve avec l'OTAN et la diplomatie. Et le bon k change chaque jour |
| **Il trouve le nombre et accepte du bruit** : HDBSCAN, sélection `eom` | 20 thèmes, 57 % de bruit, silhouette 0,22 | Des thèmes cohérents, mais un seul thème de 47 articles pour toutes les manifestations |
| … même famille, sélection `leaf` (**retenu**) | 26 thèmes, 63 % de bruit, silhouette 0,28 | Le gros thème se scinde en vrais sous-sujets (manifestation à Toulouse, interdictions, Macron et les lycéens) |
| … variante sans bruit : agglomératif, seuil cosinus 0,45 | 19 thèmes, 69 % de bruit (groupes de moins de 3), silhouette 0,30 | Proche, mais un seuil de distance de plus à régler |
| **Il enchaîne toute la chaîne** : BERTopic (UMAP + HDBSCAN + c-TF-IDF) | 44 thèmes, 19 % de bruit, silhouette 0,13 | Moins de bruit, mais des thèmes plus lâches (« maison · fleurs · Monet · participation »). Il tire PyTorch, UMAP et numba, et UMAP est aléatoire, donc moins reproductible |

**Pourquoi HDBSCAN :**
- le nombre de thèmes change chaque jour, donc il ne faut pas avoir à le donner ;
- la plupart des articles de la presse régionale sont uniques : il vaut mieux les laisser en
  bruit que les forcer dans un thème ;
- il est déterministe : même entrée, mêmes thèmes ;
- il est déjà dans scikit-learn, sans dépendance de plus.

Le bruit est élevé (environ 65 %), et c'est attendu : un thème du jour est une histoire
couverte par plusieurs articles.

## Le nommage

Pour chaque thème, on garde les **mots les plus discriminants** : un TF-IDF où chaque thème
est un document, et où les articles isolés forment un document de fond. Les mots communs à
toute l'actualité du jour ne nomment donc aucun thème. Les mots trop courants ou propres à
la presse sont écartés ([`config/mots_vides.txt`](../config/mots_vides.txt)).

Les 3 premiers mots forment le nom (« Austen · Tempête · Électricité »), et les 8 premiers
sont gardés dans `mots_cles`. Les bigrammes (`ngram_max: 2`) ont été essayés : ils donnent de
beaux noms (« tempête austen »), mais aussi des doublons (« championne monde · peres
jepchirchir »).

## Le traçage des runs

**Choix : une table `runs` dans PostgreSQL**, plutôt qu'un outil comme MLflow :
- Les thèmes et le run qui les a produits sont dans la même base, reliés par une clé
  étrangère : « quel run a produit les thèmes en base ? » se résout par une jointure.
- Pas de service de plus sur la machine qui fait tourner le pipeline.
- Prefect montre déjà chaque exécution et ses artifacts.
- Les tableaux de bord du TD 8 liront PostgreSQL.

Si on comparait un jour beaucoup de modèles entraînés, MLflow (et son registre de modèles)
deviendrait intéressant.

**Ce que chaque run enregistre** (table `runs`) :

| | Colonnes |
|---|---|
| Données | `fenetre_debut`, `fenetre_fin`, `nb_articles`, `hash_entree` (empreinte des ids et des textes vectorisés) |
| Modèle | `modele`, `modele_version` (révision Hugging Face) |
| Paramètres | `algorithme`, `parametres` (tout `clustering.yaml`, en JSON), `hash_parametres` |
| Code | `code_version` : le commit git de l'image, suivi de `-modifie` si le code n'était pas commité |
| Métriques | `metriques` : `nb_themes`, `taille_mediane`, `taille_max`, `part_bruit`, `silhouette`, `embeddings_calcules`, `duree_s` |
| Artefacts | `artefacts` : les chemins des fichiers de `runs/<run_id>/` ; les thèmes dans `themes`, les rattachements dans `articles_themes` |
| Exécution | `debut`, `duree_s`, `declencheur` (`pipeline` ou `manuel`), `statut` (`en_cours`, `ok`, `echec`), `erreur` |

Le run est inscrit **avant** de commencer (`en_cours`), puis mis à jour : un run qui plante
reste visible en `echec`, avec son erreur.

**Rejouer un run** : même fenêtre, mêmes paramètres et même modèle donnent les mêmes thèmes.

```bash
docker compose run --rm collecteur themes --fin 2026-10-23T12:53:57+00:00
```

On le vérifie en comparant `hash_entree`, `hash_parametres` et `modele_version` des deux runs
(voir le rejeu du 23/10 ci-dessous).

**Quand** : le pipeline lance le run une fois par jour, au premier passage après 6 h 30
(heure de Paris), juste après le nettoyage, les contrôles et le rapport. La commande `themes`
permet d'en lancer un à la main, tracé avec le déclencheur `manuel`.

## Les thèmes du jour : 23/10/2026

**Le run qui les a produits** : `20261023T125357Z-5a37a6`, lancé par le pipeline (passage
Prefect de 12 h 53 UTC).

| | |
|---|---|
| Fenêtre | 22/10 12 h 53 → 23/10 12 h 53 UTC, 340 articles, `hash_entree` `4fad19a5bca3cfc2` |
| Modèle | révision `faf4aa42…` |
| Paramètres | `hash_parametres` `b17eb02193fcbe96` (HDBSCAN, min_cluster_size 3, min_samples 2, leaf) |
| Métriques | 25 thèmes, taille médiane 4, plus gros thème 12, 64,7 % de bruit, silhouette 0,298 |
| Code | `51cd81c-modifie` (lancé avant le commit du TD 5) |

**Rejeu** : `20261023T125528Z-a461bd`, lancé à la main sur la même fenêtre, avec le code commité
`b45a816`. Il a la même `hash_entree`, la même `hash_parametres` et la même révision du modèle.
On obtient **les mêmes 25 thèmes, à l'identique**, et la même silhouette. Ses 340 vecteurs
venaient tous du cache : il a pris 0,2 s. C'est ce run que montre la vue `themes_du_jour`.

| # | Thème | Articles | Sources | Autres mots-clés |
|---|---|---|---|---|
| 0 | Trappes · Yvelines · Antiterroriste | 12 | 6 | tiré, fusillade, interpellé, verrière |
| 1 | Austen · Tempête · Électricité | 11 | 6 | départements, orange, vigilance, sncf |
| 2 | Pouvoir · Émeutes · Dominique | 7 | 4 | france, état, bataille, régime |
| 3 | Dette · Taux · Emprunt | 7 | 5 | note, souveraine, agence |
| 4 | Parcours · Tour · Étape | 6 | 4 | dévoilé, france, coureurs, kilomètres |
| 5 | Drogue · Trafic · Longtemps | 6 | 2 | narcotrafic, nourrices, toulouse, cocaïne |
| 6 | Parcours · Manifestation · Éloigné | 6 | 2 | toulouse, syndicats, préfecture |
| 7 | Accident · Voiture · Mirage | 5 | 3 | conducteur, nancy, avion |
| 8 | Accident · Automobiliste · Homme | 5 | 2 | nuit, jeune, route, blessé |
| 9 | Beaucoup · Lycéennes · Macron | 5 | 3 | organisations, mobilisation, manifestations |
| 10 | Poutine · Ukraine · Vladimir | 5 | 3 | trump, donald, russie |
| 11 | Préfecture · Déclaration · Interdite | 4 | 3 | lorient, lyon, manifestation, interdit |
| 12 | Eau · Foin · Pâtures | 4 | 3 | sécheresse, chanvre, climat |
| 13 | Budget · Rejeté · Assemblée | 4 | 3 | sénat, sécurité, sociale, députés |
| 14 | Hoffenheim · Europa · Ligue | 3 | 1 | bad, gones, phase |
| 15 | Bloc · Central · Partis | 3 | 1 | insoumise, matignon, électeurs |
| 16 | Commerçants · Commerçant · Parisiens | 3 | 3 | protéger, manifestations, police |
| 17 | Famille · Enfants · Proches | 3 | 3 | expulsion, logement, judiciaire |
| 18 | Attaque · Armée · Cisjordanie | 3 | 3 | bouclage, israéliens |
| 19 | Commerçants · Argentière · Dupin | 3 | 2 | fraîche, frères, peinture |
| 20 | Virus · Shamonda · Humain | 3 | 2 | décédé, bovins, contracté |
| 21 | Fibre · Gaudens · Liquidation | 3 | 2 | excellence, usine, reprise |
| 22 | Patients · Cure · Maladie | 3 | 3 | obésité, thérapeutique, médecins |
| 23 | Nationalistes · Religieux · Sécuritaires | 3 | 2 | cisjordanie, israéliens, israël |
| 24 | Championne · Monde · Athlétisme | 3 | 2 | jepchirchir, marathon, suspendue |

## Relecture des thèmes (matière du TD 6)

### Journée 1 : 23/10/2026

**Ce qui est bon :**
- Les grandes histoires du jour sont là, couvertes par plusieurs sources : la fusillade de
  Trappes (6 sources), la tempête Austen (6 sources), le budget de la Sécu, l'Ukraine, le
  Tour de France 2027.
- Les noms sont compréhensibles quand les mots-clés sont des noms propres ou des faits
  (« Austen · Tempête », « Poutine · Ukraine », « Fibre · Gaudens · Liquidation »).

**Ce qui est absurde ou discutable :**
- **Une même histoire coupée en plusieurs thèmes** :
  - les manifestations du 24 octobre se retrouvent dans 5 thèmes (6, 9, 11, 15, 16) ;
  - la Cisjordanie dans 2 thèmes (18 et 23) ;
  - les accidents de la route dans 2 thèmes (7 et 8).
- **Des thèmes qui n'en sont pas** :
  - « Commerçants · Argentière · Dupin » mélange des fromageries, une peinture et un
    sélectionné de Sainte-Foy-l'Argentière ;
  - « Famille · Enfants · Proches » est trop vague.
- **Des noms bancals** : un prénom (« Dominique »), un mot vide qui passe (« Beaucoup »,
  « Longtemps »), ou un doublon (« Commerçants · Commerçant »).

**Hypothèses :**
- La sélection `leaf` découpe trop finement les grandes histoires.
- Un `min_cluster_size` de 3 laisse passer des groupes de hasard.
- Le nommage voit les mots, pas leur sens : il ne fusionne pas le singulier et le pluriel,
  et un prénom fréquent dans 3 articles sort en tête.
- Les mots vides ne couvrent pas les adverbes.

### Journée 2 : à relire

*(Relire les thèmes du prochain run quotidien avec `themes-du-jour`, et noter ici ce qui est
bon, ce qui est absurde, et une hypothèse.)*

### La question du TD 6

Qu'est-ce qu'un « bon » regroupement ? Silhouette, part de bruit, cohérence lue à la main,
nombre de sources par thème… Les métriques de chaque run sont dans la table `runs`, pour
comparer.
