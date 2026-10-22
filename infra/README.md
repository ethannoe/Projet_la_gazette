# infra/

L'infrastructure du projet, décrite en code. Rien de ce qui tourne n'est installé à la main.

- **Aujourd'hui (TD 2)** : l'environnement de dev est dans [`docker-compose.yml`](../docker-compose.yml), à
  la racine, pour que `docker compose up` marche sans option. L'image est décrite dans le
  [`Dockerfile`](../Dockerfile).
- **À venir** : l'ordonnancement Prefect (TD 3), le provisionnement de l'infrastructure fournie
  avec Ansible ou Terraform (TD 4-6), le déploiement et nginx (TD 7), les tableaux de bord (TD 8).
