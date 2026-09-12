"""Entrée HTTP de la démonstration ; aucune identité ni base métier ici."""
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware


def create_app():
    app = FastAPI(title='AgentFuse · messagerie', docs_url=None,
                  redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def boundaries(request, call_next):
        response = await call_next(request)
        response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/health')
    async def health():
        return {'status': 'ok'}

    @app.get('/')
    async def entry():
        return RedirectResponse('http://127.0.0.1:8071/mail/')

    return app
