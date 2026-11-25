"""Error pages, robots.txt, favicon and the shared <head> meta tags."""
from django.template.loader import render_to_string
from django.test import TestCase, override_settings


class ErrorPageTests(TestCase):
    @override_settings(DEBUG=False)
    def test_404_uses_custom_page(self):
        resp = self.client.get("/olmayan-sayfa/")
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, "Bu sayfayı bulamadık", status_code=404)
        self.assertContains(resp, 'content="noindex"', status_code=404)

    def test_500_renders_without_request_context(self):
        # Django's server_error view renders 500.html with an empty context.
        html = render_to_string("500.html")
        self.assertIn("Bir şeyler ters gitti", html)
        self.assertIn('href="/"', html)


class DeployCheckTests(TestCase):
    def test_weak_ip_salt_warns(self):
        from core.checks import ip_hash_salt_check
        for salt in ("", "change-me", "short"):
            with self.subTest(salt=salt), override_settings(IP_HASH_SALT=salt):
                self.assertEqual([w.id for w in ip_hash_salt_check(None)], ["bestory.W001"])
        with override_settings(IP_HASH_SALT="a-long-random-salt-value-123"):
            self.assertEqual(ip_hash_salt_check(None), [])


class SmallRoutesTests(TestCase):
    def test_robots_txt(self):
        resp = self.client.get("/robots.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("Disallow: /api/", resp.content.decode())

    def test_favicon_redirects_to_svg(self):
        resp = self.client.get("/favicon.ico")
        self.assertEqual(resp.status_code, 301)
        self.assertTrue(resp["Location"].endswith("img/favicon.svg"))


class MetaTagTests(TestCase):
    def test_home_has_description_and_open_graph(self):
        resp = self.client.get("/?q=kulakl%C4%B1k&mode=value")
        for needle in ('name="description"', 'property="og:title"', 'property="og:description"',
                       'property="og:locale" content="tr_TR"', 'name="twitter:card"',
                       'rel="icon"'):
            self.assertContains(resp, needle)
        # The canonical/og:url is the page itself, without the search query string.
        self.assertContains(resp, '<link rel="canonical" href="http://testserver/">')
        self.assertContains(resp, '<meta property="og:url" content="http://testserver/">')

    def test_account_pages_are_noindex(self):
        for url in ("/hesap/giris/", "/hesap/kayit/"):
            self.assertContains(self.client.get(url), '<meta name="robots" content="noindex">')
        self.assertContains(self.client.get("/"), '<meta name="robots" content="index, follow">')
