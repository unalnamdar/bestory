import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from pydantic import ValidationError

from .services.analyzer import AnalysisError, run_search
from .services.countries import detect_country
from .services.schema import SearchRequest, error_fields


def _error(status, code, message, fields=None, extra=None):
    body = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    if extra:
        body["error"].update(extra)
    return JsonResponse(body, status=status)


@require_POST
def search_api(request):
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return _error(400, "invalid", "Geçersiz istek.")

    try:
        req = SearchRequest.model_validate(body)
    except ValidationError as exc:
        fields = error_fields(exc)
        return _error(400, "invalid", next(iter(fields.values())), fields)

    country = detect_country(request, req.country)
    try:
        data, cached, remaining = run_search(request, req, country)
    except AnalysisError as exc:
        return _error(exc.status, exc.code, exc.message, extra=exc.extra)

    return JsonResponse({"cached": cached, "data": data, "remaining": remaining})
