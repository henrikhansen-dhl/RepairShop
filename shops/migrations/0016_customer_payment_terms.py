from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shops", "0015_shopprofile_enabled_features"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="payment_due_condition",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "No automatic due date"),
                    ("days", "+day"),
                    ("running_week", "running week"),
                    ("running_month", "running month"),
                    ("running_week_days", "running week + days"),
                    ("running_month_days", "running month + days"),
                ],
                default="",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="payment_due_days",
            field=models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)]),
        ),
    ]