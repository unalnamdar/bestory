from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("api/health/", views.health, name="health"),
    path("robots.txt", views.robots_txt, name="robots"),
    # Browsers ask for /favicon.ico on their own; point them at the SVG icon.
    path("favicon.ico", views.favicon, name="favicon"),
]
