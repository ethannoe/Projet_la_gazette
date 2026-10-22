# infra/

L'infrastructure du projet, décrite en code. Rien de ce qui tourne n'est installé à la main.

- **TD 2** : l'environnement de dev est dans [`docker-compose.yml`](../docker-compose.yml), à
  la racine, pour que `docker compose up` marche sans option. L'image est décrite dans le
  [`Dockerfile`](../Dockerfile).
- **TD 3** : l'orchestration (serveur Prefect et collecte planifiée) est aussi dans
  `docker-compose.yml` ; le schéma de la base est dans des migrations versionnées
  ([src/gazette/migrations/](../src/gazette/migrations/)). Voir
  [docs/orchestration.md](../docs/orchestration.md).
- **À venir** : le provisionnement de l'infrastructure fournie avec Ansible ou Terraform
  (TD 4-6), le déploiement et nginx (TD 7), les tableaux de bord (TD 8).
