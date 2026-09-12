"""Évaluation du cœur installé, sans modèle, base de données ni application web.

Les faits sont fictifs pour cet exemple. En production, l’hôte doit les charger
et les vérifier auprès des systèmes d’identité, de permissions et de stockage.
"""
from agentfuse.contracts import (
    Action, AuthorizationSnapshot, EvaluationRequest, ExposureState, Policy,
    ReadResource, ResourceRef, SecuritySnapshot, Source, TaskScope,
)
from agentfuse.policy import PolicyEvaluator


def example_request():
    resource = ResourceRef(resource_id='cv-exemple', content_version='version-1')
    action = Action(action_id='lecture-1', actor_id='agent-exemple', task_id='tri-1',
                    conversation_id='conversation-1', mapping_version='pilot-v1',
                    operation=ReadResource(capability='resource.read', resource=resource))
    scope = TaskScope(task_id=action.task_id, actor_id=action.actor_id,
                      conversation_id=action.conversation_id, scope_version=1,
                      status='active', readable_resources=(resource,), docs_grants=(),
                      created_at=100, expires_at=200)
    authorization = AuthorizationSnapshot(action_id=action.action_id, actor_id=action.actor_id,
                                         task_id=action.task_id, permissions_version='acl-1',
                                         verdict='permitted', checked_at=100, valid_until=130)
    source = Source(source_id='source-1', resource=resource, label='CV fictif',
                    instruction_trust='untrusted', data_class='restricted', classification_origin='policy')
    return EvaluationRequest(
        schema_version='pilot-v1', action=action, resource_source=source,
        policy=Policy(policy_version='politique-1', docs_destinations=(),
                      approvable_capabilities=(), confirmation_rule_ids=()),
        snapshot=SecuritySnapshot(scope=scope, authorization=authorization,
                                  exposure=ExposureState(task_id=action.task_id, revision=1, sources=(),
                                                         complete=True, scans_complete=True),
                                  evidence=(), grant=None, now=110))


def main():
    request = example_request()
    evaluator = PolicyEvaluator()
    assert evaluator.evaluate(request).outcome == 'allow'
    restricted_scope = request.snapshot.scope.model_copy(update={'readable_resources': ()})
    denied = request.model_copy(update={'snapshot': request.snapshot.model_copy(update={'scope': restricted_scope})})
    assert evaluator.evaluate(denied).reason_code == 'scope.expansion_required'
    print('Cœur installé : lecture autorisée et lecture hors périmètre bloquée ; aucun outil exécuté.')


if __name__ == '__main__':
    main()
