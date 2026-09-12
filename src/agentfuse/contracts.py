"""Contrats pilot-v1 ; les règles d’appartenance ne remplacent pas les ACL.

Tous les champs sans défaut sont obligatoires. Les collections sont des tuples
immuables ; aucune entrée métier n'est un dictionnaire libre.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]
Revision = Annotated[int, Field(ge=1)]
Instant = Annotated[int, Field(ge=0, description="Secondes UTC depuis Unix, fournies par l'hôte.")]
Text = Annotated[str, Field(min_length=1, max_length=65536)]
Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
DataClass = Literal["public", "internal", "restricted", "unknown"]
Capability = Literal["resource.read", "document.create", "file.copy"]


class Contract(BaseModel):
    """Valeur stricte : champs supplémentaires et conversions implicites refusés."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, revalidate_instances="always",
        hide_input_in_errors=True,
    )


class ResourceRef(Contract):
    """Version opaque issue du stockage ; jamais le nom de fichier proposé par l'IA."""

    resource_id: Identifier
    content_version: Identifier


class DestinationRef(Contract):
    """Destination configurée et version vérifiée par l’application hôte."""

    destination_id: Identifier
    configuration_version: Identifier


class Source(Contract):
    source_id: Identifier
    resource: ResourceRef
    label: Annotated[str, Field(min_length=1, max_length=256)]
    instruction_trust: Literal["untrusted"]
    data_class: DataClass
    classification_origin: Literal["policy", "verified_user", "trusted_import", "conservative_default"]


class Evidence(Contract):
    """Position [start, end) en caractères Python du texte exact scanné, sans extrait."""

    evidence_id: Identifier
    rule_id: Identifier
    source_id: Identifier
    category: Literal["injection_pattern", "protected_content_match", "secret_pattern"]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def ordered_span(self) -> Self:
        if self.end <= self.start:
            raise ValueError("La fin doit suivre le début de la correspondance.")
        return self


class ScanReport(Contract):
    """Le scan concerne un texte, pas un parseur PDF, Office ou un verdict de sûreté."""

    source: Source
    scanner_version: Identifier
    status: Literal["not_scanned", "complete", "partial", "error", "unsupported"]
    total_chars: Annotated[int, Field(ge=0, le=65536)]
    scanned_chars: Annotated[int, Field(ge=0, le=65536)]
    findings: Annotated[tuple[Evidence, ...], Field(max_length=256)]

    @model_validator(mode="after")
    def coverage(self) -> Self:
        if self.scanned_chars > self.total_chars:
            raise ValueError("Couverture supérieure au texte reçu.")
        if self.status == "complete" and self.scanned_chars != self.total_chars:
            raise ValueError("Un scan complet doit couvrir tout le texte reçu.")
        if self.status in ("not_scanned", "unsupported") and (self.scanned_chars or self.findings):
            raise ValueError("Aucune correspondance ne peut provenir d'un scan non effectué.")
        if len({e.evidence_id for e in self.findings}) != len(self.findings):
            raise ValueError("Identifiants de preuves dupliqués.")
        if any(e.source_id != self.source.source_id or e.end > self.scanned_chars for e in self.findings):
            raise ValueError("Preuve hors de la source ou de la couverture annoncée.")
        return self


class ExposureState(Contract):
    """Sources déjà accessibles au modèle ; une liste vide ne prouve pas la complétude."""

    task_id: Identifier
    revision: Revision
    sources: Annotated[tuple[Source, ...], Field(max_length=128)]
    complete: bool
    scans_complete: bool

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len({s.source_id for s in self.sources}) != len(self.sources):
            raise ValueError("Une source ne doit apparaître qu'une fois.")
        return self


class ReadResource(Contract):
    capability: Literal["resource.read"]
    resource: ResourceRef


class CreateDocument(Contract):
    """Création ET transmission du titre/contenu à cette destination Docs uniquement."""

    capability: Literal["document.create"]
    destination: DestinationRef
    title: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[^\x00-\x1f/\\]+$")]
    content: Text


class CopyFile(Contract):
    """Copie des octets exacts d'une pièce jointe vers un dossier/destinataire configuré.

    Le digest est vérifié par le stockage. Aucun chemin, URL ou contenu arbitraire.
    Une destination de type outbox implique la transmission du PDF entier.
    """
    capability: Literal["file.copy"]
    resource: ResourceRef
    destination: DestinationRef
    filename: Annotated[str, Field(min_length=5, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*\.pdf$")]
    sha256: Digest


Operation = Annotated[ReadResource | CreateDocument | CopyFile, Field(discriminator="capability")]


class Action(Contract):
    """Un seul effet métier entièrement décrit ; aucun appel arbitraire ni URL libre."""

    action_id: Identifier
    actor_id: Identifier
    task_id: Identifier
    conversation_id: Identifier
    mapping_version: Literal["pilot-v1"]
    operation: Operation


class DocsGrant(Contract):
    destination: DestinationRef
    data_classes: Annotated[tuple[DataClass, ...], Field(min_length=1, max_length=4)]


class TaskScope(Contract):
    task_id: Identifier
    actor_id: Identifier
    conversation_id: Identifier
    scope_version: Revision
    status: Literal["active", "completed", "cancelled", "expired"]
    readable_resources: Annotated[tuple[ResourceRef, ...], Field(max_length=128)]
    docs_grants: Annotated[tuple[DocsGrant, ...], Field(max_length=16)]
    file_grants: Annotated[tuple[DocsGrant, ...], Field(max_length=16)] = ()
    created_at: Instant
    expires_at: Instant

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("La tâche doit avoir une durée positive.")
        return self


class AuthorizationSnapshot(Contract):
    """ACL de l'opération entière, vérifiée sans charger le contenu du document."""

    action_id: Identifier
    actor_id: Identifier
    task_id: Identifier
    permissions_version: Identifier
    verdict: Literal["permitted", "denied", "unknown"]
    checked_at: Instant
    valid_until: Instant

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.valid_until <= self.checked_at:
            raise ValueError("La fraîcheur ACL doit avoir une durée positive.")
        return self


class PolicyRule(Contract):
    rule_id: Identifier
    label: Annotated[str, Field(min_length=1, max_length=160)]
    effect: Literal["block", "ask"]
    capability: Capability
    data_classes: Annotated[tuple[DataClass, ...], Field(max_length=4)] = ()
    resource_ids: Annotated[tuple[Identifier, ...], Field(max_length=128)] = ()
    destination_ids: Annotated[tuple[Identifier, ...], Field(max_length=16)] = ()


class Policy(Contract):
    """Configuration minimale : absence d'une destination/classe = interdiction ferme."""

    rules: Annotated[tuple[PolicyRule, ...], Field(max_length=64)] = ()
    policy_version: Identifier
    docs_destinations: Annotated[tuple[DocsGrant, ...], Field(max_length=16)]
    file_destinations: Annotated[tuple[DocsGrant, ...], Field(max_length=16)] = ()
    approvable_capabilities: Annotated[tuple[Capability, ...], Field(max_length=3)]
    confirmation_rule_ids: Annotated[tuple[Identifier, ...], Field(max_length=128)]


class ValidatedActionGrant(Contract):
    """Résultat d'une vérification serveur ; ce DTO n'authentifie pas une approbation."""

    approval_id: Identifier
    binding: Digest
    expires_at: Instant


class SecuritySnapshot(Contract):
    scope: TaskScope
    authorization: AuthorizationSnapshot
    exposure: ExposureState
    evidence: Annotated[tuple[Evidence, ...], Field(max_length=256)]
    grant: ValidatedActionGrant | None
    now: Instant


class EvaluationRequest(Contract):
    resource_source: Source | None = None
    schema_version: Literal["pilot-v1"]
    action: Action
    snapshot: SecuritySnapshot
    policy: Policy

    @model_validator(mode="after")
    def ownership(self) -> Self:
        a, s = self.action, self.snapshot
        if (a.task_id, a.actor_id, a.conversation_id) != (
            s.scope.task_id, s.scope.actor_id, s.scope.conversation_id
        ):
            raise ValueError("Action et tâche de propriétaires différents.")
        if (a.action_id, a.task_id, a.actor_id) != (
            s.authorization.action_id, s.authorization.task_id, s.authorization.actor_id
        ) or s.exposure.task_id != a.task_id:
            raise ValueError("ACL ou exposition étrangères à l'action.")
        if any(e.source_id not in {source.source_id for source in s.exposure.sources} for e in s.evidence):
            raise ValueError("Preuve sans source exposée dans cette tâche.")
        return self


Reason = Literal[
    "policy.allowed", "context.incomplete", "task.inactive", "permissions.denied",
    "policy.destination_denied", "policy.data_denied", "scope.expansion_required",
    "evidence.confirmation_required", "approval.stale", "policy.rule_denied", "policy.confirmation_required",
]


class Decision(Contract):
    """Le binding relie cette décision à l'action et à ses versions de sécurité."""

    action_id: Identifier
    binding: Digest
    outcome: Literal["allow", "block", "ask"]
    reason_code: Reason
    rule_ids: Annotated[tuple[Identifier, ...], Field(max_length=128)]
    evidence_ids: Annotated[tuple[Identifier, ...], Field(max_length=256)]

    @model_validator(mode="after")
    def reason_matches(self) -> Self:
        if (self.outcome == "allow") != (self.reason_code == "policy.allowed"):
            raise ValueError("Seul allow peut et doit utiliser policy.allowed.")
        if self.outcome == "ask" and self.reason_code not in (
            "scope.expansion_required", "evidence.confirmation_required", "policy.confirmation_required"
        ):
            raise ValueError("Une interdiction ferme ne peut pas devenir une approbation.")
        return self


class ApprovalRequest(Contract):
    """Vue privée, réservée au propriétaire ; ne pas diffuser dans un événement public."""

    approval_id: Identifier
    action: Action
    decision: Decision
    expires_at: Instant
    status: Literal["pending", "approved", "denied", "expired", "cancelled", "consumed", "invalidated"]

    @model_validator(mode="after")
    def pending_action(self) -> Self:
        if self.decision.outcome != "ask" or self.decision.action_id != self.action.action_id:
            raise ValueError("L'approbation doit décrire l'action mise en attente.")
        return self


class ApprovalResolution(Contract):
    """Entrée navigateur ; identité et action sont relues côté serveur, jamais ici."""

    approval_id: Identifier
    binding: Digest
    choice: Literal["approve", "deny"]


class ExecutionTicket(Contract):
    """Reçu serveur d'une prise atomique ; l'exécuteur doit le vérifier auprès de l'hôte."""

    ticket_id: Identifier
    action_id: Identifier
    binding: Digest


class ReadResult(Contract):
    kind: Literal["resource.read"]
    text: Annotated[str, Field(max_length=65536)]
    scan: ScanReport

    @model_validator(mode="after")
    def text_coverage(self) -> Self:
        if len(self.text) != self.scan.total_chars:
            raise ValueError("Le rapport doit décrire le texte exact retourné.")
        return self


class CreatedDocument(Contract):
    kind: Literal["document.create"]
    destination: DestinationRef
    document_id: Identifier
    document_url: Annotated[str, Field(max_length=2048, pattern=r"^(https://[^\s]+|/documents/[A-Za-z0-9._:-]+)$")]


class CopiedFile(Contract):
    kind: Literal["file.copy"]
    resource: ResourceRef
    destination: DestinationRef
    filename: str
    sha256: Digest
    copy_id: Identifier


class ExecutionSuccess(Contract):
    status: Literal["succeeded"]
    result: Annotated[ReadResult | CreatedDocument | CopiedFile, Field(discriminator="kind")]


class ExecutionFailure(Contract):
    """failed : échec connu ; execution_unknown : vérifier l'effet avant toute reprise."""

    status: Literal["failed", "execution_unknown"]
    error_code: Literal["resource.missing", "resource.changed", "permissions.denied", "scan.incomplete", "service.unavailable", "execution.error"]


ExecutionResult = Annotated[ExecutionSuccess | ExecutionFailure, Field(discriminator="status")]


class DecisionEvent(Contract):
    kind: Literal["decision_made"]
    decision: Decision


class ExecutionEvent(Contract):
    """Résumé sans texte, titre, URL, paramètres ou jeton d'accès."""

    kind: Literal["execution_finished"]
    status: Literal["succeeded", "failed", "execution_unknown"]


class SecurityEvent(Contract):
    schema_version: Literal["pilot-v1"]
    type: Literal["security"]
    event_id: Identifier
    task_id: Identifier
    conversation_id: Identifier
    action_id: Identifier
    sequence: Revision
    created_at: Instant
    payload: Annotated[DecisionEvent | ExecutionEvent, Field(discriminator="kind")]

    @model_validator(mode="after")
    def same_action(self) -> Self:
        if isinstance(self.payload, DecisionEvent) and self.payload.decision.action_id != self.action_id:
            raise ValueError("Décision étrangère à l'événement.")
        return self
