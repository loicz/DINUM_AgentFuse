"""L’entrée ne fournit que la redirection et l’état du service."""
import httpx

from agentfuse.app import create_app


async def test_mail_entry_without_legacy_api_or_storage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),
                                 base_url='http://testserver') as client:
        assert (await client.get('/api/health')).json() == {'status': 'ok'}
        response = await client.get('/')
        assert response.status_code == 307
        assert response.headers['location'] == 'http://127.0.0.1:8071/mail/'
        assert response.headers['Cache-Control'] == 'no-store'
        assert (await client.get('/', headers={'Host': 'attacker.invalid'})).status_code == 400
        for path in ('/legacy', '/documents/old', '/static/app.js', '/api/resources',
                     '/api/tasks', '/api/documents/old', '/api/approvals', '/api/policy', '/api/demo'):
            assert (await client.get(path)).status_code == 404
        assert (await client.post('/api/login', json={'user': 'alice'})).status_code == 404
    assert list(tmp_path.iterdir()) == []
