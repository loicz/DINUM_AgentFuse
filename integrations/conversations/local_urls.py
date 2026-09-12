"""Local password login; all chat endpoints remain upstream Conversations views."""
import json

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.urls import include, path
from django.views.decorators.http import require_http_methods


@require_http_methods(['GET', 'POST'])
def local_session(request):
    if request.method == 'GET':
        return JsonResponse({'authenticated': request.user.is_authenticated, 'csrf': get_token(request)})
    if len(request.body) > 4096:
        return JsonResponse({'detail': 'Requête trop volumineuse.'}, status=413)
    try:
        body = json.loads(request.body)
        name = body['user']
        if name not in ('alice', 'marie', 'admin'):
            raise ValueError()
        user = authenticate(request, username=name+'@demo.invalid', password=body['password'])
    except (ValueError, KeyError, TypeError):
        user = None
    if not user:
        return JsonResponse({'detail': 'Identifiants incorrects.'}, status=401)
    login(request, user)
    response=JsonResponse({'authenticated': True, 'csrf': get_token(request), 'id': str(user.pk)})
    response.set_cookie('conversations_language','fr',samesite='Lax')
    return response


def local_authenticate(request):
    return HttpResponseRedirect('http://127.0.0.1:8787/?login=1')


@require_http_methods(['POST'])
def local_logout(request):
    logout(request)
    return JsonResponse({'ok': True})


urlpatterns = [
    path('local/session/', local_session),
    path('api/v1.0/authenticate/', local_authenticate),
    path('api/v1.0/logout/', local_logout),
]

from mail_views import api, archive, attachment, page, upload, copy_download, quarantine_download
urlpatterns += [
    path('mail/',page),path('mail/<str:asset>',page),
    path('local/mail/<str:action>/',api),
    path('local/pdf/<str:resource>/',attachment),
    path('local/archive.zip',archive),
    path('local/application-upload/',upload),
    path('local/copy/<str:copy_id>/',copy_download),
    path('local/quarantine/<str:quarantine_id>/',quarantine_download),
    path('', include('conversations.urls')),
]
