from django.core.management.base import BaseCommand, CommandError
from engineering.services import purge_expired_runs


class Command(BaseCommand):
    help = "Delete expired isolated lab records in bounded batches (even when the lab flag is off)."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--max-batches", type=int, default=5)

    def handle(self, *args, **options):
        try:
            count = purge_expired_runs(batch_size=options["batch_size"], max_batches=options["max_batches"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Purged {count} expired engineering runs."))
