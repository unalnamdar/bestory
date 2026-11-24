from django.conf import settings
from django.db import models


class SearchCache(models.Model):
    """Cached, validated analysis result for a normalized request."""

    MODE_CHOICES = [
        ("best_sellers", "En çok satanlar"),
        ("top_rated", "En yüksek puan"),
        ("value", "Fiyat / performans"),
        ("custom", "Özel"),
    ]

    cache_key = models.CharField(max_length=64, unique=True, db_index=True)
    query = models.CharField(max_length=200)
    country = models.CharField(max_length=2)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    params = models.JSONField(default=dict)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    def __str__(self):
        return f"{self.query} [{self.country}/{self.mode}]"


class SearchLog(models.Model):
    """One row per search request. Raw IPs are never stored (KVKK)."""

    STATUS_CHOICES = [
        ("ok", "ok"),
        ("invalid", "invalid"),
        ("rate_limited", "rate_limited"),
        ("provider_error", "provider_error"),
        ("timeout", "timeout"),
        ("not_a_product", "not_a_product"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    ip_hash = models.CharField(max_length=64, db_index=True)
    query = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=2, blank=True)
    mode = models.CharField(max_length=20, blank=True)
    cache_hit = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    duration_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.status} {self.query}"
