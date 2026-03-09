from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shops", "0012_repairworkorderline_and_workorder_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="repairworkorder",
            name="due_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="repairworkorder",
            name="priority",
            field=models.CharField(
                choices=[("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")],
                default="normal",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="repairworkorderline",
            name="line_type",
            field=models.CharField(
                choices=[("service", "Service"), ("part", "Part")],
                default="service",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="repairworkorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("assigned", "Assigned"),
                    ("in_progress", "In Progress"),
                    ("ready", "Ready for Invoice"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ],
                default="new",
                max_length=24,
            ),
        ),
    ]