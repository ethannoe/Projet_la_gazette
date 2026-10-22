# Qualité des données brutes

Les items de `articles_bruts/` qui n'ont rien à faire dans une gazette. Ils restent en
brut et seront écartés au nettoyage (TD 4). Ici, on les repère et on note comment les
reconnaître, pour en tirer des règles.

Relevé du 22/10/2026 sur les 330 premiers items collectés (9 sources).

## Dix items à écarter

| # | Source | `id` | Titre | Pourquoi l'écarter | Comment le reconnaître |
|---|---|---|---|---|---|
| 1 | ouestfrance | `37be69ff6d380e81` | « Je suis dégoûtée » : Angèle annule en dernière minute sa participation aux « NRJ Music Awards »… | Programme TV et people, sur le site télé d'Ouest-France | Domaine du lien : `programmetv.ouest-france.fr` |
| 2 | sudouest | `e6f5a2a8d7f1c179` | La météo à Bordeaux du jeudi 22 octobre 2026 | Bulletin météo quotidien : du service, pas de l'actualité (la tempête Austen, elle, en est) | Titre `La météo à … du <date>`, lien en `-meteo-du-` |
| 3 | ladepeche | `4016ae38fa2f070c` | CARTE. Prix des carburants : tarifs, stations et bornes de recharge électrique les moins chères… | Page de service mise à jour en continu, pas un article | Préfixe `CARTE.`, « les moins chères » |
| 4 | ladepeche | `fcc3d4cde05f6a60` | La Dépêche du Midi lance son espace jeux : à vos neurones, prêts, jouez ! | Autopromotion du journal, et des jeux | Nom du média dans le titre ; « jeux », « jouez » |
| 5 | latribune | `e2241d1dc9474ecd` | Territoires Awards : BFM La Tribune récompense l'excellence entreprenariale | Autopromotion d'un événement organisé par le média lui-même | Nom du média dans le titre ; « Awards » |
| 6 | sudouest | `67657ed3cf15ef57` | DIRECT VIDÉO. UBB Espoirs : Suivez la rencontre face à l'Aviron Bayonnais en live sur TV7 | Retransmission vidéo d'un match, pas un article | Préfixe `DIRECT VIDÉO.` ; « Suivez … en live » |
| 7 | liberation | `6e1bd0cea9210c54` | EN IMAGES - La jeunesse d'Europe se révolte | Diaporama : que des photos, et on ne garde pas les images | Préfixe `EN IMAGES` |
| 8 | lacroix | `2164cad3306cf9b0` | Feu, foi, baptême. Commentaire de l'Évangile du jeudi 22 octobre | Rendez-vous quotidien de spiritualité, pas de l'actualité | « Commentaire de l'Évangile du » |
| 9 | lacroix | `14b953bad35462df` | Jean-Paul II, apôtre de la jeunesse et de la liberté | Fiche encyclopédique intemporelle, remontée dans le flux | Chemin du lien en `/Definitions/` |
| 10 | liberation | `6bcf1ed258dba1b9` | Tempête Austen, interdictions de manifester, présentation du Tour de France… L'actu de ce jeudi | Récapitulatif de plusieurs sujets : il brouillerait le regroupement par thèmes | « L'actu de ce … », titre qui énumère plusieurs sujets |



- **Les directs** (« EN DIRECT », « DIRECT. ») : de la vraie actualité, mais une page dont
  le titre change à chaque mise à jour, sous le même lien. On ne garde que le premier
  titre vu. La Croix ouvre aussi un direct par jour sur le même sujet (`…-jour-5`,
  `…-jour-6`). Exemple : lacroix `d709cf97a22ff5c7`.
- **People et télé** : la rubrique « Télé - médias » de La Dépêche mélange l'actualité des
  médias et la promotion d'émissions. Exemple : ladepeche `13c9102428ac47af`, la
  présentation d'un nouveau jeu de M6.
- **Les tribunes et chroniques** (« OPINION. », « La chronique de… ») : à garder, mais
  peut-être à signaler comme opinion dans l'édition.

## Défauts de champs repérés (pas des items à écarter)

- **Rubrique « article » chez La Tribune** : ses liens commencent par `/article/afrique/…`.
  C'est corrigé pour les prochains items, et les 20 items déjà écrits gardent
  « article ».
- **Rubrique = titre de l'article** chez La Croix, quand le lien n'a pas de rubrique
  (lacroix `9d57a76cee648a6d`). C'est corrigé de la même façon.
- **Rubriques géographiques chez Le Progrès** (« Rhône » partout) : à recalculer depuis
  l'URL au nettoyage.

## Pas trouvé (pour l'instant)

Aucun horoscope, aucun publi-reportage signalé comme tel, aucun titre vide, aucune date
manquante dans ces 330 items. À revérifier quand la collecte aura tourné une semaine.

## Pour chercher

```bash
grep -ilE '"titre": "(EN IMAGES|CARTE\.)|meteo-du-' articles_bruts/*/*.json
grep -l 'programmetv\.' articles_bruts/*/*.json
grep -l '"titre": ""' articles_bruts/*/*.json
```
