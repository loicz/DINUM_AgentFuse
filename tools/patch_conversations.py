"""Apply small reviewable integration edits to the isolated pinned copy only."""
from pathlib import Path
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
UPSTREAM=ROOT/'.runtime/conversations'


def replace(relative,old,new):
    path=UPSTREAM/relative;text=path.read_text()
    if new in text:return
    if text.count(old)!=1:raise SystemExit('Unexpected pinned source: '+relative)
    path.write_text(text.replace(old,new))


def main():
    client='src/backend/chat/clients/pydantic_ai.py'
    replace(client,'                async for event in self._run_agent(messages, force_web_search):\n',
        '                run_events = self._run_agent(messages, force_web_search)\n'
        '                if getattr(settings, "AGENTFUSE_MAIL_ENABLED", False):\n'
        '                    from mail_tools import guarded_stream\n'
        '                    run_events = guarded_stream(self, run_events)\n'
        '                async for event in run_events:\n')
    replace(client,'        history = ModelMessagesTypeAdapter.validate_python(self.conversation.pydantic_messages)\n',
        '        if getattr(settings, "AGENTFUSE_MAIL_ENABLED", False):\n'
        '            from mail_tools import validate_input\n'
        '            await validate_input(self, messages)\n\n'
        '        history = ModelMessagesTypeAdapter.validate_python(self.conversation.pydantic_messages)\n')
    replace(client,'        doc_result = None\n',
        '        if getattr(settings, "AGENTFUSE_MAIL_ENABLED", False):\n'
        '            from mail_tools import register\n'
        '            await register(self, user_prompt)\n\n'
        '        doc_result = None\n')
    replace(client,'        self._setup_self_documentation_tool()\n',
        '        if not getattr(settings, "AGENTFUSE_MAIL_ENABLED", False):\n'
        '            self._setup_self_documentation_tool()\n')
    replace(client,'        async for event in self._finalize_conversation(\n',
        '        if getattr(settings, "AGENTFUSE_MAIL_ENABLED", False):\n'
        '            from mail_tools import finish\n'
        '            await finish(self, run_output)\n\n'
        '        async for event in self._finalize_conversation(\n')
    replace(client,'            for translated in translator.flush():\n',
        '            finally:\n'
        '                if getattr(settings, "AGENTFUSE_MAIL_ENABLED", False):\n'
        '                    from mail_tools import interrupted\n'
        '                    await interrupted(self)\n\n'
        '            for translated in translator.flush():\n')
    replace('src/frontend/apps/conversations/src/features/chat/components/Chat.tsx',
        "  const [input, setInput] = useState('');",
        "  const [input, setInput] = useState(() => new URLSearchParams(window.location.search).get('mail_prompt')?.slice(0, 8000) || '');")
    app=UPSTREAM/'src/frontend/apps/conversations'
    replace('src/frontend/apps/conversations/src/features/chat/components/InputChat.tsx',
        "  const fileUploadEnabled = useFeatureEnabled('document-upload');",
        "  const documentUploadEnabled = useFeatureEnabled('document-upload');\n  const fileUploadEnabled = documentUploadEnabled && !import.meta.env.VITE_AGENTFUSE_MAIL;")
    for suffix,filename in [('UcCm3FwrK3iLTcvnUwQT9g','Inter-italic'),('UcCo3FwrK3iLTcviYwY','Inter-normal')]:
        replace('src/frontend/apps/conversations/src/cunningham/cunningham-style.css',
            f'https://fonts.gstatic.com/s/inter/v18/{suffix}.woff2',f'/fonts/{filename}.woff2')
    shutil.copytree(ROOT/'integrations/conversations/assets/fonts',app/'public/fonts',dirs_exist_ok=True)
    (app/'.env.local').write_text('VITE_API_ORIGIN=http://127.0.0.1:8071\nVITE_AGENTFUSE_MAIL=1\n')
    print('Pinned Conversations: tool registration, completion, local prompt prefill applied.')

if __name__=='__main__':main()
