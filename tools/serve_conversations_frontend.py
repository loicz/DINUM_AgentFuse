"""Serve the actual built Conversations SPA locally, including deep links."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]/'.runtime/conversations/src/frontend/apps/conversations/dist'


class SPAHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/' or path=='/chat' or path.startswith('/chat/') or path in ('/home','/login','/unauthorized'):
            self.path='/index.html'
        super().do_GET()

    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()

    def log_message(self,*args):pass


if __name__=='__main__':
    if not (ROOT/'index.html').exists():raise SystemExit('Build the Conversations frontend first.')
    print('Actual Conversations frontend: http://127.0.0.1:3000',flush=True)
    ThreadingHTTPServer(('127.0.0.1',3000),partial(SPAHandler,directory=str(ROOT))).serve_forever()
