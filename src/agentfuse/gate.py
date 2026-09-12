"""Ordre minimal d'appel des ports ; pas un adaptateur pydantic-ai opérationnel."""

from dataclasses import dataclass

from pydantic import TypeAdapter

from .contracts import (
    Action, ApprovalRequest, CreateDocument, CreatedDocument, Decision,
    EvaluationRequest, ExecutionFailure, ExecutionResult, ExecutionSuccess,
    ExecutionTicket, ReadResource, ReadResult, CopyFile, CopiedFile,
)
from .ports import Evaluator, Executor, HostConflict, HostPort, Unavailable
from .wire import action_binding

_result_adapter = TypeAdapter(ExecutionResult)


@dataclass(frozen=True)
class DispatchResult:
    decision: Decision
    approval: ApprovalRequest | None = None
    execution: ExecutionResult | None = None


def _check_allow(request: EvaluationRequest) -> None:
    """Garde de cohérence minimale ; la politique et le claim restent indispensables."""
    snapshot = request.snapshot
    if (snapshot.scope.status != "active"
        or not snapshot.scope.created_at <= snapshot.now < snapshot.scope.expires_at
        or not snapshot.authorization.checked_at <= snapshot.now < snapshot.authorization.valid_until
        or snapshot.authorization.verdict != "permitted"
        or not snapshot.exposure.complete or not snapshot.exposure.scans_complete):
        raise HostConflict("Un allow contredit le contexte de sécurité minimal.")


def _check_result(action: Action, result: ExecutionResult) -> ExecutionResult:
    if isinstance(result, ExecutionSuccess):
        op, value = action.operation, result.result
        if isinstance(op, ReadResource):
            valid = isinstance(value, ReadResult) and value.scan.source.resource == op.resource
        elif isinstance(op, CopyFile):
            valid = (isinstance(value, CopiedFile) and value.resource == op.resource
                     and value.destination == op.destination and value.sha256 == op.sha256
                     and value.filename == op.filename)
        else:
            valid = isinstance(op, CreateDocument) and isinstance(value, CreatedDocument) and value.destination == op.destination
        if not valid:
            raise HostConflict("Résultat étranger à l'action exécutée.")
        if isinstance(value, ReadResult) and value.scan.status != "complete":
            return ExecutionFailure(status="failed", error_code="scan.incomplete")
    return result


async def dispatch(action: Action, *, host: HostPort, evaluator: Evaluator, executor: Executor) -> DispatchResult:
    """Aucun port par défaut ; l’application fournit les faits et l’exécution."""
    action = Action.model_validate(action)
    request = EvaluationRequest.model_validate(await host.load_request(action))
    if request.action != action:
        raise HostConflict("L'hôte a remplacé l'action proposée.")
    decision = Decision.model_validate(evaluator.evaluate(request))
    binding = action_binding(request)
    if decision.action_id != action.action_id or decision.binding != binding:
        raise HostConflict("Décision étrangère à l'action ou au contexte.")
    if not set(decision.evidence_ids) <= {e.evidence_id for e in request.snapshot.evidence}:
        raise HostConflict("La décision cite une preuve absente.")
    await host.record_decision(action, decision)
    if decision.outcome == "block":
        return DispatchResult(decision)
    if decision.outcome == "ask":
        approval = ApprovalRequest.model_validate(await host.defer(action, decision))
        if (approval.action != action or approval.decision != decision
            or approval.status != "pending" or approval.expires_at <= request.snapshot.now
            or approval.expires_at > request.snapshot.scope.expires_at):
            raise HostConflict("Mise en attente incohérente.")
        return DispatchResult(decision, approval=approval)
    _check_allow(request)
    ticket = ExecutionTicket.model_validate(await host.claim_execution(request, decision))
    if ticket.action_id != action.action_id or ticket.binding != binding:
        raise HostConflict("Ticket étranger à l'action.")
    try:
        result = await executor.execute(action, ticket)
        # Révalidation du retour : un objet de test ou model_construct n'est pas fiable.
        result = _result_adapter.validate_python(result)
        result = _check_result(action, result)
    except Unavailable:
        # Le port réserve cette exception à une indisponibilité AVANT tout effet.
        result = ExecutionFailure(status="failed", error_code="service.unavailable")
    except Exception:
        # L'invocation a commencé : ni un timeout ni une réponse invalide ne prouvent
        # l'absence d'effet. Ne pas exposer de message d'exception contenant du texte.
        result = ExecutionFailure(status="execution_unknown", error_code="execution.error")
    await host.record_result(ticket, result)
    return DispatchResult(decision, execution=result)
