"""Explicit localhost profile of the real Conversations application."""
import os
from pathlib import Path

from conversations.settings import Base

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.runtime'


class LocalMail(Base):
    DEBUG = False
    ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
    SECRET_KEY = (RUNTIME / 'conversations.key').read_text().strip()
    ROOT_URLCONF = 'local_urls'
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql', 'NAME': 'agentfuse_conversations',
        'USER': 'agentfuse', 'PASSWORD': (RUNTIME / 'postgres.key').read_text().strip(),
        'HOST': '127.0.0.1', 'PORT': 15439,
    }}
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'
    SESSION_COOKIE_NAME = 'conversations_sessionid'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_NAME = 'csrftoken'
    CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:3000', 'http://127.0.0.1:8787']
    CORS_ALLOWED_ORIGINS = CSRF_TRUSTED_ORIGINS
    LANGUAGE_CODE = 'fr-fr'
    TIME_ZONE = 'Europe/Paris'
    AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.ModelBackend']
    REST_FRAMEWORK = dict(Base.REST_FRAMEWORK, DEFAULT_AUTHENTICATION_CLASSES=(
        'rest_framework.authentication.SessionAuthentication',))
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
    MEDIA_ROOT = str(RUNTIME / 'conversations-media')
    STATIC_ROOT = str(RUNTIME / 'conversations-static')
    FRONTEND_HOMEPAGE_FEATURE_ENABLED = False
    FRONTEND_SILENT_LOGIN_ENABLED = False
    LOGIN_REDIRECT_URL = 'http://127.0.0.1:3000/'
    LOGIN_REDIRECT_URL_FAILURE = 'http://127.0.0.1:8787/'
    LOGOUT_REDIRECT_URL = 'http://127.0.0.1:8787/'
    AI_MODEL = 'agentfuse-local'
    AI_BASE_URL = 'http://127.0.0.1:18081/v1'
    AI_API_KEY = (RUNTIME / 'model.key').read_text().strip()
    _llm_configuration_file_path = str(ROOT / 'integrations/conversations/llm.json')
    AI_AGENT_TOOLS = []
    WARNING_MOCK_CONVERSATION_AGENT = False
    LANGFUSE_ENABLED = False
    SENTRY_DSN = None
    POSTHOG_KEY = None
    CELERY_TASK_ALWAYS_EAGER = True
    AGENTFUSE_MAIL_ENABLED = True
