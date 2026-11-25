from django.db import connection
from django.http import HttpResponse, HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

ROBOTS_TXT = "User-agent: *\nDisallow: /api/\nDisallow: /hesap/\nDisallow: /admin/\n"


@require_GET
@cache_control(max_age=86400, public=True)
def robots_txt(request):
    return HttpResponse(ROBOTS_TXT, content_type="text/plain; charset=utf-8")


@require_GET
def favicon(request):
    return HttpResponsePermanentRedirect(static("img/favicon.svg"))


@ensure_csrf_cookie  # the search JS reads this cookie to send X-CSRFToken
def home(request):
    return render(request, "core/home.html", {"show_country_select": True})


def health(request):
    """Liveness + DB check. Returns 503 if the database is unreachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse(
        {"status": "ok" if db_ok else "error", "db": db_ok},
        status=200 if db_ok else 503,
    )
