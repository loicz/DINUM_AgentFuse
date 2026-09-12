"""Adaptateur local installé : vraies lectures et copies PDF, sans LLM ni serveur.

Cet exemple utilise des identités fictives ; le guide installation.md décrit
les responsabilités d’un adaptateur pour une application existante.
"""
import asyncio
from pathlib import Path
import tempfile

from agentfuse.mailbox import EXTERNAL_RECIPIENT, MailWorkspace


async def main():
    with tempfile.TemporaryDirectory(prefix='agentfuse-example-') as folder:
        host = MailWorkspace(Path(folder) / 'mail.sqlite')
        host.initialize(scenario='clean')
        host.bind_identity('identite-de-test', 'alice')
        task = host.conversation_task('identite-de-test', 'conversation-de-test', 'Classer les CV.')
        read = await host.perform(task, 'read_resource', {'resource_id': 'cv-noe-moreau'})
        assert read.execution.status == 'succeeded'
        saved = await host.perform(task, 'file_cv', {'attachment_id': 'cv-noe-moreau', 'folder': 'droit'})
        assert saved.execution.status == 'succeeded'
        assert host.copy_file('alice', saved.execution.result.copy_id)[0] == host.pdf('alice', 'cv-noe-moreau')[0]
        denied = await host.perform(task, 'forward_cv', {
            'attachment_id': 'cv-noe-moreau', 'recipient': EXTERNAL_RECIPIENT})
        assert denied.decision.outcome == 'block' and denied.execution is None
        assert host.task(task)['status'] == 'cancelled'
        assert len(host.view('alice')['quarantine']) == 1
        print('Lecture, copie PDF exacte, blocage, arrêt et quarantaine vérifiés.')


if __name__ == '__main__':
    asyncio.run(main())
