# Installer AgentFuse dans une application DINUM

AgentFuse s’installe comme **bibliothèque Python dans le backend de l’application qui exécute les outils de l’agent**. Le paquet distribué s’appelle `agentfuse-pilot`, le module importé `agentfuse`. Le cœur fonctionne dans le processus de l’application ; il ne démarre aucun serveur et n’appelle aucun modèle.

Cette procédure concerne le composant. Les commandes `tools/setup.py`, `tools/setup_mail.py`, `start.py`, `stop.py` et `agentfuse-ui` servent uniquement à la démonstration locale. Installer le cœur n’exige ni Qwen, ni llama.cpp, ni Ollama, ni le frontend de messagerie, ni PostgreSQL, ni Django. La dépendance Python obligatoire est `pydantic==2.13.4` ; Python 3.12 minimum est déclaré, et la validation actuelle utilise Python 3.14.

## 1. Livrer un paquet versionné

Construire les artefacts depuis la racine de ce dépôt :

```sh
python3 -m venv .venv-build
.venv-build/bin/python -m pip install build
.venv-build/bin/python -m build --outdir dist
sha256sum dist/agentfuse_pilot-0.1.0-py3-none-any.whl
```

Livrer le wheel, son empreinte par un canal de confiance, cette documentation et les exemples. Le sdist permet de reconstruire depuis les sources. `0.1.0` est la version du prototype dans `pyproject.toml` ; incrémenter la version avant chaque future livraison distincte. Aucun paquet public PyPI ni registre interne DINUM n’est supposé disponible.

## 2. Installer dans le backend destinataire

Vérifier l’artefact reçu puis l’ajouter aux dépendances et à la construction de l’image ou de l’environnement Python de l’application. Exemple dans un environnement dédié :

```sh
python3 -m venv .venv-agentfuse
.venv-agentfuse/bin/python -m pip install /chemin/livraison/agentfuse_pilot-0.1.0-py3-none-any.whl
.venv-agentfuse/bin/python -c 'import agentfuse; print(agentfuse.__version__, agentfuse.__file__)'
```

Pour une application existante, utiliser son interpréteur et son verrou de dépendances, puis vérifier la compatibilité de Pydantic avec le reste du backend. Ne pas installer le supplément `[app]` pour utiliser uniquement le cœur. Aucun fichier `.runtime/`, compte de démonstration, clé de modèle ou base SQLite de démonstration n’est nécessaire à cette installation.

Pour un environnement sans réseau, préparer les dépendances sur une machine correspondant au système, à l’architecture et à la version Python destinataires :

```sh
python3 -m pip download --only-binary=:all: --dest wheelhouse dist/agentfuse_pilot-0.1.0-py3-none-any.whl
```

Transférer le répertoire vérifié, puis installer avec l’interpréteur du backend destinataire :

```sh
python3 -m pip install --no-index --find-links=/chemin/wheelhouse agentfuse-pilot==0.1.0
```

Le wheel du projet est Python pur, mais certaines dépendances disposent de binaires propres à la plateforme. Un jeu de wheels préparé pour une autre plateforme n’est pas une livraison hors ligne valide.

## 3. Brancher le contrôle avant les effets

**Installer le paquet ne branche aucun outil automatiquement.** Le développeur de l’application doit adapter ses outils et fournir les ports décrits dans [`ports.py`](../src/agentfuse/ports.py). Le cœur vérifie les faits reçus ; il ne découvre pas les ACL de production.

| Responsabilité de l’application destinataire | Interface utilisée |
| --- | --- |
| Résoudre l’utilisateur connecté, la tâche et la conversation côté serveur ; transformer un outil connu en une action précise avec versions et destination configurée | `ActionMapper.normalize` → `Action` |
| Charger le périmètre de tâche, la politique, les ACL actuelles, les sources déjà vues et les preuves ; ne pas accepter ces faits du modèle | `HostPort.load_request` → `EvaluationRequest` |
| Persister la décision avant toute suite ; gérer l’arrêt et le signalement nécessaires à son métier | `HostPort.record_decision` |
| Sous verrou ou mécanisme équivalent, revérifier droits, versions, politique et unicité de l’exécution ; émettre un ticket lié à l’action | `HostPort.claim_execution` |
| Effectuer uniquement l’opération validée, avec le ticket serveur et les mêmes paramètres ; conserver les ACL du service cible | `Executor.execute` |
| Persister résultat, exposition, preuves et audit avant de rendre le contenu au modèle ; suspendre une exécution de résultat inconnu | `HostPort.record_result` |
| Si des règles `ask` sont nécessaires, authentifier la personne habilitée, persister l’action exacte et reprendre après nouvelle vérification | `HostPort.defer`, `HostPort.resolve_approval` |

Le point d’interception utilise les objets fournis par l’intégration de l’application, par exemple :

```python
from agentfuse.gate import dispatch
from agentfuse.policy import PolicyEvaluator

async def guarded_tool(tool_name, arguments_json, *, action_id,
                       actor_id, task_id, conversation_id, mapper, host, executor):
    action = mapper.normalize(
        tool_name, arguments_json, action_id=action_id, actor_id=actor_id,
        task_id=task_id, conversation_id=conversation_id,
    )
    return await dispatch(action, host=host,
                          evaluator=PolicyEvaluator(), executor=executor)
```

C’est un exemple de branchement, pas un connecteur DINUM déjà fourni : `mapper`, `host`, `executor` et les identités viennent du backend. Le modèle ne choisit que les paramètres métier autorisés. Après `dispatch`, le framework restitue le résultat contrôlé ou signale le blocage/l’attente ; **il ne rappelle pas l’outil original**, puisque `dispatch` a déjà invoqué l’exécuteur dans la branche autorisée.

L’application doit aussi suivre toute entrée de contenu avant exposition au modèle : historique, RAG, pièces jointes, résumés et caches inclus. Une entrée non couverte doit être désactivée ou refusée. Un scan sans signal n’accorde aucun droit. Avec un service externe, prévoir l’idempotence et la vérification des effets inconnus ; la transaction SQLite de l’adaptateur local ne fournit pas une transaction distribuée avec ce service.

## 4. Vérifier l’installation et l’intégration

Après installation, exécuter l’exemple livré avec les sources, depuis un répertoire extérieur au dépôt et sans `PYTHONPATH` vers `src/` :

```sh
/chemin/.venv-agentfuse/bin/python /chemin/livraison/examples/policy_check.py
```

Il évalue des faits fictifs, autorise une lecture dans le périmètre et bloque une lecture hors périmètre. Aucun outil n’est exécuté : cela valide l’import et le cœur installé, pas les ACL DINUM.

[`examples/embedded.py`](../examples/embedded.py) va plus loin avec l’adaptateur local `MailWorkspace` : vraie lecture PDF, copie des octets, blocage de transfert et quarantaine dans une base temporaire. Cet exemple exige `pdftotext` et `prlimit` disponibles dans le système ; il n’exige ni serveur ni modèle. Ses identités et fichiers sont fictifs et ne doivent pas remplacer les systèmes de production.

Avant d’activer une intégration destinataire, vérifier sur ses outils réels : parcours normal, lecture hors périmètre malgré une ACL favorable, refus par ACL, destination interdite même sans signal au scan, changement de politique entre décision et effet, répétition d’une même action, indisponibilité de l’audit, résultat externe inconnu et absence de parcours d’outil contournant `dispatch`. Les résultats du modèle ne remplacent pas les reçus du service cible.

## État de la livraison

Le cœur, les contrats `pilot-v1`, le paquet installable, l’hôte SQLite et la chaîne locale Conversations → PDF sont implémentés. `document.create` et `ask` restent des capacités du contrat et du moteur de politique, avec tests indépendants ; aucun exécuteur de documents ni circuit d’approbation métier n’est fourni dans l’application de messagerie. `SQLiteHost` refuse ces opérations non intégrées, et la configuration de messagerie refuse les règles `ask`.

Les connecteurs vers une messagerie DINUM réelle, ProConnect et les services de fichiers La Suite ne sont pas livrés. La procédure décrit l’installation de la bibliothèque et la construction d’une intégration ; elle ne constitue pas la validation d’un déploiement en production déjà réalisé. Voir les [responsabilités du code](architecture.md) et les [vérifications effectuées](mail-validation.md).
