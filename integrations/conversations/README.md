# Intégration locale de Conversations à la messagerie

Chaîne réellement exécutée : React/AI SDK natifs → sessions Django et ChatConversation → AIAgentService → ConversationAgent natif → PydanticAI → Qwen local → AgentFuse → copies PDF réelles et boîte de réception isolée dans SQLite.

L’amont `suitenumerique/conversations` est fixé au commit `4d6edc79be5ccfa34e57497a07311e8a1f2bba74`. L’installateur vérifie l’archive source ; le [script de correctifs](../../tools/patch_conversations.py) ne modifie que la copie isolée du répertoire d’exécution du prototype. `requirements.lock` fige les dépendances Python validées ; le frontend utilise le verrou Yarn d’origine et Node 22.23.2.

| Fichier | Responsabilité |
| --- | --- |
| `local_settings.py` | Configuration localhost explicite, véritables connexion Django/PostgreSQL/sessions en base, services externes désactivés |
| `local_urls.py` | Connexion locale, CSRF, cookie de langue ; les URL de chat utilisent les vues natives |
| `mail_views.py` | Messagerie, import/téléchargement, classement, administration et expériences isolées ; vérification des rôles côté serveur |
| `mail_tools.py` | Enregistrement des outils, liaison de l’entrée réelle, vérification du compte et du contexte, contrôle d’exécution, fin de tâche |
| `mail_evidence.py` | Empreintes figées du modèle, du code et de la configuration ; distinction entre proposition, livraison réelle, blocage et classement |
| `llm.json` | Modèle et instructions de tâche communs aux deux branches ; ne peuvent accorder aucun droit |
| `assets/fonts/` | Police Inter et licence ; aucune requête de police vers un tiers |

L’amont actuel ne transmet pas automatiquement les `settings` de la configuration du modèle à l’exécution de l’agent. Cette intégration applique explicitement dans `register` : `temperature=0.2`, `seed=42`, `max_tokens=1500`, `timeout=180`, `parallel_tool_calls=False`. Le champ `llm_configuration` des preuves est l’instantané de la configuration d’origine ; les paramètres réellement appliqués sont ceux de `mail_tools.py`, dont l’empreinte est figée en même temps. Les deux branches partagent cette implémentation. Les paramètres de lancement de llama.cpp — un seul slot, contexte de 8192 tokens et reasoning désactivé — figurent dans `tools/serve_model.py`.

Chaque nouveau chat traite une tâche de classement. Le serveur produit le TaskScope à partir du compte connecté, de la journée de démonstration de la boîte et des dossiers prédéfinis. Modifier la demande en tant qu’utilisateur ordinaire n’ajoute aucun droit ; le texte réellement soumis est lié à nouveau et scanné avant la première exécution. Une requête de streaming répétée ne peut pas obtenir deux fois le droit d’exécuter la même tâche.

Les appels d’outils passent par `normalize → load_request → PolicyEvaluator → claim_execution → execute → record_result`. La copie lie la version du PDF source, la version de configuration de la destination, le nom du fichier et son SHA-256 complet. Dans une même transaction, l’exécuteur revérifie ACL, politique et périmètre, puis écrit la copie, les effets et le reçu. Le téléchargement d’une copie existante vérifie également les ACL et l’intégrité actuelles.

Lorsqu’une opération dangereuse est bloquée, l’hôte enregistre, dans la transaction de la décision, le rapport de provenance, la mise en quarantaine par défaut et l’arrêt de la tâche. Seuls les PDF présentant un signal d’injection au scan, ou l’unique PDF lu, sont automatiquement isolés. Avec plusieurs PDF sans signal, les candidats sont listés et la tâche s’arrête. Le contexte déjà lu est conservé pour l’audit ; la tâche courante ne reprend pas. Les nouvelles tâches excluent les octets isolés, et les téléchargements ordinaires/copies classées sont également restreints. La messagerie affiche les événements serveur sans dépendre du récit du modèle. Le téléchargement manuel depuis la quarantaine n’est pas enregistré comme outil du modèle. Voir la [sémantique complète de quarantaine](../../docs/mail-quarantine.md).

Les outils intégrés sont `list_today_emails`, `read_cv`, `file_cv` et `forward_cv`. Leurs phases de disponibilité dépendent des listes de messages effectivement obtenues et des lectures enregistrées, pour éviter que le petit modèle devine les identifiants des pièces jointes. Les deux branches utilisent les mêmes règles de préparation. La visibilité d’un outil ne confère pas de droit ; chaque appel doit encore être vérifié au point d’exécution.

`file_cv` copie le PDF original et n’accepte ni octets générés par le modèle ni chemin arbitraire. `forward_cv` ne peut cibler que la boîte locale isolée préconfigurée, sans SMTP ni URL arbitraire. La branche de référence conserve les ACL sous-jacentes, mais n’applique pas les restrictions d’organisation/de tâche d’AgentFuse ; ce mode n’est disponible que dans les bases d’expériences indépendantes créées par l’administrateur. La boîte principale reste toujours protégée.

Les pièces jointes intégrées au chat, les bases de connaissances de projet, les anciens historiques et le RAG ne sont pas encore inclus dans le suivi réel des expositions : les entrées correspondantes sont donc refusées avant l’appel au modèle. L’import dans la messagerie est le point d’entrée PDF pris en charge. Les chats ouverts directement dans l’interface native sont soumis aux mêmes restrictions. Le frontend natif conserve sa marque L’Assistant ; ce n’est pas un substitut de chat réécrit.

Seul un administrateur Django peut publier une version de politique ; le modèle ne dispose d’aucun outil de modification des règles. Les règles initiales de classement interne et d’interdiction de transfert externe sont directement utilisables ; le formulaire permet d’ajouter des blocages de dossiers. Cette interface de messagerie ne propose pas de règles d’approbation. Le contrat cœur conserve `ask`, mais cet adaptateur n’implémente pas sa persistance ni sa reprise ; les règles correspondantes sont refusées lors de la publication.

Le contrat `pilot-v1` lie les champs `CopyFile`, `CopiedFile`, `TaskScope.file_grants` et `Policy.file_destinations`. L’adaptateur étend `SQLiteHost` pour les métadonnées/effets PDF via `_operation_facts` et `_execute_operation`, en réutilisant les transactions, ACL, politiques et audits sans introduire ces dépendances dans le cœur. Les droits de copie viennent exclusivement des dossiers internes configurés et du périmètre généré côté serveur.

L’installation native actuelle cible Fedora 44 x86-64/Python 3.14. PostgreSQL 18.6 est seulement extrait dans le répertoire du prototype et utilise le port dédié 15439. Tous les services écoutent uniquement sur la machine locale ; aucun téléchargement au démarrage. L’installation complète sur d’autres plateformes, ProConnect en production, une véritable messagerie administrative, les services de fichiers La Suite et la concurrence en cluster n’ont pas été validés.

Le redémarrage conserve les effets réels et clôt les tâches inachevées. L’arrêt du classement invalide les appels suivants, mais conserve les copies déjà validées. Une erreur du modèle ne peut pas être transformée en succès d’exécution ; l’exactitude du classement par spécialité reste à vérifier selon le besoin métier.
