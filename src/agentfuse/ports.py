"""Interfaces structurelles ; aucune dépendance Django, pydantic-ai ou réseau."""

from typing import Protocol

from .contracts import (
    Action, ApprovalRequest, ApprovalResolution, Decision, EvaluationRequest,
    ExecutionResult, ExecutionTicket, ExposureState, ScanReport, Source,
)


class Unavailable(RuntimeError):
    """Dépendance non implémentée ou indisponible avant son invocation métier."""


class HostConflict(RuntimeError):
    """État/liaison périmé, exécution déjà réclamée ou audit indisponible : arrêt."""


class Scanner(Protocol):
    def scan_text(self, text: str, source: Source) -> ScanReport:
        """analyser uniquement le texte reçu, sans lire le stockage."""
        ...


class ExposureTracker(Protocol):
    def observe(self, state: ExposureState, report: ScanReport) -> ExposureState:
        """état cumulatif, révision croissante ; jamais effacer une classe."""
        ...


class Evaluator(Protocol):
    def evaluate(self, request: EvaluationRequest) -> Decision:
        """fonction pure, horloge dans snapshot ; aucune exécution ni I/O."""
        ...


class ActionMapper(Protocol):
    def normalize(self, tool_name: str, arguments_json: str, *, action_id: str,
                  actor_id: str, task_id: str, conversation_id: str) -> Action:
        """identités de l'hôte, arguments suspects ; résoudre versions et cible.

        Outil inconnu, effets multiples non couverts ou JSON ambigu : ContractError.
        Aucun accès au contenu ni appel externe pendant cette normalisation.
        """
        ...


class HostPort(Protocol):
    async def load_request(self, action: Action) -> EvaluationRequest:
        """recharger ACL/tâche/politique/exposition et vérifier tout grant serveur."""
        ...

    async def record_decision(self, action: Action, decision: Decision) -> None:
        """Persister avant attente ou exécution ; échec = pas de lancement."""
        ...

    async def defer(self, action: Action, decision: Decision) -> ApprovalRequest:
        """Persister l'action exacte et un checkpoint privé ; aucun effet métier."""
        ...

    async def resolve_approval(self, resolution: ApprovalResolution, *, actor_id: str) -> ApprovalRequest:
        """Authentifier, vérifier appartenance/binding/expiration ; clic répété idempotent.

        Ne lance rien : la reprise relit le checkpoint et réévalue l'action.
        """
        ...

    async def claim_execution(self, request: EvaluationRequest, decision: Decision) -> ExecutionTicket:
        """Revalider sous verrou, consommer le grant et enregistrer executing atomiquement.

        Un seul exécuteur par tâche ; vérifier versions, ACL actuelles, expiration,
        audit durable et absence de lancement antérieur. Sinon HostConflict.
        """
        ...

    async def record_result(self, ticket: ExecutionTicket, result: ExecutionResult) -> None:
        """Persister résultat, preuves ET exposition avant publication/outil suivant.

        Échec après lancement : conserver executing à réconcilier en unknown,
        suspendre la tâche et ne pas republier les données ni relancer l'outil.
        """
        ...


class Executor(Protocol):
    async def execute(self, action: Action, ticket: ExecutionTicket) -> ExecutionResult:
        """L’application fournit l’exécuteur et l’injecte dans dispatch sans doubler l’appel.

        Seul point d'effet : vérifier le ticket serveur et conserver les ACL.
        Lire la version exacte ou créer dans la cible exacte, avec les paramètres
        contrôlés. Les exceptions après invocation rendent l'effet inconnu.
        """
        ...
