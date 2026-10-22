# Qualité des données brutes

Les items de `articles_bruts/` qui n'ont rien à faire dans une gazette :
publi-reportages, horoscopes, programme TV, jeux, titres vides… Ils restent en brut
et seront écartés au nettoyage (TD 4). Ici, on les repère et on note comment les
reconnaître.

Pour fouiller : `ls articles_bruts/<source>/`, ou chercher un mot dans les titres :

```bash
grep -l '"titre": ""' articles_bruts/*/*.json
grep -il horoscope articles_bruts/*/*.json
```

| # | Source | Fichier (`id`) | Titre | Pourquoi l'écarter | Comment le reconnaître |
|---|---|---|---|---|---|
| 1 | ouestfrance | | | Programme TV | lien sur `programmetv.ouest-france.fr` |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |
| 6 | | | | | |
| 7 | | | | | |
| 8 | | | | | |
| 9 | | | | | |
| 10 | | | | | |
