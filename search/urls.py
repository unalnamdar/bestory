from django.urls import path

from . import views

app_name = "search"

urlpatterns = [
    path("api/search/", views.search_api, name="api"),
]
