from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shops", "0014_workorder_priority_due_date_and_line_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="shopprofile",
            name="enabled_features",
            field=models.JSONField(
                blank=True,
                default=[
                    "repair_orders",
                    "inspections",
                    "inventory",
                    "reports",
                    "invoices",
                    "customers",
                    "user_management",
                ],
            ),
        ),
    ]