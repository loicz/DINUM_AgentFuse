# Architecture et responsabilités

Le cœur est une bibliothèque Python. La messagerie locale est son application d’intégration ; elle utilise de vrais PDF et la véritable chaîne Conversations. Pour installer le composant dans une application existante, commencer par le [guide d’installation et de branchement](installation.md).

| Code | Responsabilité |
| --- | --- |
| `src/agentfuse/contracts.py`, `wire.py`, `ports.py` | Contrats `pilot-v1`, JSON strict, liaison des paramètres et interfaces de l’application hôte |
| `policy.py` | Évaluation déterministe `allow / block / ask`, sans accès au réseau, au modèle ou au stockage |
| `detection.py` | Motifs textuels auxiliaires en français/anglais, positions des signaux et suivi cumulatif des sources ; aucune autorisation accordée par le scan |
| `gate.py` | Ordre des ports et validation des décisions, tickets et résultats avant publication |
| `storage.py` | Schéma SQLite commun, transactions, identifiants et empreintes ; aucune donnée métier préchargée |
| `host.py` | `SQLiteHost` : faits fiables, lecture protégée, réservation d’exécution, relecture des conditions, reçu, exposition et audit atomiques |
| `mailbox.py` | `MailWorkspace` : initialisation locale, identités de test liées à Django, messages, PDF, destinations, copies, provenance et quarantaine |
| `mail_web/`, `assets/` | Interface de messagerie et police/licence partagées |
| `integrations/conversations/` | Connexion à Django/PydanticAI, outils, vues et expériences locales isolées |
| `app.py`, `cli.py` | Redirection HTTP vers la messagerie et `/api/health` ; aucune base ni API métier |
| `tools/` | Installation, services de démonstration, génération de PDF fictifs et validation |

`stop.py` délègue à `tools/manage.py` l'arrêt ordonné des services Linux de ce dépôt : entrée, frontend, backend, modèle, puis PostgreSQL. La vérification des processus et l'attente de leur sortie restent dans cet outillage, sans dépendance ajoutée au cœur. Voir la [procédure d'arrêt](../README.md#arrêter-la-démonstration).

`MailWorkspace` hérite de `SQLiteHost`, qui utilise `Database`. La spécialisation des métadonnées et des effets se fait par `_operation_facts` et `_execute_operation`. La mise en quarantaine utilise `_record_decision` dans la même transaction que l’audit du blocage. Les transactions restent dans l’adaptateur ; le cœur n’importe pas ces modules.

La chaîne actuelle est : demande utilisateur native → identité Django et périmètre généré par le serveur → outils PydanticAI → `MailWorkspace.perform` → `normalize` → `dispatch` → faits et politique → décision persistée → blocage, attente ou réservation → exécution vérifiée → résultat/exposition/audit → retour au modèle. Le branchement détaillé figure dans la [documentation Conversations](../integrations/conversations/README.md).

Les droits effectifs sont l’intersection des ACL de l’utilisateur, du périmètre de la tâche et de la politique. Les arguments du modèle ne peuvent créer ni droit, ni destination, ni version de ressource. Une copie transmet les octets originaux du PDF liés à leur empreinte complète ; elle ne transmet pas un texte généré par le modèle. Le contrat général `document.create`, destiné à un futur adaptateur de document, évalue au contraire toutes les classes de données déjà exposées. Il est testé dans le cœur mais n’est pas exposé par la messagerie.

`claim_execution` revérifie les faits et interdit un second lancement ; `execute` vérifie encore le ticket et les conditions avant l’effet. Dans cet hôte local, effet, reçu, scan et exposition sont enregistrés dans la même transaction. Le redémarrage réconcilie les reçus persistés et suspend les tâches interrompues, sans rejouer automatiquement les outils. Ces garanties SQLite ne s’étendent pas automatiquement à un service externe.

Le contrat `ask` exige un adaptateur d’approbation réel pour être utilisé. La messagerie n’en fournit pas : elle refuse les nouvelles politiques de confirmation et échoue sans effet si une ancienne politique en demande une. Les DTO d’approbation et leurs tests de liaison appartiennent au cœur ; aucune page, API, table ou exécution de l’ancien scénario documentaire n’est créée.

Les nouveaux répertoires d’exécution ne contiennent ni anciennes ressources textuelles, ni sessions locales distinctes de Django, ni base documentaire. Une ancienne base peut conserver des tables historiques supplémentaires : elles ne sont ni utilisées ni supprimées par l’ouverture du fichier. `.runtime/` et les environnements restent exclus du dépôt et de la distribution.

Les seuls connecteurs d’effet fournis concernent les lectures locales et les copies PDF vers des dossiers ou une boîte MIME locale isolée. ProConnect, SMTP, La Suite Docs, les chemins de contexte non interceptés et l’exploitation en cluster ne font pas partie des intégrations validées.

Les PDF de test sont déjà fournis. Leur script de régénération `tools/create_mail_fixtures.py` requiert ReportLab dans un environnement de développement séparé ; il n’est pas exécuté à l’installation ou au démarrage. Toute régénération modifie les empreintes des échantillons et impose une nouvelle validation des expériences.
