from search.services.countries import COUNTRIES, detect_country


def site(request):
    """Values the shared header needs on every page."""
    path = request.get_full_path()
    return {
        "countries": [{"code": code, "name": info["name"], "currency": info["currency"]}
                      for code, info in COUNTRIES.items()],
        "default_country": detect_country(request, request.GET.get("country")),
        # Where "Giriş yap" should send the user back to (not from the account pages themselves).
        "login_next": "" if path.startswith("/hesap/") else path,
        # Path only: query strings (searches) are not separate pages.
        "canonical_url": request.build_absolute_uri(request.path),
    }
