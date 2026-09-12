"""Deterministic policy evaluation. All facts are verified by the host beforehand."""
from .contracts import CopyFile, CreateDocument, Decision, EvaluationRequest, ReadResource
from .wire import action_binding


class PolicyEvaluator:
    def evaluate(self, request: EvaluationRequest) -> Decision:
        r = EvaluationRequest.model_validate(request)
        a, s, p = r.action, r.snapshot, r.policy
        binding = action_binding(r)

        def result(outcome, reason, rules=()):
            return Decision(action_id=a.action_id, binding=binding, outcome=outcome,
                            reason_code=reason, rule_ids=tuple(rules), evidence_ids=())

        if s.scope.status != "active" or not s.scope.created_at <= s.now < s.scope.expires_at:
            return result("block", "task.inactive")
        if (not s.exposure.complete or not s.exposure.scans_complete
            or not s.authorization.checked_at <= s.now < s.authorization.valid_until
            or s.authorization.verdict == "unknown"):
            return result("block", "context.incomplete")
        if s.authorization.verdict != "permitted":
            return result("block", "permissions.denied")
        op = a.operation
        if isinstance(op, (ReadResource, CopyFile)):
            if r.resource_source is None or r.resource_source.resource != op.resource:
                return result("block", "context.incomplete")
            if op.resource not in s.scope.readable_resources:
                return result("block", "scope.expansion_required")
            classes = {r.resource_source.data_class}
        else:
            classes = {source.data_class for source in s.exposure.sources} or {"unknown"}
        if isinstance(op, (CreateDocument, CopyFile)):
            # CopyFile sends only the immutable original bytes; document.create
            # can contain anything seen by the model and uses cumulative exposure.
            org_grants = p.file_destinations if isinstance(op, CopyFile) else p.docs_destinations
            task_grants = s.scope.file_grants if isinstance(op, CopyFile) else s.scope.docs_grants
            org = [g for g in org_grants if g.destination == op.destination]
            task = [g for g in task_grants if g.destination == op.destination]
            if not org:
                return result("block", "policy.destination_denied")
            if not classes <= set(org[0].data_classes):
                return result("block", "policy.data_denied")
            if not task or not classes <= set(task[0].data_classes):
                return result("block", "scope.expansion_required")
        matched = []
        for rule in p.rules:
            if rule.capability != op.capability:
                continue
            if rule.data_classes and not classes.intersection(rule.data_classes):
                continue
            if rule.resource_ids and (not isinstance(op, (ReadResource, CopyFile)) or op.resource.resource_id not in rule.resource_ids):
                continue
            if rule.destination_ids and (not isinstance(op, (CreateDocument, CopyFile)) or op.destination.destination_id not in rule.destination_ids):
                continue
            matched.append(rule)
        denies = [rule.rule_id for rule in matched if rule.effect == "block"]
        if denies:
            return result("block", "policy.rule_denied", denies)
        asks = [rule.rule_id for rule in matched if rule.effect == "ask"]
        evidence_asks = [e.rule_id for e in s.evidence if e.rule_id in p.confirmation_rule_ids]
        if s.grant and (s.grant.binding != binding or s.grant.expires_at <= s.now):
            return result("block", "approval.stale")
        if asks or evidence_asks:
            if op.capability not in p.approvable_capabilities:
                return result("block", "policy.rule_denied", asks or evidence_asks)
            if not s.grant:
                return result("ask", "policy.confirmation_required" if asks else "evidence.confirmation_required", asks or evidence_asks)
        return result("allow", "policy.allowed")
