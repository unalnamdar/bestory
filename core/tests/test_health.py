from unittest import mock

from django.test import TestCase
from django.urls import reverse


class HealthTests(TestCase):
    def test_health_ok(self):
        resp = self.client.get(reverse("core:health"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok", "db": True})

    def test_health_db_down(self):
        with mock.patch("core.views.connection.cursor", side_effect=Exception("boom")):
            resp = self.client.get(reverse("core:health"))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json(), {"status": "error", "db": False})

    def test_home_renders(self):
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bestory")
