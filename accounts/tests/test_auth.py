"""Registration, sign-in (e-mail or username), sign-out, profile, privacy and throttling."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import throttle
from accounts.models import LoginAttempt
from search.models import SearchLog

User = get_user_model()
PASSWORD = "S3cret-pass-123"
EMAIL = "ali.veli@private-mail.example"


def register_payload(**kw):
    data = {"username": "ali", "email": EMAIL, "password1": PASSWORD, "password2": PASSWORD}
    data.update(kw)
    return data


class RegisterTests(TestCase):
    url = "/hesap/kayit/"

    def test_register_logs_in_and_shows_username_in_header(self):
        resp = self.client.post(self.url, register_payload(), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.redirect_chain[-1][0], "/")
        self.assertTrue(resp.context["user"].is_authenticated)
        self.assertContains(resp, 'class="user-menu"')
        self.assertContains(resp, ">ali</summary>")
        self.assertContains(resp, "Hoş geldin, ali!")
        self.assertEqual(User.objects.get().username, "ali")

    def test_username_is_stored_lowercase_and_is_case_insensitive_unique(self):
        self.client.post(self.url, register_payload(username="Ali"))
        self.assertEqual(User.objects.get().username, "ali")
        self.client.logout()
        resp = self.client.post(self.url, register_payload(username="ALI", email="other@example.com"))
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Bu kullanıcı adı zaten alınmış.", status_code=400)
        self.assertEqual(User.objects.count(), 1)

    def test_same_email_cannot_register_twice_any_case(self):
        self.client.post(self.url, register_payload())
        self.client.logout()
        resp = self.client.post(self.url, register_payload(username="veli", email=EMAIL.upper()))
        self.assertContains(resp, "Bu e-posta adresi zaten kayıtlı.", status_code=400)
        self.assertEqual(User.objects.count(), 1)

    def test_email_is_stored_lowercase(self):
        self.client.post(self.url, register_payload(email="Ali.Veli@Private-Mail.Example"))
        self.assertEqual(User.objects.get().email, EMAIL)

    def test_reserved_and_invalid_usernames_are_rejected(self):
        for name in ("admin", "Bestory", "root", "destek", "ab", "a" * 21, "ali veli", "çağlar", "ali@x", "ali-veli"):
            with self.subTest(name=name):
                resp = self.client.post(self.url, register_payload(username=name, email=f"{abs(hash(name))}@example.com"))
                self.assertEqual(resp.status_code, 400)
                self.assertFalse(User.objects.exists())

    def test_reserved_name_message_is_turkish(self):
        resp = self.client.post(self.url, register_payload(username="admin"))
        self.assertContains(resp, "Bu kullanıcı adı kullanılamaz.", status_code=400)

    def test_password_rules_and_mismatch_have_turkish_messages(self):
        resp = self.client.post(self.url, register_payload(password1="12345678", password2="12345678"))
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Bu parola çok geneldir.", status_code=400)
        self.assertContains(resp, "tamamıyla sayısaldır", status_code=400)
        resp = self.client.post(self.url, register_payload(password2="Different-pass-999"))
        self.assertContains(resp, "Parolalar eşleşmiyor.", status_code=400)
        resp = self.client.post(self.url, register_payload(password1="kısa", password2="kısa"))
        self.assertContains(resp, "En az 8 karakter", status_code=400)
        self.assertFalse(User.objects.exists())

    def test_email_is_required_and_validated(self):
        for email in ("", "not-an-email"):
            with self.subTest(email=email):
                self.assertEqual(self.client.post(self.url, register_payload(email=email)).status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_page_renders_in_turkish_with_labels(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, "Kullanıcı adı")
        self.assertContains(resp, 'for="id_email"')
        self.assertContains(resp, "csrfmiddlewaretoken")

    def test_logged_in_user_is_redirected_away(self):
        self.client.post(self.url, register_payload())
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_errors_mark_fields_invalid_for_screen_readers(self):
        resp = self.client.post(self.url, register_payload(username="admin"))
        self.assertContains(resp, 'aria-invalid="true"', status_code=400)
        self.assertContains(resp, 'aria-describedby="id_username_hint id_username_error"', status_code=400)


class LoginTests(TestCase):
    url = "/hesap/giris/"

    def setUp(self):
        self.user = User.objects.create_user("ali", EMAIL, PASSWORD)

    def test_login_with_username_or_email_any_case(self):
        for identifier in ("ali", "ALI", EMAIL, EMAIL.upper(), "  ali  "):
            with self.subTest(identifier=identifier):
                self.client.logout()
                resp = self.client.post(self.url, {"identifier": identifier, "password": PASSWORD})
                self.assertRedirects(resp, "/", fetch_redirect_response=False)
                self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_wrong_password_and_unknown_user_give_the_same_generic_message(self):
        bad = [{"identifier": "ali", "password": "wrong"}, {"identifier": "nobody", "password": PASSWORD},
               {"identifier": "nobody@example.com", "password": PASSWORD}, {"identifier": EMAIL, "password": "wrong"}]
        messages = set()
        for data in bad:
            resp = self.client.post(self.url, data)
            self.assertEqual(resp.status_code, 400)
            self.assertContains(resp, "Bilgiler hatalı.", status_code=400)
            messages.add(resp.content.decode().count("Bilgiler hatalı."))
            self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(messages, {1})

    def test_inactive_user_cannot_login_and_gets_the_same_message(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        resp = self.client.post(self.url, {"identifier": "ali", "password": PASSWORD})
        self.assertContains(resp, "Bilgiler hatalı.", status_code=400)

    def test_next_parameter_is_honoured_when_safe(self):
        resp = self.client.post(self.url + "?next=/hesap/profil/", {"identifier": "ali", "password": PASSWORD})
        self.assertRedirects(resp, "/hesap/profil/", fetch_redirect_response=False)

    def test_next_from_hidden_field_is_honoured(self):
        resp = self.client.post(self.url, {"identifier": "ali", "password": PASSWORD, "next": "/?q=kulaklik&mode=value"})
        self.assertRedirects(resp, "/?q=kulaklik&mode=value", fetch_redirect_response=False)

    def test_unsafe_next_is_ignored(self):
        for target in ("https://evil.example/", "//evil.example/x", "javascript:alert(1)", "http://evil.example"):
            with self.subTest(target=target):
                self.client.logout()
                resp = self.client.post(self.url + "?next=" + target, {"identifier": "ali", "password": PASSWORD})
                self.assertRedirects(resp, "/", fetch_redirect_response=False)

    def test_next_is_carried_in_the_form_and_escaped(self):
        resp = self.client.get(self.url + '?next=/hesap/profil/"><script>alert(1)</script>')
        self.assertNotContains(resp, "<script>alert(1)</script>")
        resp = self.client.get(self.url + "?next=/hesap/profil/")
        self.assertContains(resp, 'name="next" value="/hesap/profil/"')

    def test_login_page_labels(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, "E-posta veya kullanıcı adı")
        self.assertContains(resp, 'for="id_password"')

    def test_admin_login_still_works_with_the_custom_backend(self):
        User.objects.create_superuser("boss", "boss@example.com", PASSWORD)
        self.assertTrue(self.client.login(username="boss", password=PASSWORD))
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_session_is_rotated_on_login(self):
        self.client.get(self.url)
        before = self.client.session.session_key
        self.client.post(self.url, {"identifier": "ali", "password": PASSWORD})
        self.assertNotEqual(self.client.session.session_key, before)


class LogoutTests(TestCase):
    def setUp(self):
        User.objects.create_user("ali", EMAIL, PASSWORD)
        self.client.login(username="ali", password=PASSWORD)

    def test_logout_requires_post(self):
        resp = self.client.get("/hesap/cikis/")
        self.assertEqual(resp.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_post_logs_out(self):
        resp = self.client.post("/hesap/cikis/")
        self.assertRedirects(resp, "/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_is_csrf_protected(self):
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="ali", password=PASSWORD)
        self.assertEqual(strict.post("/hesap/cikis/").status_code, 403)
        self.assertIn("_auth_user_id", strict.session)

    def test_header_logout_is_a_post_form(self):
        html = self.client.get("/").content.decode()
        self.assertIn('action="/hesap/cikis/"', html)
        self.assertIn('method="post"', html)


class ProfileAndPrivacyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ali", EMAIL, PASSWORD)

    def test_profile_requires_login_and_redirects_back(self):
        resp = self.client.get("/hesap/profil/")
        self.assertRedirects(resp, "/hesap/giris/?next=/hesap/profil/", fetch_redirect_response=False)

    def test_profile_shows_own_email_username_and_join_date(self):
        self.client.login(username="ali", password=PASSWORD)
        resp = self.client.get("/hesap/profil/")
        self.assertContains(resp, EMAIL)
        self.assertContains(resp, "ali")
        self.assertContains(resp, "Katılma tarihi")

    def test_email_is_never_in_public_html(self):
        # anonymous visitors
        for url in ("/", "/hesap/giris/", "/hesap/kayit/"):
            self.assertNotContains(self.client.get(url), EMAIL)
        # a signed-in user looking at the home page and the header
        self.client.login(username="ali", password=PASSWORD)
        home = self.client.get("/")
        self.assertNotContains(home, EMAIL)
        self.assertContains(home, ">ali</summary>")
        # another visitor never sees it either
        self.client.logout()
        self.assertNotContains(self.client.get("/"), EMAIL)

    def test_email_is_never_in_search_api_responses_or_logs(self):
        from django.test import override_settings as ov
        self.client.login(username="ali", password=PASSWORD)
        with ov(LLM_PROVIDER="mock", MOCK_DELAY_SECONDS=0):
            resp = self.client.post("/api/search/", data=json.dumps({"query": "kablosuz kulaklık"}),
                                    content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(EMAIL, resp.content.decode())
        self.assertNotIn(EMAIL, str(list(SearchLog.objects.values())))

    def test_login_attempts_store_only_hashes(self):
        self.client.post("/hesap/giris/", {"identifier": EMAIL, "password": "wrong"}, HTTP_X_FORWARDED_FOR="203.0.113.9")
        row = LoginAttempt.objects.get()
        self.assertEqual(len(row.ip_hash), 64)
        self.assertEqual(len(row.identifier_hash), 64)
        self.assertNotIn(EMAIL, str(list(LoginAttempt.objects.values())))
        self.assertNotIn("203.0.113.9", str(list(LoginAttempt.objects.values())))


class MemberSearchLimitTests(TestCase):
    def post(self, query):
        return self.client.post("/api/search/", data=json.dumps({"query": query}), content_type="application/json")

    @override_settings(LLM_PROVIDER="mock", MOCK_DELAY_SECONDS=0, RATE_LIMIT_ANON_PER_DAY=5, RATE_LIMIT_USER_PER_DAY=20)
    def test_member_limit_is_20_and_searches_are_logged_with_the_user(self):
        self.client.post("/hesap/kayit/", register_payload())
        user = User.objects.get()
        first = self.post("üye arama 0").json()
        self.assertEqual(first["remaining"], 19)
        for i in range(1, 6):  # an anonymous visitor would already be blocked after 5
            self.assertEqual(self.post(f"üye arama {i}").status_code, 200)
        self.assertEqual(SearchLog.objects.filter(user=user, status="ok").count(), 6)
        self.assertEqual(self.post("üye arama 6").json()["remaining"], 13)

    @override_settings(LLM_PROVIDER="mock", MOCK_DELAY_SECONDS=0, RATE_LIMIT_USER_PER_DAY=2)
    def test_429_for_members_has_no_signup_pitch_but_anonymous_429_links_to_signup(self):
        for i in range(2):
            self.post(f"anon {i}")  # anonymous limit is 5 by default, so these pass
        anon_user_limit = self.client.post("/api/search/", data=json.dumps({"query": "x1"}), content_type="application/json")
        self.assertEqual(anon_user_limit.status_code, 200)
        with override_settings(RATE_LIMIT_ANON_PER_DAY=1):
            resp = self.post("anon yeni")
        self.assertEqual(resp.status_code, 429)
        error = resp.json()["error"]
        self.assertIn("üye ol", error["message"])
        self.assertEqual(error["signup_url"], reverse("accounts:register"))  # the Phase 2 hook now has a target


class ThrottleTests(TestCase):
    url = "/hesap/giris/"

    def setUp(self):
        User.objects.create_user("ali", EMAIL, PASSWORD)

    def fail(self, identifier="ali", ip="198.51.100.1", n=1):
        for _ in range(n):
            self.client.post(self.url, {"identifier": identifier, "password": "wrong"}, HTTP_X_FORWARDED_FOR=ip)

    def test_account_is_locked_after_5_failures_even_with_the_right_password(self):
        self.fail(n=5)
        resp = self.client.post(self.url, {"identifier": "ali", "password": PASSWORD}, HTTP_X_FORWARDED_FOR="198.51.100.1")
        self.assertEqual(resp.status_code, 429)
        self.assertContains(resp, "Çok fazla başarısız deneme", status_code=429)
        self.assertContains(resp, "dakika", status_code=429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lock_applies_across_ips_for_the_same_account(self):
        for i in range(5):
            self.fail(ip=f"198.51.100.{i + 10}")
        resp = self.client.post(self.url, {"identifier": "ali", "password": PASSWORD}, HTTP_X_FORWARDED_FOR="203.0.113.77")
        self.assertEqual(resp.status_code, 429)

    def test_identifier_is_matched_case_insensitively_for_the_lock(self):
        self.fail(identifier="ALI", n=3)
        self.fail(identifier="ali", n=2)
        resp = self.client.post(self.url, {"identifier": "Ali", "password": PASSWORD})
        self.assertEqual(resp.status_code, 429)

    def test_other_accounts_are_not_affected_by_one_locked_account(self):
        User.objects.create_user("veli", "veli@example.com", PASSWORD)
        self.fail(n=5)
        resp = self.client.post(self.url, {"identifier": "veli", "password": PASSWORD}, HTTP_X_FORWARDED_FOR="203.0.113.50")
        self.assertEqual(resp.status_code, 302)

    def test_one_ip_is_blocked_after_10_failures_across_accounts(self):
        for i in range(10):
            self.fail(identifier=f"ghost{i}", ip="198.51.100.99")
        resp = self.client.post(self.url, {"identifier": "ali", "password": PASSWORD}, HTTP_X_FORWARDED_FOR="198.51.100.99")
        self.assertEqual(resp.status_code, 429)

    def test_lock_expires_after_the_window(self):
        self.fail(n=5)
        LoginAttempt.objects.update(created_at=timezone.now() - throttle.WINDOW - timedelta(seconds=5))
        resp = self.client.post(self.url, {"identifier": "ali", "password": PASSWORD}, HTTP_X_FORWARDED_FOR="198.51.100.1")
        self.assertEqual(resp.status_code, 302)

    def test_blocked_attempts_are_not_recorded_and_old_rows_are_cleaned(self):
        self.fail(n=5)
        self.fail(n=3)  # blocked: must not extend the lock
        self.assertEqual(LoginAttempt.objects.count(), 5)
        LoginAttempt.objects.update(created_at=timezone.now() - timedelta(days=2))
        self.fail(identifier="someone", ip="198.51.100.200")
        self.assertEqual(LoginAttempt.objects.count(), 1)

    def test_successful_login_records_nothing(self):
        self.client.post(self.url, {"identifier": "ali", "password": PASSWORD})
        self.assertEqual(LoginAttempt.objects.count(), 0)
