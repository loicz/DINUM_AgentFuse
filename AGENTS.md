# Instructions de développement

Ce dépôt contient le composant AgentFuse et son intégration locale de messagerie avec Conversations. Lire le [README](README.md), le [guide d’installation du composant](docs/installation.md), puis les [responsabilités du code](docs/architecture.md).

- Présenter AgentFuse comme un projet autonome, sans attribution personnelle ni répartition du travail. Conserver les mentions de licence des dépendances tierces.
- Écrire les commentaires, messages ajoutés et documents explicatifs en français. Les identifiants Python et les noms de contrats restent stables. Les archives traduites sont des éditions de publication, jamais des flux bruts : consigner la transformation et les empreintes dans les [notes de publication des preuves](docs/evidence/mail/README.md). Ne pas modifier les paramètres, décisions ou reçus d’effets des expériences historiques.
- Le cœur (`contracts`, `wire`, `ports`, `policy`, `detection`, `gate`) ne dépend ni de Django, ni du modèle, ni de SQLite, ni du réseau. Les adaptations métier appartiennent à `host.py`, `mailbox.py` et `integrations/`.
- Les droits proviennent du serveur : ACL de l’utilisateur ∩ périmètre de tâche ∩ politique. Le modèle ne peut agrandir aucun de ces ensembles. Aucune opération non intégrée ne doit être autorisée implicitement.
- Préserver l’ordre décision persistée → réservation et revérification → effet → reçu/exposition/audit. Ne jamais appeler l’outil une seconde fois après `dispatch`.
- Préserver la provenance, l’arrêt et les règles de [quarantaine](docs/mail-quarantine.md). Un blocage ne prouve pas à lui seul quel fichier a causé une injection.
- Ne pas recréer l’ancien scénario documentaire, ses API ou son exécuteur. Les contrats génériques `document.create` et `ask` ne prouvent pas l’existence de ces intégrations.
- Ne pas inclure `.runtime/`, environnements, clés ou bases d’utilisation dans une livraison. Préserver les données existantes ; les essais et constructions temporaires vont de préférence dans `/tmp`.
- L’amont Conversations est une dépendance externe fixée par l’installateur. Maintenir les adaptations reproductibles dans `tools/patch_conversations.py` et `integrations/conversations/`.
- Une demande de lecture, de revue ou d’explication n’autorise pas les modifications. Ne pas modifier des fichiers sans rapport avec le travail demandé, ni démarrer des sous-agents sans demande explicite.
- Après une modification, exécuter les tests concernés et mettre à jour les documents affectés. Distinguer tests déterministes, essais du vrai modèle, preuves historiques et intégrations de production non réalisées.

Commandes de validation : [README](README.md#validation). Les tests d’identité et d’HTTP réel utilisent l’environnement Conversations ; les tests du paquet doivent importer depuis `site-packages`, sans `PYTHONPATH` vers les sources.
