from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command

from repairshop.tenant_db import ensure_tenant_database_alias


class Command(BaseCommand):
    help = "Initialize database schema for a tenant DB alias."

    def add_arguments(self, parser):
        parser.add_argument("alias", help="Tenant DB alias, for example: shop3_db")
        parser.add_argument(
            "--app",
            dest="apps",
            action="append",
            default=[],
            help="Optional app label to migrate. Repeat for multiple apps.",
        )

    def handle(self, *args, **options):
        alias = options["alias"].strip()
        app_labels = options["apps"]
        shared_apps = set(getattr(settings, "SHARED_APPS", set()))

        if not alias:
            raise CommandError("Alias cannot be empty.")

        ensure_tenant_database_alias(alias)

        if alias not in settings.DATABASES:
            raise CommandError(
                (
                    f"Database alias '{alias}' is not configured. "
                    "Define env vars (e.g. PA_<ALIAS>_NAME for MySQL) or use local sqlite mode."
                )
            )

        if not app_labels:
            installed_labels = [app.rsplit(".", 1)[-1] for app in settings.INSTALLED_APPS]
            app_labels = [label for label in installed_labels if label not in shared_apps]

        if not app_labels:
            self.stdout.write(
                self.style.WARNING(
                    "No tenant-domain apps found to migrate. Add tenant apps to INSTALLED_APPS first."
                )
            )
            return

        if app_labels:
            for app_label in app_labels:
                if app_label in shared_apps:
                    raise CommandError(
                        (
                            f"App '{app_label}' is configured as shared and should not be migrated "
                            f"on tenant alias '{alias}'."
                        )
                    )
                self.stdout.write(f"Applying migrations for app '{app_label}' on '{alias}'...")
                call_command("migrate", app_label, database=alias, interactive=False)

        self.stdout.write(self.style.SUCCESS(f"Tenant database '{alias}' initialized."))
