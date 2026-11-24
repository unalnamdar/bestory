from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

User = get_user_model()


class UserModelTests(TestCase):
    def make(self, username="ali", email="ali@example.com"):
        user = User(username=username, email=email)
        user.set_password("S3cret-pass-123")
        user.full_clean()
        user.save()
        return user

    def test_username_and_email_lowercased(self):
        user = self.make("Ali.Veli", "Ali@Example.COM")
        user.refresh_from_db()
        self.assertEqual(user.username, "ali.veli")
        self.assertEqual(user.email, "ali@example.com")

    def test_username_unique_case_insensitive(self):
        self.make("ali", "a@example.com")
        with self.assertRaises(ValidationError):
            self.make("Ali", "b@example.com")

    def test_email_unique_case_insensitive(self):
        self.make("ali", "a@example.com")
        with self.assertRaises(ValidationError):
            self.make("veli", "A@EXAMPLE.com")

    def test_db_enforces_unique_username_on_direct_save(self):
        self.make("ali", "a@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(username="ALI", email="other@example.com")

    def test_reserved_usernames_rejected(self):
        for name in ("admin", "Bestory", "root", "api", "destek"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.make(name, f"{name}@example.com")

    def test_invalid_usernames_rejected(self):
        for name in ("ab", "a" * 21, "ali veli", "ali-veli", "çağlar", "ali@x"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.make(name, "x@example.com")

    def test_email_required(self):
        user = User(username="noemail", email="")
        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_no_first_last_name_fields(self):
        field_names = {f.name for f in User._meta.get_fields()}
        self.assertNotIn("first_name", field_names)
        self.assertNotIn("last_name", field_names)

    def test_createsuperuser_path(self):
        admin_user = User.objects.create_superuser("boss", "boss@example.com", "S3cret-pass-123")
        self.assertTrue(admin_user.is_superuser)
