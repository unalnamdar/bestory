from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from search.services.countries import COUNTRIES, detect_country


@ensure_csrf_cookie  # the search JS reads this cookie to send X-CSRFToken
def home(request):
    country = detect_country(request, request.GET.get("country"))
    countries = [{"code": code, "name": info["name"], "currency": info["currency"]}
                 for code, info in COUNTRIES.items()]
    return render(request, "core/home.html", {"countries": countries, "default_country": country})


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
