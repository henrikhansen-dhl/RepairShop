from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shops", "0011_shopuseraccess_preferred_language"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="repairworkorder",
            name="car",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="work_orders", to="shops.customercar"),
        ),
        migrations.AddField(
            model_name="repairworkorder",
            name="customer",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name="work_orders", to="shops.customer"),
        ),
        migrations.AddField(
            model_name="repairworkorder",
            name="invoice",
            field=models.OneToOneField(blank=True, null=True, on_delete=models.SET_NULL, related_name="work_order", to="shops.invoice"),
        ),
        migrations.AddField(
            model_name="repairworkorder",
            name="technician_notes",
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name="RepairWorkOrderLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(max_length=255)),
                ("quantity", models.DecimalField(decimal_places=2, default=1, max_digits=10, validators=[MinValueValidator(0.01)])),
                ("unit_price", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("vat_percent", models.DecimalField(decimal_places=2, default=25, max_digits=5)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("price_item", models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="work_order_lines", to="shops.invoicepriceitem")),
                ("work_order", models.ForeignKey(on_delete=models.CASCADE, related_name="service_lines", to="shops.repairworkorder")),
            ],
            options={
                "db_table": "repair_work_order_line",
                "ordering": ["id"],
            },
        ),
    ]