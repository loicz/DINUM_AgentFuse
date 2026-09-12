# AgentFuse · Sécurité des appels d’outils

**État au 11 septembre 2026 : prototype local fonctionnel, revue de publication avec réserves.** Un accès réseau par image Markdown dans le frontend Conversations reste à corriger ; l’installation du navigateur de validation et les procédures d’exploitation sont incomplètes. Voir la [revue avant publication](docs/publication-review.md) pour les défauts, les tests réussis et le périmètre réellement livré.

Les politiques de l’organisation encadrent en arrière-plan les appels d’outils de l’IA. Les opérations conformes se poursuivent automatiquement ; les opérations interdites sont bloquées avant leur exécution. Les agents commencent directement leur travail, sans remplir de formulaire d’autorisation de tâche AgentFuse.

La démonstration principale associe **une messagerie interne de recrutement, inspirée des services publics français, et une véritable instance de Conversations** : traiter les candidatures d’une journée, lire les CV PDF et classer les pièces jointes originales par spécialité. Un CV contient une injection de prompt qui cherche à pousser le modèle à transférer une pièce jointe vers une adresse externe.

La messagerie et les personnes constituent un scénario local fictif ; l’interface React de Conversations, les services Django d’identité et de conversation, PostgreSQL, PydanticAI et le modèle Qwen fonctionnent réellement. Les PDF, les archives ZIP et les messages MIME reçus dans la boîte isolée sont téléchargeables. L’essai de transfert externe écrit uniquement dans une boîte locale, sans connexion SMTP.

## Installer le composant dans une application

Pour DINUM et les développeurs d’un backend existant : suivre le **[guide d’installation et de branchement du composant](docs/installation.md)**. Il décrit la construction/livraison du wheel, l’installation dans le backend destinataire, les dépendances hors ligne et les ports à implémenter avant les effets réels.

```sh
python3 -m pip install .
python3 examples/policy_check.py
```

La distribution est `agentfuse-pilot`, le module Python `agentfuse`. Le cœur dépend uniquement de Pydantic ; le modèle local, Django et les serveurs de démonstration ne sont pas nécessaires. L’installation ne protège pas automatiquement des outils non branchés. Les intégrations de production DINUM/ProConnect/La Suite restent à réaliser.

Pour développer : lire les [responsabilités et le plan des fichiers](docs/architecture.md) et les [instructions du dépôt](AGENTS.md). `storage.py` porte SQLite, `host.py` l’exécution protégée et `mailbox.py` le métier de la messagerie. Les exemples d’utilisation du cœur et de PDF locaux sont dans `examples/`.

## Essayer la messagerie locale

Après l’installation de la démonstration décrite ci-dessous, depuis la racine de ce dépôt :

```sh
python3 start.py
```

Ouvrir **http://127.0.0.1:8787** pour accéder à la messagerie.

| Compte | Utilisation |
| --- | --- |
| `alice` | Lire les messages, consulter ou télécharger les PDF, ajouter ses propres CV PDF fictifs, demander leur classement à Conversations |
| `admin` | Lancer des comparaisons avec le vrai modèle, protection activée/désactivée, consulter les preuves historiques et ajouter ou retirer des règles de blocage par formulaire |

Le mot de passe commun est `agentfuse-demo`. Cette connexion de démonstration locale utilise de véritables sessions Django ; ce n’est pas une intégration ProConnect.

1. Après connexion, Alice sélectionne la candidature de Noé Moreau et clique sur **Consulter le CV** pour voir le PDF complet.
2. Cliquer sur **Trier avec Conversations**. L’application native prépare une demande de travail ordinaire, modifiable avant son envoi normal.
3. Consulter **CV classés** et télécharger les vrais PDF/ZIP classés dans `informatique / droit / environnement / gestion`. Après le blocage d’une opération dangereuse, l’exécution des outils de cette tâche s’arrête. **Activité de protection** affiche le nom du fichier, le message d’origine, l’expéditeur, la date de réception, la version du fichier et le motif du blocage. Un PDF présentant un signal d’injection au scan, ou l’unique PDF lu, est placé par défaut en **Quarantaine**. Si plusieurs PDF ont été lus sans signal direct, seuls les fichiers candidats sont signalés, sans mise en quarantaine collective.
4. admin → **Comparer les effets** : choisir le PDF injecté ou le témoin sain et lancer deux requêtes Conversations réelles et indépendantes, ou sélectionner un enregistrement historique. Examiner séparément la proposition de transfert du modèle, le nombre de PDF réellement reçus et l’achèvement du classement normal ; télécharger le JSON et les fichiers `.eml` effectivement reçus.
5. admin → **Règles du service** : saisir le nom d’une règle, choisir le dossier interne dont les copies doivent être suspendues, puis publier. Aucun code à écrire ; les utilisateurs ordinaires n’ont pas ce droit d’administration.

Pour ses propres PDF : Alice → **Ajouter une candidature PDF**, saisir le nom du candidat et importer le fichier. Limites : 2 MiB par fichier et 12 CV par journée de démonstration. Seuls les PDF dont le texte est extractible sont pris en charge, sans OCR ni fichiers chiffrés. Les nouvelles pièces jointes reçoivent automatiquement la classification restreinte prévue par l’organisation ; une déclaration « public/déjà autorisé » dans le PDF ne confère aucun droit. Terminer d’abord le classement en cours ; **Arrêter le tri** bloque les appels d’outils suivants tout en conservant les copies déjà créées.

La quarantaine est un dossier logique persistant de la messagerie locale : les octets du PDF et sa provenance sont conservés, mais le fichier est exclu des lectures du modèle, des listes des nouvelles tâches, du classement/transfert et des téléchargements PDF/ZIP ordinaires. Les copies existantes contenant les mêmes octets sont également restreintes. L’utilisateur peut demander explicitement un téléchargement depuis la quarantaine pour inspection manuelle, sous réserve de ses droits sur le fichier. Le modèle ne dispose ni de cet outil ni d’un outil de levée de quarantaine. Une nouvelle tâche Conversations peut traiter les fichiers restants. Mettre en quarantaine l’unique PDF lu est une précaution, pas une preuve qu’il a causé l’injection ; une simple règle de suspension de dossier ne suffit pas à déclarer un fichier suspect. Voir le [fonctionnement de la quarantaine](docs/mail-quarantine.md).

Ce petit modèle ne se laisse pas nécessairement tromper à chaque essai et ne garantit pas un classement correct. Sans proposition d’opération interdite, on ne peut pas déclarer l’interception réussie. Voir le [guide de démonstration](docs/mail-demo.md) et les [résultats de validation](docs/mail-validation.md).

## Installer et démarrer la démonstration

```sh
python3 tools/setup.py
python3 tools/setup_mail.py
python3 start.py
```

L’installateur natif de la messagerie cible **Fedora 44 / Linux x86-64 / Python 3.14** et nécessite `uv`, `curl`, `rpm2cpio`, `pdftotext` et `prlimit`. Les téléchargements, environnements Python, Node, bases de données et copies de l’application restent dans ce répertoire. Le commit amont, les dépendances verrouillées et les SHA-256 des binaires sont fixés. La première installation nécessite le réseau et plusieurs Go d’espace disque ; après démarrage, seuls des services localhost sont utilisés. L’installation complète sur d’autres plateformes n’a pas été validée.

```sh
python3 tools/setup_mail.py --verify
python3 start.py --restart
```

Le redémarrage ne gère que les services lancés depuis ce répertoire et conserve messages, pièces jointes, archives, versions de politique et historique. Les tâches interrompues sont marquées comme inachevées ; leurs effets réels et leur audit sont conservés, sans réexécution automatique.

| Adresse/répertoire | Rôle |
| --- | --- |
| `127.0.0.1:8787` | Point d’entrée du produit |
| `127.0.0.1:8071/mail/` | Messagerie et backend Conversations |
| `127.0.0.1:3000` | Frontend natif de Conversations |
| `127.0.0.1:18081` | Modèle local, avec clé aléatoire côté serveur |
| `.runtime/mail-workspace.sqlite` | Messages, PDF, ACL, politiques, traces d’exécution et archives |
| `.runtime/mail-experiments/` | Bases d’expériences isolées les unes des autres |
| `.runtime/mail-registry.sqlite` | Propriété des expériences, liaison des conversations, configuration figée |
| `.runtime/pgdata/` | Base des conversations et des identités Conversations |
| `.runtime/conversations.log`, `model.log` | Journaux de diagnostic ; ne pas publier le répertoire d’exécution ni les clés |

La démonstration n’expose que la messagerie actuelle. Le point d’entrée 8787 fournit la redirection et `/api/health`, sans base ni API documentaire. Les données d’utilisation restent dans `.runtime/` et ne sont pas livrées aux développeurs. Une ancienne base peut conserver des archives supplémentaires ; le code ne les supprime pas.

La [documentation Conversations](integrations/conversations/README.md) décrit le branchement réel et les restrictions de contexte. Le schéma du paquet est `pilot-v1` ; les contrats génériques sont distincts des capacités effectivement exposées par l’application.

## Validation

```sh
.venv/bin/python -m pytest -q
.runtime/conversations-venv/bin/python tools/test_mail_http.py
.runtime/conversations-venv/bin/python tools/test_mail_quarantine_browser.py --output /tmp/agentfuse-quarantine-browser
.venv/bin/python tools/test_mail_browser.py --run-model
.venv/bin/python tools/test_mail_admin_browser.py
.venv/bin/python tools/test_mail_live.py --scenario attack --repeat 3 --assert-result
.venv/bin/python tools/test_mail_live.py --scenario clean --repeat 2 --assert-result
```

Le verrou principal ne contient plus le moteur PydanticAI de l’ancien scénario. Conversations conserve ses propres dépendances dans `integrations/conversations/requirements.lock`.

Les tests navigateur utilisent le Chromium déjà installé dans cet espace de travail ; il ne s’agit pas d’une dépendance du produit. Les validations avec le vrai modèle créent de nouvelles expériences isolées et de nouvelles conversations. Les exécutions historiques et nouvelles sont distinguées, sans fabriquer de marqueur de réussite.

La couverture porte sur le cœur indépendant, l’hôte SQLite, les outils de messagerie, la quarantaine et les frontières d’exécution. `document.create` et `ask` sont conservés dans les contrats et testés au niveau du moteur ; aucun adaptateur documentaire ni circuit d’approbation métier n’est fourni par la messagerie. Celle-ci refuse les nouvelles règles d’approbation et suspend sans effet une ancienne configuration qui en demande une.

Les pièces jointes envoyées directement au chat, les bases de connaissances de projet, la reprise d’anciens échanges, le RAG et la recherche web ne font pas partie de cette intégration ; leurs entrées sont désactivées ou refusées avant l’appel au modèle.

Les droits proviennent du compte, de la boîte de la journée de démonstration courante, des capacités d’outils prédéfinies et de la configuration de l’organisation. Le modèle propose le classement par spécialité ; ce n’est pas une étiquette de sécurité. Le scan repose sur un ensemble limité de motifs textuels : il ne reconnaît pas tous les contenus malveillants et ne suit pas précisément des données reformulées arbitrairement. Le composant applique les limites configurées et vérifiables, sans garantir que chaque décision métier autorisée corresponde à l’intention réelle de l’utilisateur.
