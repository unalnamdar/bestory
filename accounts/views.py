from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from search.services.history import recent_searches
from search.services.ratelimit import client_ip, hash_ip

from . import throttle
from .forms import LoginForm, RegisterForm

BACKEND = "accounts.backends.EmailOrUsernameBackend"
GENERIC_LOGIN_ERROR = "Bilgiler hatalı."  # never say which field was wrong


def _safe_next(request):
    """The ?next= target, only if it stays on this site (no open redirect)."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return ""


@require_http_methods(["GET", "POST"])
def register(request):
    next_url = _safe_next(request)
    if request.user.is_authenticated:
        return redirect(next_url or "/")
    form = RegisterForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            login(request, user, backend=BACKEND)
            messages.success(request, f"Hoş geldin, {user.username}!")
            return redirect(next_url or "/")
        form.mark_invalid()
    return render(request, "accounts/register.html", {"form": form, "next": next_url}, status=400 if form.errors else 200)


@require_http_methods(["GET", "POST"])
def login_view(request):
    next_url = _safe_next(request)
    if request.user.is_authenticated:
        return redirect(next_url or "/")
    form = LoginForm(request.POST or None)
    status = 200
    if request.method == "POST":
        if form.is_valid():
            identifier = form.cleaned_data["identifier"]
            ip_hash = hash_ip(client_ip(request))
            blocked = throttle.blocked_message(ip_hash, identifier)
            if blocked:
                form.add_error(None, blocked)
                status = 429
            else:
                user = authenticate(request, username=identifier, password=form.cleaned_data["password"])
                if user is not None:
                    login(request, user)
                    return redirect(next_url or "/")
                throttle.record_failure(ip_hash, identifier)
                form.add_error(None, GENERIC_LOGIN_ERROR)
                status = 400
        else:
            status = 400
        form.mark_invalid()
    return render(request, "accounts/login.html", {"form": form, "next": next_url}, status=status)


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Çıkış yaptın.")
    return redirect("/")


@login_required
def profile(request):
    return render(request, "accounts/profile.html", {"recent": recent_searches(request.user)})
