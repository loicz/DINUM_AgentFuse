# Rapport de provenance et quarantaine par défaut après blocage

Le traitement d’un incident suspend la tâche courante et signale les fichiers candidats ; seuls les PDF avec signal direct ou l’unique PDF lu sont isolés automatiquement. Ce comportement appartient à l’adaptateur de messagerie locale ; il conserve les contrats du cœur indépendants du stockage et de l’interface.

## Règles de traitement

1. Dans la branche protégée, les transferts externes interdits, y compris vers un destinataire non configuré, et les lectures hors périmètre ou sans droit sont arrêtés avant exécution. La provenance vient des lectures réelles enregistrées pour la tâche, des scans et du stockage de confiance des messages/PDF, jamais des déclarations du modèle.
2. Si des PDF lus présentent un signal `injection_pattern`, seuls ces PDF sont isolés ; les autres candidats restent visibles dans le rapport. Un signal de scan ne constitue pas une preuve de causalité.
3. Sans signal, si un seul PDF a été lu : l’isoler par précaution et indiquer explicitement que l’origine n’est pas confirmée. L’objet du transfert peut être un autre fichier ; cela ne justifie pas d’isoler cette cible non lue.
4. Sans signal, si plusieurs PDF ont été lus : signaler tous les candidats, suspendre la tâche et ne pas les isoler collectivement. Si aucun PDF n’a encore été lu, signaler que l’origine ne peut pas être déterminée.
5. Après un événement dangereux, l’état de la tâche est persisté à `cancelled` ; les outils suivants de cette exécution et les autorisations d’exécution déjà émises sont invalidés. Les autres tâches actives ayant lu les octets isolés sont également arrêtées. L’ancien contexte est conservé pour l’audit ; on ne tente pas de le nettoyer pour poursuivre. Une nouvelle tâche traite les fichiers restants.

La suspension administrative d’un dossier de classement interne, la fin normale ou l’expiration d’une tâche ne prouvent pas la présence d’une injection dans un PDF. Un nouvel accès à un fichier déjà isolé arrête la tâche, sans entraîner la quarantaine d’un autre PDF sain. Les appels invalides qui ne peuvent pas être normalisés en opération de fichier vérifiable restent signalés comme indisponibles, sans inventer de provenance ni de trace d’exécution.

## Stockage et accès

La quarantaine est un stockage logique SQLite, cohérent avec les BLOB de la messagerie et des archives existantes. Elle ne déplace pas de fichiers du système d’exploitation et ne supprime pas les enregistrements d’origine. `mail_quarantine` conserve la ressource, le SHA-256 complet, les octets originaux, le nom de fichier, l’instantané de provenance et le premier incident. `mail_incidents` conserve le motif du blocage, la cible de l’opération, les sources candidates, les éléments d’attribution, le résultat de quarantaine et l’état d’arrêt de la tâche.

L’hôte revérifie la décision et enregistre le blocage, l’événement de provenance, la quarantaine et l’arrêt dans une seule transaction. Un échec de l’audit/de la transaction empêche l’exécution de l’outil. Si l’intégrité des octets est anormale, le fichier reste exclu du traitement automatique, l’échec de vérification est signalé et le téléchargement est interdit ; on ne peut pas prétendre avoir conservé une copie valide.

La quarantaine s’applique selon l’empreinte complète des octets aux PDF ordinaires, à toutes les copies déjà classées, aux ZIP, aux outils suivants et aux imports répétés. Le message d’origine est conservé et marqué comme mis en quarantaine ; les listes et périmètres des nouvelles tâches excluent ces PDF. Les copies déjà téléchargées ailleurs ne peuvent pas être retirées, et la détection d’un fichier modifié puis réimporté n’est pas revendiquée.

L’inspection manuelle utilise l’entrée distincte `/local/quarantine/{id}/`. Elle exige une authentification réelle et les ACL actuelles de la ressource, renvoie le fichier en attachment, interdit l’intégration dans une page et la mise en cache, et enregistre le téléchargement. Cette entrée n’est pas proposée au modèle et ne lève pas la quarantaine. Aucun bouton de levée de quarantaine ni parcours de reprise après approbation n’existe actuellement. Les enregistrements de quarantaine et les droits d’accès de la boîte principale et des bases d’expériences restent séparés.

## Affichage et limites

Les alertes de la messagerie et **Activité de protection** lisent directement les événements serveur. Elles affichent le nom du fichier, l’ID/l’objet du message source, l’expéditeur, la réception, la version, le SHA-256 et les règles/positions de caractères du scan, sans dépendre de la fidélité du récit du modèle. **Quarantaine** fournit une liste persistante et un accès explicite au téléchargement manuel, également utilisables sur téléphone et après actualisation. Tous les noms, objets et textes de provenance externes sont échappés à l’affichage.

Les DTO cœur `Decision`/`Source` n’acquièrent aucune dépendance au stockage ou à l’interface. Seuls l’état HTTP et les retours d’outils de l’hôte local sont étendus. `SQLiteHost._record_decision` est un point d’extension d’adaptateur dans la même transaction ; l’ordre d’appel commun de `record_decision` ne change pas. Le cœur, l’adaptation des outils, l’interface utilisateur et l’association des sources conservent leurs responsabilités respectives.

Les trois anciennes comparaisons injectées réelles poursuivaient le classement des quatre CV après blocage. Ce sont des preuves figées de l’ancienne version, pas une validation de la quarantaine actuelle. La nouvelle démonstration distingue `normal_work_complete` — classement normal intégralement terminé — et `containment_demonstrated` — transfert externe réel bloqué, tâche arrêtée et sources signalées. Les tâches saines ordinaires doivent toujours achever le classement. Voir la [validation de la messagerie](mail-validation.md).
