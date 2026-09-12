"""Frontières de l’hôte SQLite sur les ressources PDF réellement utilisées."""
import asyncio
import sqlite3

import pytest

from agentfuse.contracts import Policy, PolicyRule
from agentfuse.host import SQLiteHost
from agentfuse.mailbox import MailWorkspace
from agentfuse.ports import HostConflict
from agentfuse.storage import packed
from agentfuse.wire import ContractError, parse_json


@pytest.fixture
def w(tmp_path):
    host = MailWorkspace(tmp_path / 'mail.sqlite')
    host.initialize(scenario='clean')
    return host


def task(w):
    return w.start_task('alice', 'Lire le CV sélectionné.', ['cv-noe-moreau'])


def action(w, t):
    return w.normalize(t, 'read_resource', {'resource_id': 'cv-noe-moreau'})


def count(w, table):
    assert table in ('effects', 'actions')
    with w.db() as c:
        return c.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]


async def test_scope_is_less_than_user_acl_and_scan_miss_still_blocks(w):
    result = await w.perform(task(w), 'read_resource', {'resource_id': 'cv-sarah-bernard'})
    assert result.decision.reason_code == 'scope.expansion_required'
    assert result.execution is None and count(w, 'effects') == 0


@pytest.mark.parametrize(('tool', 'args'), [
    ('read_resource', {'resource_id': 'cv-noe-moreau', 'authorized': True}),
    ('shell', {'command': 'commande fictive'}),
    ('create_document', {'destination_id': 'local-docs', 'title': 'Titre', 'content': 'Texte'}),
])
async def test_model_cannot_fabricate_scope_or_authorization(w, tool, args):
    with pytest.raises(HostConflict):
        await w.perform(task(w), tool, args)
    assert count(w, 'effects') == 0


async def test_user_acl_still_enforced_if_scope_is_broader(w):
    t = task(w)
    with w.db() as c:
        c.execute("UPDATE resources SET acl='[\"admin\"]' WHERE id='cv-noe-moreau'")
    result = await w.perform(t, 'read_resource', {'resource_id': 'cv-noe-moreau'})
    assert result.decision.reason_code == 'permissions.denied'
    assert count(w, 'effects') == 0


async def test_unknown_resource_fails_closed(w):
    result = await w.perform(task(w), 'read_resource', {'resource_id': 'absent'})
    assert result.decision.reason_code == 'context.incomplete'
    assert count(w, 'effects') == 0


@pytest.mark.parametrize('change', ['version', 'classification', 'acl'])
async def test_changed_source_invalidates_context(w, change):
    t = task(w)
    await w.perform(t, 'read_resource', {'resource_id': 'cv-noe-moreau'})
    statements = {
        'version': "UPDATE resources SET version='changed' WHERE id='cv-noe-moreau'",
        'classification': "UPDATE resources SET class='public',classification_version=2 WHERE id='cv-noe-moreau'",
        'acl': "UPDATE resources SET acl='[\"admin\"]' WHERE id='cv-noe-moreau'",
    }
    with w.db() as c:
        c.execute(statements[change])
    with pytest.raises(HostConflict):
        await w.perform(t, 'read_resource', {'resource_id': 'cv-noe-moreau'})
    assert count(w, 'effects') == 1


async def test_claim_rechecks_policy_and_blocks_race(w):
    a = action(w, task(w))
    request = await w.load_request(a)
    decision = w.evaluator.evaluate(request)
    await w.record_decision(a, decision)
    p = w.policy()
    rule = PolicyRule(rule_id='pause', label='Suspendre les lectures', effect='block', capability='resource.read')
    w.publish_policy('admin', packed(p.model_copy(update={'rules': (*p.rules, rule)})), p.policy_version)
    with pytest.raises(HostConflict):
        await w.claim_execution(request, decision)
    assert count(w, 'effects') == 0


async def test_concurrent_same_action_at_most_once(w):
    t = task(w)
    def attempt():
        return asyncio.run(w.perform(t, 'read_resource', {'resource_id': 'cv-noe-moreau'}, 'same-action'))
    results = await asyncio.gather(*(asyncio.to_thread(attempt) for _ in range(2)), return_exceptions=True)
    assert sum(isinstance(r, HostConflict) for r in results) == 1
    assert count(w, 'effects') == 1


async def test_audit_failure_prevents_effect(w):
    t = task(w)
    with w.db() as c:
        c.execute('DROP TABLE events')
    with pytest.raises(sqlite3.OperationalError):
        await w.perform(t, 'read_resource', {'resource_id': 'cv-noe-moreau'})
    assert count(w, 'effects') == count(w, 'actions') == 0


async def test_scan_failure_rolls_back_local_read_result(w, monkeypatch):
    t = task(w)
    before = w.task(t)['exposure']
    def broken(*args):
        raise RuntimeError('Scan indisponible')
    monkeypatch.setattr(w.scanner, 'scan_text', broken)
    result = await w.perform(t, 'read_resource', {'resource_id': 'cv-noe-moreau'})
    assert result.execution.status == 'execution_unknown'
    assert count(w, 'effects') == 0
    assert w.task(t)['status'] == 'failed' and w.task(t)['exposure'] == before


async def test_restart_reconciles_committed_effect_without_retry(w):
    t = task(w)
    a = action(w, t)
    request = await w.load_request(a)
    decision = w.evaluator.evaluate(request)
    await w.record_decision(a, decision)
    ticket = await w.claim_execution(request, decision)
    await w.execute(a, ticket)
    restarted = MailWorkspace(w.path)
    restarted.recover()
    assert count(w, 'effects') == 1
    assert w.task(t)['actions'][0]['status'] == 'succeeded'
    assert w.task(t)['status'] == 'failed'
    with pytest.raises(HostConflict):
        await restarted.execute(a, ticket)


def test_policy_admin_auth_and_optimistic_version(w):
    p = w.policy()
    with pytest.raises(HostConflict):
        w.publish_policy('alice', packed(p), p.policy_version)
    w.publish_policy('admin', packed(p), p.policy_version)
    with pytest.raises(HostConflict):
        w.publish_policy('admin', packed(p), p.policy_version)


def test_json_rejects_duplicate_keys(w):
    raw = packed(w.policy()).replace('"rules":', '"policy_version":"fake","rules":')
    with pytest.raises(ContractError):
        parse_json(Policy, raw)


def test_fresh_storage_contains_no_legacy_scenario(tmp_path, w):
    bare = SQLiteHost(tmp_path / 'bare.sqlite')
    with bare.db() as c:
        for table in ('users', 'resources', 'policies'):
            assert c.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
    with w.db() as c:
        tables = {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not {'sessions', 'documents', 'approvals'} & tables
        assert not c.execute("SELECT 1 FROM resources WHERE id LIKE 'brief-%'").fetchone()
        assert {r['name'] for r in c.execute('PRAGMA table_info(users)')} == {'id', 'name', 'role', 'active'}
    assert not {'login', 'session', 'add_resource', 'classify'} & set(dir(w))


async def test_mail_rejects_unintegrated_approval(w):
    p = w.policy()
    rule = PolicyRule(rule_id='review', label='Relecture', effect='ask', capability='resource.read')
    with pytest.raises(HostConflict):
        w.publish_policy('admin', packed(p.model_copy(update={'rules': (rule,)})), p.policy_version)
    # Une ancienne politique peut encore demander une confirmation : aucun effet.
    with w.db() as c:
        updated = p.model_copy(update={'rules': (rule,), 'approvable_capabilities': ('resource.read',)})
        c.execute('UPDATE policies SET body=?', (packed(updated),))
    with pytest.raises(HostConflict):
        await w.perform(task(w), 'read_resource', {'resource_id': 'cv-noe-moreau'})
    assert count(w, 'effects') == 0


def test_existing_database_extras_remain_untouched(w):
    with w.db() as c:
        c.execute('ALTER TABLE users ADD COLUMN salt TEXT')
        c.execute('ALTER TABLE users ADD COLUMN password TEXT')
        c.execute('CREATE TABLE documents(id TEXT, content TEXT)')
        c.execute("INSERT INTO documents VALUES('archive', 'Donnée historique')")
    reopened = MailWorkspace(w.path)
    reopened.initialize()
    with reopened.db() as c:
        assert c.execute('SELECT content FROM documents').fetchone()[0] == 'Donnée historique'
    assert reopened.pdf('alice', 'cv-noe-moreau')[0] == w.pdf('alice', 'cv-noe-moreau')[0]
