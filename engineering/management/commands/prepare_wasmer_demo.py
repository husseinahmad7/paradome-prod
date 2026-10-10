from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Prepare the independent Wasmer database before preview promotion."

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != "paradome.settings.wasmer":
            raise CommandError("Only the independent Wasmer profile may run this deployment job")
        call_command("migrate", interactive=False, stdout=self.stdout)
        call_command("createcachetable", stdout=self.stdout)
        call_command("wasmer_compatibility", stdout=self.stdout)
        if not User.objects.filter(username=settings.DEMO_USERNAME).exists():
            call_command("maintain_demo_sandbox", stdout=self.stdout)
        # Assets should be packaged at build time. A read-only deployment should
        # fail its build rather than try writing static files on every web start.
