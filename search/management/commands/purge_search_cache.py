from django.core.management.base import BaseCommand

from search.services.cache import purge_expired


class Command(BaseCommand):
    help = "Delete expired SearchCache rows."

    def handle(self, *args, **options):
        deleted = purge_expired()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired cache row(s)."))
