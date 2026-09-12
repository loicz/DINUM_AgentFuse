# Archives des expériences et édition française

Ces fichiers décrivent des exécutions historiques de Conversations avec le modèle local. Ils se consultent indépendamment de la base d’utilisation. Les identifiants et liens `localhost` désignent les conversations de l’environnement où l’expérience a été exécutée ; ils ne recréent pas ces conversations sur une nouvelle installation.

## Quatre fichiers traduits le 11 septembre 2026

Les rapports et flux des expériences `pair-b4720c1ba7913118` et `pair-c54eaf5a66136dac` contenaient chacun une expression non française dans la réponse finale du modèle. Cette expression est rendue par « mené à bien » dans les deux rapports JSON et les deux fichiers `-streams.json`.

Ces quatre fichiers sont désormais des **éditions françaises de publication**, et non des octets bruts reçus du modèle. Leur champ `publication` indique la traduction et l’empreinte SHA-256 du fichier avant transformation. Le [manifeste de publication](publication-fr.json) donne également les empreintes des éditions publiées. Les versions antérieures restent dans l’historique Git du projet.

La traduction ne modifie ni les paramètres d’outils, ni les décisions, ni les reçus d’exécution, ni les compteurs, ni les empreintes des PDF. Un instantané `source_sha256` décrit toujours le code utilisé à l’époque ; il ne doit pas être remplacé par l’empreinte du code actuel. Les autres archives sont conservées sans traduction. Une réponse historique traduite ne garantit pas la langue des réponses futures du modèle.

## Versions de comportement

- Les expériences directement dans ce répertoire précèdent l’arrêt et la quarantaine : le classement pouvait continuer après un transfert bloqué.
- `quarantine/` correspond à l’arrêt avec rapport de provenance et sélection prudente des fichiers à isoler.
- `refactor/` correspond à la séparation du stockage, de l’hôte et de l’adaptateur de messagerie.
- `review/` conserve les deux nouvelles paires et leurs flux pendant la [revue avant publication du 11 septembre](../../publication-review.md) ; cette revue identifie aussi un défaut navigateur indépendant des outils.

Le détail des vérifications et leurs limites figure dans la [validation](../../mail-validation.md). Aucun résultat historique ne prouve à lui seul le bon fonctionnement d’une installation ou d’une version différente.
