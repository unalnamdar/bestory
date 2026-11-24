from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from search.models import SearchCache, SearchLog


class SearchModelTests(TestCase):
    def test_cache_key_unique(self):
        kwargs = dict(
            cache_key="a" * 64, query="ofis sandalyesi", country="TR", mode="value",
            result={"products": []}, expires_at=timezone.now() + timedelta(hours=24),
        )
        SearchCache.objects.create(**kwargs)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SearchCache.objects.create(**kwargs)

    def test_log_allows_anonymous(self):
        log = SearchLog.objects.create(ip_hash="h" * 64, query="x", status="ok")
        self.assertIsNone(log.user)
        self.assertFalse(log.cache_hit)
