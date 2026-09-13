# AgentFuse et La Suite : étude des intégrations et proposition de produit

Date de consultation : **13 septembre 2026**.

Cette note propose une cible de produit et un ordre de réalisation. Elle s’appuie sur les dépôts publics de La Suite, leurs descriptions, des documents d’API et quelques points d’entrée du code. Elle ne constitue ni un audit exhaustif, ni une validation par déploiement de ces applications, ni un engagement des équipes qui les maintiennent. Les liens vers `main` décrivent des sources susceptibles d’évoluer ; les versions à prendre en charge devront être fixées avant les essais d’intégration.

## 1. Proposition de positionnement

**AgentFuse serait un composant de sécurité côté serveur pour les opérations des assistants IA de La Suite. Après déploiement et configuration par l’exploitant, les agents publics utiliseraient leurs interfaces habituelles ; les opérations raccordées seraient vérifiées avant leur exécution.**

Le cœur resterait une bibliothèque Python indépendante. Des adaptateurs maintenus pour les applications de La Suite et une procédure de déploiement complète permettraient d’éviter à chaque organisme de réécrire le branchement.

L’objectif d’usage est simple : aucune installation AgentFuse sur le poste de l’agent public, et aucun code à écrire par l’administrateur pour une combinaison de versions officiellement prise en charge par le projet. La configuration propre à l’organisme reste nécessaire.

Cette cible est distincte de la livraison actuelle : le prototype contient le cœur et une intégration locale de messagerie avec Conversations. Les connexions à une messagerie réelle, à ProConnect et aux services de fichiers La Suite restent à réaliser. Le [guide d’installation actuel](installation.md#état-de-la-livraison) décrit cette limite.

## 2. Des applications réelles couvrent déjà de nombreux besoins

La Suite regroupe plusieurs applications, avec des dépôts et des services distincts. Leur présence ne signifie pas que tous leurs outils sont déjà exposés à Conversations ou contrôlés par AgentFuse. Le [catalogue officiel](https://lasuite.numerique.gouv.fr/) présente notamment la rédaction, les fichiers, les tableaux, la messagerie et la visioconférence.

Les opérations proposées dans la dernière colonne sont des **candidates à l’adaptation**, pas des fonctions AgentFuse déjà livrées.

| Besoin | Dépôt | Fonctions décrites par le projet | Opérations candidates |
| --- | --- | --- | --- |
| Assistant IA | [Conversations](https://github.com/suitenumerique/conversations) | Conversation, appels au modèle et mécanismes d’outils | Recevoir la tâche et contrôler les appels d’outils |
| Courrier électronique | [Messages](https://github.com/suitenumerique/messages) | Messages, brouillons, pièces jointes, recherche et boîtes partagées | Lire des messages désignés, extraire une pièce jointe, préparer ou envoyer un courrier |
| Espace de fichiers | [Drive](https://github.com/suitenumerique/drive) | Fichiers, dossiers, prévisualisation, partage et corbeille | Lire, classer ou copier un fichier vers un dossier autorisé |
| Documents collaboratifs | [Docs](https://github.com/suitenumerique/docs) | Édition collaborative, organisation des documents, droits et imports/exports | Créer un compte rendu ou un résumé dans une destination autorisée |
| Tableaux et données métier | [Grist](https://github.com/gristlabs/grist-core) | Tableaux liés, formules, droits d’accès et API | Alimenter un tableau de suivi ou modifier des lignes désignées |
| Calendrier | [Calendars](https://github.com/suitenumerique/calendars) | Événements, partage de calendriers et permissions | Consulter un agenda et proposer un rendez-vous |
| Gestion de projet | [Projects](https://github.com/suitenumerique/projects) | Projets, tableaux, cartes, responsables, échéances et commentaires | Créer une tâche ou mettre à jour son avancement |
| Réunions | [Meet / Visio](https://github.com/suitenumerique/meet) | Visioconférence, partage d’écran et enregistrement ; transcription et résumé annoncés en bêta | Traiter une transcription ou produire un compte rendu |
| Utilisateurs et équipes | [People](https://github.com/suitenumerique/people) | Gestion des utilisateurs, équipes et permissions entre applications | Fournir des informations d’identité et d’appartenance aux adaptateurs |

Ces projets constituent une base crédible pour des parcours de travail réels. Ils ne sont pas tous au même stade de maturité et ne couvrent pas nécessairement toutes les fonctions d’une suite bureautique. Par exemple, Drive prévoit l’édition de documents bureautiques via WOPI, un protocole permettant de connecter un service d’édition tel que Collabora ou OnlyOffice ; le dépôt Drive ne fournit pas à lui seul tout ce moteur d’édition.

**Attention au nom du service de messagerie :** le dépôt Messages se présente comme la messagerie collaborative de **La Suite territoriale**, portée par l’ANCT. Cette étude n’a pas établi qu’il s’agit de l’implémentation du service « Messagerie » présenté sur le catalogue national. Le premier objectif doit donc nommer précisément le dépôt et le service destinataires : « adaptateur Messages », sans annoncer une compatibilité avec toute messagerie administrative.

## 3. Des points de branchement existent déjà

Une API est une interface permettant à un programme de demander une opération à un autre programme. Disposer du code source permet de comprendre ses paramètres, ses droits et ses résultats. Quand une API convient au besoin, son utilisation évite de dépendre directement des tables internes de l’application.

| Application | Source à lire | Ce que l’étude a identifié |
| --- | --- | --- |
| Conversations → Docs | [`docs/interoperabilities.md`](https://github.com/suitenumerique/conversations/blob/4d6edc79be5ccfa34e57497a07311e8a1f2bba74/docs/interoperabilities.md), [`chat/views/edit_in_docs.py`](https://github.com/suitenumerique/conversations/blob/4d6edc79be5ccfa34e57497a07311e8a1f2bba74/src/backend/chat/views/edit_in_docs.py), [`chat/docs_client.py`](https://github.com/suitenumerique/conversations/blob/4d6edc79be5ccfa34e57497a07311e8a1f2bba74/src/backend/chat/docs_client.py) | Le bouton « Edit in Docs » crée un document à partir du texte d’une réponse. `edit_in_docs` appelle `DocsClient.create_document`, qui contacte Docs avec le jeton d’accès de l’utilisateur. |
| Docs | [`documentation/resource_server.md`](https://github.com/suitenumerique/docs/blob/main/documentation/resource_server.md) | Une API externe existe sous `/external_api/v1.0/`. Les routes et opérations disponibles dépendent de la configuration du serveur. |
| Messages | [`src/backend/core/api/openapi.json`](https://github.com/suitenumerique/messages/blob/main/src/backend/core/api/openapi.json) | Le schéma décrit notamment la lecture d’un message, les pièces jointes, les brouillons et l’envoi : `/api/v1.0/messages/{id}/`, `/api/v1.0/blob/{id}/download/`, `/api/v1.0/draft/`, `/api/v1.0/send/`. |
| Drive | [`src/backend/core/api/viewsets.py`](https://github.com/suitenumerique/drive/blob/main/src/backend/core/api/viewsets.py) | `ItemViewSet` gère les opérations sur les fichiers et dossiers et s’appuie sur `ItemPermission` pour les contrôles d’accès. |

Le parcours Conversations → Docs est une référence utile, mais il est déclenché par un bouton. Son existence ne prouve pas qu’un modèle dispose déjà d’un outil autonome de création documentaire, ni qu’AgentFuse contrôle ce parcours. Le support d’entrée des documents à analyser doit également être raccordé.

Les interfaces internes utilisées par un navigateur ne sont pas nécessairement prêtes pour un appel entre deux serveurs. Pour chaque cible, vérifier le mode d’authentification accepté et les permissions réellement appliquées. Le jeton d’un utilisateur ne doit pas être supposé valable dans toutes les applications simplement parce qu’elles appartiennent à La Suite.

## 4. Où le produit fonctionnerait

Les applications étudiées suivent principalement un fonctionnement web : un navigateur sur le poste de travail, et un backend — la partie qui traite les demandes — sur un serveur. Les dépôts de [Conversations](https://github.com/suitenumerique/conversations#self-host) et de [Drive](https://github.com/suitenumerique/drive#self-host) décrivent leur hébergement sur des serveurs.

L’intégration proposée serait la suivante lorsque Conversations émet les appels d’outils :

```text
Poste de l’agent public
  Navigateur : conversation, lecture, édition
                         |
                         v
Serveur de l’application
  Conversations : identité connectée et tâche
                         |
  Outil connu : traduction de la demande du modèle
                         |
  AgentFuse : vérification et décision enregistrée
                         |
  Si autorisé : nouvelle vérification, puis exécution
             +-----------+-----------+
             |           |           |
             v           v           v
         Messages       Drive       Docs
         API + droits   API + droits API + droits
             |           |           |
             +-----------+-----------+
                         |
              Reçu, journal et résultat
                         |
              Retour dans la conversation
```

Le cœur s’exécuterait dans le processus du backend Python qui appelle les outils. Il n’exigerait pas un serveur AgentFuse séparé. Les services cibles continueraient à appliquer leurs propres droits.

**Installer AgentFuse sur le poste d’un agent public ne modifie pas le fonctionnement d’un service distant.** Si l’organisme utilise un service hébergé par un tiers, son opérateur doit réaliser l’intégration. Si l’organisme héberge lui-même les applications, son équipe technique peut déployer le composant sur ses serveurs.

Si Docs, Messages ou un autre produit possède son propre assistant IA, ses chemins d’exécution doivent être examinés et raccordés séparément. Un adaptateur capable d’appeler l’API de Docs ne protège pas automatiquement l’IA interne de Docs. L’historique, les pièces jointes, les recherches et les sorties réseau qui contournent le point de contrôle restent également à traiter.

## 5. Ce qui serait automatique, et ce qui reste à configurer

L’objectif proposé est **un usage sans installation supplémentaire pour l’agent public**, et un déploiement sans modification de code pour l’administrateur sur les versions prises en charge.

| Responsable | Intervention attendue | Automatisation à fournir |
| --- | --- | --- |
| Agent public | Se connecter, exprimer sa tâche, éventuellement répondre à une demande de confirmation | Contrôles avant les opérations, retour de résultat et explication des refus |
| Administrateur ou exploitant | Choisir les intégrations actives, configurer les connexions, valider les politiques et les personnes habilitées | Installation, chargement des adaptateurs, vérifications de connexion et journalisation |
| Équipe AgentFuse | Développer les adaptateurs, tester les versions et préparer la livraison | Réutilisation du même branchement dans les organismes compatibles |

Trois informations propres à l’installation restent nécessaires :

1. **Les services destinataires :** adresses des API, versions et fonctionnalités activées. Les valeurs déjà présentes dans l’application peuvent être réutilisées lorsque cela convient.
2. **L’identité et les droits :** utilisateur connecté, boîtes accessibles, dossiers autorisés et méthode d’authentification entre services. Ces faits proviennent des systèmes de confiance, jamais du modèle.
3. **Les politiques de l’organisme :** destinations externes autorisées ou interdites, ressources exclues, conditions de confirmation et personnes habilitées. Des valeurs initiales peuvent être proposées, puis validées par l’administrateur.

Ces éléments peuvent être renseignés par configuration ou par un assistant d’installation. Ils ne nécessitent pas forcément du Python. En revanche, l’installateur ne peut ni inventer les règles métier ni s’accorder des permissions.

Le périmètre de la tâche doit être établi côté serveur à partir du parcours utilisateur et des ressources sélectionnées. L’expérience visée ne demande pas à l’agent public de remplir un formulaire technique d’autorisation avant chaque tâche.

## 6. Une bibliothèque indépendante et une intégration livrée ensemble

Le produit devrait réunir trois éléments complémentaires :

| Élément | Rôle | État visé |
| --- | --- | --- |
| Cœur AgentFuse | Contrats, contrôle des opérations et décisions | Bibliothèque indépendante, sans dépendance au modèle ni au framework web |
| Adaptateurs La Suite | Conversion des outils, lecture des droits, appels métier et gestion des résultats | Code réutilisable et maintenu pour des versions annoncées |
| Livraison pour l’exploitant | Configuration, chargement automatique, stockage des décisions, diagnostic et procédure de mise à jour | Installation reproductible dans l’environnement du backend |

Les adaptateurs ne se limitent pas à envoyer des requêtes HTTP. Ils doivent fournir les identités et droits fiables, conserver l’ordre d’exécution, enregistrer les résultats et gérer les échecs. Les interfaces existantes sont décrites dans [`ports.py`](../src/agentfuse/ports.py) et dans le [guide de branchement](installation.md#3-brancher-le-contrôle-avant-les-effets).

Les implémentations locales [`host.py`](../src/agentfuse/host.py) et [`storage.py`](../src/agentfuse/storage.py) peuvent servir de référence. Le stockage et les garanties à fournir dans un déploiement avec plusieurs serveurs doivent être choisis et validés ; une transaction SQLite locale n’englobe pas une opération distante sur une messagerie.

### Faire partie de La Suite

Une intégration aux distributions des applications serait une direction intéressante : la version publiée embarquerait le paquet, chargerait le contrôle au démarrage et lirait la configuration de l’exploitant. L’utilisateur final n’aurait alors aucun paquet à installer lui-même.

**La présence d’un dépôt AgentFuse dans une organisation GitHub ne suffit pas.** Il faut que les applications incluent effectivement la dépendance et appellent le contrôle sur les opérations concernées. L’acceptation de cette intégration relève des mainteneurs amont ; elle n’est pas acquise.

Avant une éventuelle intégration officielle, le projet peut préparer une distribution intégrée et versionnée pour des versions précises de Conversations et des services cibles. Cela conserve l’indépendance du cœur tout en permettant un déploiement reproductible.

Le [script de correctifs actuel](../tools/patch_conversations.py) concerne la copie isolée de Conversations installée pour la démonstration. Il ne recherche pas toutes les installations existantes et ne garantit pas la compatibilité avec un emplacement ou une version quelconques. Une future procédure devra recevoir explicitement sa cible et vérifier sa compatibilité.

## 7. Parcours de livraison proposé

Les étapes suivantes décrivent le travail à fournir pour atteindre une installation automatisée ; elles ne sont pas des commandes déjà disponibles.

1. **Préparer une version compatible.** Fixer les versions du cœur, des adaptateurs et des applications ; annoncer les opérations réellement prises en charge et tester leurs interfaces.
2. **Livrer le branchement.** Inclure les dépendances et l’enregistrement des outils contrôlés dans la construction du backend. Fournir les réglages nécessaires et les changements de stockage éventuels.
3. **Configurer l’organisme.** Renseigner ou réutiliser les adresses, raccorder les identités, choisir les politiques et les droits d’administration. Le même code peut servir à plusieurs organismes avec des configurations différentes.
4. **Vérifier avant activation.** Contrôler les versions, l’identité, les accès aux services et l’écriture du journal. Une intégration obligatoire indisponible doit empêcher les opérations concernées, sans retour silencieux vers un outil non protégé.
5. **Déployer sur les processus qui exécutent les outils.** Mettre à jour les services concernés et rendre visible l’état de protection. Un simple import Python ne démontre pas que tous ces processus passent par le contrôle.
6. **Valider les effets et préparer les mises à jour.** Tester un parcours autorisé, un refus de lecture, une destination interdite, un changement de droits, un appel répété et un résultat distant incertain. Documenter l’arrêt, la reprise et le retour à une version compatible sans perdre les journaux.

Pour un service distant, un délai dépassé peut signifier que l’opération a eu lieu mais que sa réponse a été perdue. L’adaptateur doit vérifier le résultat ou utiliser un mécanisme empêchant le double effet, plutôt que relancer aveuglément un envoi ou une création. Les critères déjà définis figurent dans la [validation d’installation](installation.md#4-vérifier-linstallation-et-lintégration).

## 8. Ordre de réalisation recommandé

| Étape | Parcours | Résultat à démontrer |
| --- | --- | --- |
| 1 — Conversations + Docs | Analyser une ressource autorisée et créer un résumé dans Docs | Identité réelle, droits vérifiés, création contrôlée et lien vers le document ; une opération hors périmètre est bloquée |
| 2 — Messages + Drive | Lire des pièces jointes désignées et les classer dans des dossiers autorisés | Effets réels dans les services ; refus d’accès à une autre boîte ou d’un transfert vers une destination interdite |
| 3 — Autres opérations | Ajouter progressivement tableaux, agendas et tâches | Pour chaque opération : droits, paramètres, effets, résultats et tests propres au métier |

L’étape 1 crée une nouvelle intégration réelle ; elle ne demande pas de restaurer l’ancien scénario documentaire du prototype. Le client Docs de Conversations peut servir de point de départ, après vérification de la version retenue.

L’étape 2 permettrait de remplacer le métier local de [`mail_tools.py`](../integrations/conversations/mail_tools.py) et de [`MailWorkspace`](../src/agentfuse/mailbox.py) par des services réels, tout en conservant les garanties du contrôle. Les fonctions locales ne constituent pas déjà un connecteur Messages ou Drive.

Les contrats actuels décrivent `resource.read`, `document.create` et `file.copy`. Envoyer un courrier complet, supprimer un fichier, changer un partage ou créer un rendez-vous peut nécessiter de nouveaux contrats et de nouvelles règles. Ces opérations ne doivent pas être ramenées artificiellement à une simple copie de fichier.

Pour lancer la première intégration, il reste à choisir les versions exactes, obtenir un environnement de test avec identités et permissions représentatives, fixer les premières opérations autorisées et désigner l’exploitant du service. Les politiques avec confirmation nécessitent aussi un véritable circuit de validation et de reprise : le contrat `ask` existe, mais la messagerie actuelle ne fournit pas ce circuit.

## 9. Ce que cette proposition ne change pas dans l’état actuel

Le prototype continue à fournir une messagerie métier fictive, des PDF réels, une instance réelle de Conversations et une boîte MIME locale. Il ne délivre pas de messages par un service SMTP externe. La [documentation d’intégration actuelle](../integrations/conversations/README.md) et les [résultats de validation](mail-validation.md) décrivent les essais réalisés.

Cette étude n’ajoute aucun adaptateur, ne déploie aucun service et ne valide pas une installation de production. Les réserves recensées dans la [revue de publication](publication-review.md), notamment le chemin réseau des images Markdown dans Conversations, restent distinctes de cette proposition et ne sont pas corrigées par la rédaction de ce document.
