# Veille éclair — six sujets

Pour chaque sujet : deux options, leurs limites, notre recommandation.

## 1. Récupérer ce que la presse publie
- **Option A : flux RSS / Atom.** Format prévu pour les machines : titre, extrait, lien, date. Limites : un flux ne garde que ses derniers articles, certains éditeurs bloquent leurs flux (La Voix du Nord depuis décembre 2025), les formats de date varient, et certains flux contiennent le texte intégral (champ `content:encoded`, à ignorer).
- **Option B : sitemaps news** (`news-sitemap.xml`). Liste les articles des dernières 48 h. Limites : pas d'extrait, pas toujours public.
- **Écarté : scraping HTML.** Interdit par le sujet, fragile, souvent contraire aux CGU.
- **Pièges** : opposition des éditeurs à la fouille de textes (`robots.txt`, `tdmrep.json`, CGU), adresses de flux qui changent, blocages si on interroge trop souvent.
- **Reco : RSS**, avec le sitemap news en secours si un flux tombe.

## 2. Faire tourner quelque chose tous les matins
- **Option A : cron** (dans un conteneur). Très simple. Limites : pas de relance automatique, pas d'historique, on ne voit pas facilement ce qui a échoué.
- **Option B : Prefect** (auto-hébergé, gratuit). Relances, historique, interface web. Limites : un service de plus à faire tourner.
- **Écartés** : Airflow (trop lourd pour 9 flux : base de données, scheduler, serveur web), GitHub Actions (les tâches planifiées peuvent partir en retard, et ça ne tournera pas sur l'infra fournie).
- **Reco : Prefect.**

## 3. Où et sous quelle forme stocker
- **Brut : fichiers JSON horodatés** (un dossier par jour) **ou stockage objet** de type S3 (MinIO). Les fichiers suffisent en local ; MinIO si l'infra fournie s'y prête.
- **Propre : PostgreSQL ou DuckDB / Parquet.** DuckDB est très simple mais n'accepte qu'un écrivain à la fois ; PostgreSQL gère les accès concurrents et la contrainte d'unicité sur l'URL.
- **Reco : JSON pour le brut, PostgreSQL pour le propre.** Dans les deux cas, uniquement titre, extrait, lien, date, source.

## 4. Regrouper des textes par thèmes
- **Option A : TF-IDF + clustering** (agglomératif ou k-means, scikit-learn). Rapide, sans GPU, explicable : un thème est décrit par ses mots-clés. Limites : sensible aux synonymes, il faut une liste de mots vides en français et régler un seuil.
- **Option B : embeddings de phrases + HDBSCAN / BERTopic.** Regroupe mieux les titres formulés différemment. Limites : modèle à télécharger, plus lent, plus dur à expliquer.
- **Hors sujet** : résumer avec un LLM.
- **Reco : TF-IDF + clustering agglomératif d'abord**, embeddings en évolution si les thèmes sont peu lisibles.

## 5. Surveiller un pipeline
- **Option A : logs structurés (JSON) + interface Prefect + alerte par webhook** (Discord, mail). Indicateurs : articles collectés par source, erreurs par source, durée des étapes, heure de publication, nombre de thèmes.
- **Option B : Prometheus + Grafana.** Tableaux de bord et alertes complètes. Limites : deux services de plus, lourd pour nos machines.
- **Reco : option A maintenant**, Prometheus et Grafana à réévaluer avec l'infra fournie.

## 6. Décrire une infrastructure en code
- **Option A : Docker Compose.** Un fichier décrit tous les services (collecte, PostgreSQL, Prefect, nginx). Limites : une seule machine.
- **Option B : Terraform** (créer les machines) **et / ou Ansible** (les configurer). Limites : utile seulement quand on aura une vraie infra.
- **Écarté : Kubernetes**, démesuré pour ce projet.
- **Reco : Docker Compose dès le TD 2**, puis Terraform ou Ansible selon l'infra fournie au TD 4 ou 6.
