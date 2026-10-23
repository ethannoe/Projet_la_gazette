# Qualité des données

Entre le brut et la gazette, il y a le tri. Ce document décrit :
- ce qui pollue (relevé sur nos vraies données) ;
- les règles qui l'écartent ;
- les contrôles qui vérifient les données après chaque passage ;
- comment lire le rapport de qualité ;
- le journal des ajustements de règles.

Le code : `src/gazette/normalisation.py`, `src/gazette/regles.py` et `src/gazette/controles.py`.
Les motifs et les seuils sont dans [`regles.toml`](../regles.toml).

## 1. Ce qui pollue : nos dix pollueurs

Relevé du 22/10/2026 sur les 330 premiers items collectés. Chacun est écarté par une
règle, et un test le vérifie (`tests/test_regles.py`, fixture `tests/fixtures/qualite.json`).

| # | Source | `id` | Titre | Pourquoi l'écarter | Règle |
|---|---|---|---|---|---|
| 1 | ouestfrance | `37be69ff6d380e81` | « Je suis dégoûtée » : Angèle annule en dernière minute sa participation aux « NRJ Music Awards »… | Programme TV et people, sur le site télé d'Ouest-France | `R03_programme_tv` |
| 2 | sudouest | `e6f5a2a8d7f1c179` | La météo à Bordeaux du jeudi 22 octobre 2026 | Bulletin météo quotidien : du service, pas de l'actualité | `R05_meteo_service` |
| 3 | ladepeche | `4016ae38fa2f070c` | CARTE. Prix des carburants : tarifs, stations… les moins chères… | Page de service mise à jour en continu | `R06_page_service` |
| 4 | ladepeche | `fcc3d4cde05f6a60` | La Dépêche du Midi lance son espace jeux : à vos neurones, prêts, jouez ! | Jeux, et autopromotion du journal | `R04_jeux` |
| 5 | latribune | `e2241d1dc9474ecd` | Territoires Awards : BFM La Tribune récompense l'excellence entreprenariale | Événement organisé par le média lui-même | `R08_autopromo` |
| 6 | sudouest | `67657ed3cf15ef57` | DIRECT VIDÉO. UBB Espoirs : Suivez la rencontre… en live sur TV7 | Retransmission vidéo, pas un article | `R07_media_seul` |
| 7 | liberation | `6e1bd0cea9210c54` | EN IMAGES - La jeunesse d'Europe se révolte | Diaporama : on ne garde pas les images | `R07_media_seul` |
| 8 | lacroix | `2164cad3306cf9b0` | Feu, foi, baptême. Commentaire de l'Évangile du jeudi 22 octobre | Rendez-vous quotidien, pas de l'actualité | `R06_page_service` |
| 9 | lacroix | `14b953bad35462df` | Jean-Paul II, apôtre de la jeunesse et de la liberté | Fiche encyclopédique intemporelle | `R06_page_service` |
| 10 | liberation | `6bcf1ed258dba1b9` | Tempête Austen, interdictions de manifester… L'actu de ce jeudi | Récapitulatif multi-sujets : brouillerait les thèmes | `R09_recapitulatif` |

**Gardés volontairement :**
- Les directs (« EN DIRECT ») : de la vraie actualité, dont on garde le premier titre vu.
- L'actualité des médias (« Télé - médias » à La Dépêche) : elle est gardée, sauf les grilles
  de programmes.
- Les tribunes (« OPINION. ») : gardées, à signaler comme opinion dans l'édition.

## 2. La normalisation

Une fonction pure par transformation, un test par fonction (`tests/test_normalisation.py`).
On l'applique avant les règles, sur le titre et l'extrait.

| Fonction | Ce qu'elle fait |
|---|---|
| `retirer_html` | Retire les balises, ainsi que le contenu des `<script>` et `<style>` |
| `decoder_entites` | `&amp;` → `&`, `&eacute;` → `é`, même doublement encodées |
| `reparer_encodage` | `Ã©tÃ©` → `été`, segment par segment, sans toucher le texte sain autour |
| `normaliser_espaces` | Espaces insécables → espace, caractères invisibles retirés, espaces fusionnés |
| `borner_extrait` | 300 caractères au plus, coupé au dernier mot entier, suivi de « … » |
| `date_utc` | Date ISO 8601 → UTC (sans fuseau, elle est supposée en UTC). `None` si elle est illisible |
| `cle_titre`, `mots`, `jaccard` | Titre sans casse, accents ni ponctuation ; ses mots porteurs de sens ; leur ressemblance |

## 3. Les règles d'exclusion

L'ordre d'application est le suivant : R10, R13, R12, R11, puis R01 à R09, puis R14 et R15.
**La première règle qui correspond l'emporte**, et son identifiant va dans la table
`rejets`, avec ce qui l'a déclenchée (le motif trouvé, ou l'article gardé à la place).

| Règle | Ce qu'elle écarte | Pourquoi | Exemple réel |
|---|---|---|---|
| `R01_publi` | Publi-reportages, contenus partenaires, bons plans, codes promo | De la publicité, qu'on n'a pas à republier | *(aucun vu pour l'instant)* « CONTENU SPONSORISÉ. Les meilleures offres… » |
| `R02_horoscope` | Horoscope, astrologie, tarot | Pas de l'information | *(aucun vu pour l'instant)* « Horoscope du jour… » |
| `R03_programme_tv` | Grilles télé, « sur quelle chaîne », site `programmetv.*` | Du service, pas de l'actualité | « Grand Prix MotoGP d'Australie. À quelle heure et sur quelle chaîne suivre… » |
| `R04_jeux` | Jeux, concours, quiz, résultats de loterie, « places à gagner » | Pas de l'information | « La Dépêche du Midi lance son espace jeux… » |
| `R05_meteo_service` | Bulletins météo quotidiens (« La météo à … du … ») | Du service. Une tempête, elle, reste de l'actualité | « La météo à Bordeaux du vendredi 23 octobre 2026 » |
| `R06_page_service` | Cartes, prix des carburants, pharmacies de garde, Évangile du jour, `/Definitions/` | Des pages mises à jour en continu ou intemporelles | « CARTE. Prix des carburants… » |
| `R07_media_seul` | « EN IMAGES », « DIRECT VIDÉO », diaporamas, podcasts | Pas d'article à lier, et on ne garde pas les images | « EN IMAGES. Tempête Austen : le point sur les dégâts… » |
| `R08_autopromo` | Le média parle de lui-même : ses prix, ses offres, son application | Ce n'est pas l'actualité | « Territoires Awards : BFM La Tribune récompense… » |
| `R09_recapitulatif` | « L'actu de ce jeudi », « L'essentiel de l'actu » | Plusieurs sujets dans un titre : ça brouillerait le regroupement par thèmes | « Macron reçoit des lycéens, la tempête Austen balaie la France… L'actu de ce vendredi » |
| `R10_titre_vide` | Titre vide ou de moins de 12 caractères | Ce n'est pas un titre d'article | *(aucun vu)* « Météo » |
| `R11_date_future` | Publié plus d'une heure dans le futur | Date fausse : l'article serait mal classé dans l'édition | *(aucun vu)* |
| `R12_sans_date` | Sans date, ou avec une date illisible | On ne peut pas dire s'il a moins de 24 h (cadrage) | *(aucun vu)* |
| `R13_encodage_casse` | Encodage cassé qu'on n'a pas su réparer (`�`) | Illisible | *(aucun vu)* |
| `R14_doublon_exact` | Même titre (casse, accents et ponctuation mis à part) qu'un article déjà gardé | Dépêche d'agence reprise à l'identique : on garde la première publiée | « Pierre Moscovici démissionne de la Cour des comptes européenne », La Croix, déjà chez Le Figaro |
| `R15_doublon_proche` | Titre presque identique (Jaccard ≥ 0,8 sur les mots, au moins 4 mots) | La même dépêche, à deux mots près | « Le prix Sakharov 2026 attribué… » (Libération) contre « … est accordé… » (Ouest-France), Jaccard 0,83 |

**Pourquoi un seuil de 0,8 pour R15 ?** Il a été mesuré sur nos 780 premiers items. Au-dessus
de 0,8, on ne trouve que des reprises de la même dépêche (Shamonda, Sakharov, Jean-Paul
Huchon). Dès 0,73, on trouve déjà deux articles différents de La Dépêche sur la même
manifestation toulousaine. Les doublons R14 et R15 sont cherchés parmi les articles des
72 dernières heures.

**Ajouter ou modifier une règle :**
1. Modifier le motif dans `regles.toml`.
2. Ajouter un exemple et un contre-exemple dans `tests/test_regles.py`.
3. Lancer `bin/test`.
4. Repasser les anciens rejets dans les règles :
   ```bash
   docker compose run --rm collecteur rejouer R07_media_seul
   ```
5. Noter le changement dans le journal (section 6).

## 4. Les contrôles de qualité

Les contrôles ne testent pas le code : ça, c'est le rôle de la CI, avec les fixtures. Ils
vérifient **des faits sur les vraies données**, après chaque passage, dans une tâche Prefect
(`controles-qualite`).

**Pourquoi des assertions maison en SQL plutôt qu'un outil dédié comme Great Expectations ?**
Huit faits simples tiennent en huit requêtes lisibles, sans service ni dépendance de plus.
Le cadrage avait déjà écarté Great Expectations, trop lourd ici.

| Contrôle | Le fait vérifié | Seuil |
|---|---|---|
| `C01_aucune_date_future` | Aucun article propre publié plus d'une heure dans le futur | 0 |
| `C02_aucun_titre_vide` | Aucun article propre au titre de moins de 12 caractères | 0 |
| `C03_taux_rejet_par_source` | Sur 24 h, aucune source ne voit plus de 80 % de ses items rejetés (au moins 10 items) | 0,8 |
| `C04_fraicheur_collecte` | Chaque source active a réussi une collecte dans les 2 dernières heures | 2 h |
| `C05_aucune_source_en_sommeil` | Aucune source de `sources.csv` en sommeil | 0 |
| `C06_extraits_bornes` | Aucun extrait de plus de 300 caractères | 0 |
| `C07_ni_html_ni_encodage_casse` | Ni balise HTML ni encodage cassé dans les titres et extraits | 0 |
| `C08_articles_des_dernieres_24h` | Au moins un article propre publié dans les dernières 24 h | ≥ 1 |

- **Les métriques** : chaque résultat (valeur, seuil, ok) est enregistré dans la table
  `controles`, que les tableaux de bord du TD 8 liront. Il est aussi publié comme artifact
  `controles-qualite` dans l'interface Prefect.
- **L'alerte** part vers le webhook Discord ou Slack de l'équipe (`GAZETTE_ALERTE_WEBHOOK`,
  dans `.env`) quand un fait **devient** faux, puis quand il redevient vrai. Elle ne part
  pas toutes les 30 min tant que le problème dure.
- **Alerte déclenchée pour de vrai le 23/10/2026** : le contrôle a été lancé sur les vraies
  données avec le seuil de `C03` abaissé à 5 % au lieu de 80 %. À 12 h 30 UTC, il est passé en
  échec (La Tribune 8 %, Sud Ouest 6 %, Ouest-France 8 %), et l'alerte 🔴 est arrivée sur le
  Discord de l'équipe. Remis au seuil normal, le contrôle est redevenu vrai, et le message
  🟢 « rétabli » est arrivé à 12 h 31.
- **L'incident du 22/10** : si ces contrôles avaient existé, `C05` et `C04` auraient sonné
  dès 15 h 23 UTC, au lieu de 22 h de silence avec 8 sources endormies.

## 5. Le rapport de qualité

Il est réécrit après chaque passage dans `rapports/qualite-AAAA-MM-JJ.md` : un fichier par
jour, archivé. Il est aussi publié comme artifact `rapport-qualite` dans Prefect, et
`python -m gazette rapport` l'affiche.

Pour le lire, il dit :
- pour le dernier passage et pour la journée, combien d'items sont **entrés**, **gardés**
  et **rejetés** ;
- les **rejets par règle**, avec leur part des items entrés ;
- le détail **par source**, avec le taux de rejet et la règle la plus fréquente. Un ⚠️
  au-delà de 80 % signale une règle sans doute trop gourmande ;
- les **cinq rejets les plus fréquents**, par couple règle × source ;
- **trois exemples par règle**, avec le motif qui l'a déclenchée : c'est là qu'on voit un
  faux positif ;
- l'état des **contrôles** du dernier passage.

## 6. Journal des ajustements

| Date | Règle | Changement | Pourquoi |
|---|---|---|---|
| 23/10/2026 | `R07_media_seul` | Retrait du motif `^replay` | Le premier rapport montrait 3 vrais articles de La Dépêche titrés « REPLAY. … » (des directs terminés, avec du texte). Ils ont été rejoués avec `rejouer R07_media_seul` et sont maintenant gardés |
| 23/10/2026 | `R07_media_seul` | Pas de motif `^VIDÉO` | La Dépêche et Ouest-France mettent « VIDÉO. » devant de vrais articles qui ont une vidéo |
| 23/10/2026 | `R08_autopromo` | `territoires awards` plutôt que `awards` | « NRJ Music Awards » est aussi de l'actualité |
| 23/10/2026 | `R04_jeux` | « places / cadeaux à gagner » plutôt que « à gagner » | « Ce que Macron a à gagner » est un vrai titre |
