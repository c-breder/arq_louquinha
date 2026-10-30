import time

from django.core.management.base import BaseCommand

from works.listing import rebuild_all


class Command(BaseCommand):
    help = "Reconstrói a tabela de listagens (WorkListing) de todas as obras."

    def handle(self, *args, **options):
        start = time.monotonic()
        total = rebuild_all()
        self.stdout.write(self.style.SUCCESS(f"{total} obras atualizadas em {time.monotonic() - start:.1f}s."))
