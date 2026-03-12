import calendar
from datetime import timedelta

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _


def default_shop_features():
    return [
        "repair_orders",
        "inspections",
        "inventory",
        "reports",
        "invoices",
        "customers",
        "user_management",
    ]


class ShopProfile(models.Model):
    """
    Shared metadata for each shop/tenant.

    `database_name` should match the DB alias used in settings.DATABASES
    (for example: "shop1_db", "shop2_db").
    """

    FEATURE_REPAIR_ORDERS = "repair_orders"
    FEATURE_INSPECTIONS = "inspections"
    FEATURE_INVENTORY = "inventory"
    FEATURE_REPORTS = "reports"
    FEATURE_INVOICES = "invoices"
    FEATURE_CUSTOMERS = "customers"
    FEATURE_USER_MANAGEMENT = "user_management"
    FEATURE_CHOICES = [
        (FEATURE_REPAIR_ORDERS, _("Repair Orders")),
        (FEATURE_INSPECTIONS, _("Vehicle Inspections")),
        (FEATURE_INVENTORY, _("Inventory Management")),
        (FEATURE_REPORTS, _("Reports")),
        (FEATURE_INVOICES, _("Invoices")),
        (FEATURE_CUSTOMERS, _("Customers & Vehicles")),
        (FEATURE_USER_MANAGEMENT, _("Shop User Management")),
    ]

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shop_profile",
    )
    shop_name = models.CharField(max_length=120, unique=True)
    database_name = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    enabled_features = models.JSONField(default=default_shop_features, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shop_profile"

    def __str__(self) -> str:
        return f"{self.shop_name} ({self.database_name})"

    def get_enabled_features(self) -> list[str]:
        valid_codes = {code for code, _label in self.FEATURE_CHOICES}
        return [code for code in (self.enabled_features or []) if code in valid_codes]

    def has_feature(self, feature_code: str) -> bool:
        return feature_code in set(self.get_enabled_features())

    def get_enabled_feature_labels(self) -> list[str]:
        labels_by_code = dict(self.FEATURE_CHOICES)
        return [str(labels_by_code[code]) for code in self.get_enabled_features() if code in labels_by_code]

    @property
    def enabled_feature_summary(self) -> str:
        labels = self.get_enabled_feature_labels()
        return ", ".join(labels) if labels else "No paid functions"


class ShopUserAccess(models.Model):
    """
    Maps users to shops with shop-scoped rights.
    """

    ROLE_OWNER = "owner"
    ROLE_MANAGER = "manager"
    ROLE_ADVISOR = "advisor"
    ROLE_TECHNICIAN = "technician"
    ROLE_CLERK = "clerk"

    ROLE_CHOICES = [
        (ROLE_OWNER, "Owner"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_ADVISOR, "Service Advisor"),
        (ROLE_TECHNICIAN, "Technician"),
        (ROLE_CLERK, "Front Desk Clerk"),
    ]

    LANGUAGE_EN = "en"
    LANGUAGE_DA = "da"
    LANGUAGE_DE = "de"
    LANGUAGE_CHOICES = [
        (LANGUAGE_EN, "English"),
        (LANGUAGE_DA, "Danish"),
        (LANGUAGE_DE, "German"),
    ]

    shop = models.ForeignKey(
        ShopProfile,
        on_delete=models.CASCADE,
        related_name="user_accesses",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shop_accesses",
    )
    role = models.CharField(max_length=24, choices=ROLE_CHOICES, default=ROLE_CLERK)
    can_manage_users = models.BooleanField(default=False)
    can_create_repair_order = models.BooleanField(default=True)
    can_manage_inventory = models.BooleanField(default=False)
    can_view_reports = models.BooleanField(default=False)
    preferred_language = models.CharField(max_length=8, choices=LANGUAGE_CHOICES, default=LANGUAGE_EN)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shop_user_access"
        unique_together = ("shop", "user")

    def __str__(self) -> str:
        return f"{self.user} -> {self.shop.shop_name} ({self.role})"


class ShopMasterData(models.Model):
    """Invoice sender master data per shop."""

    shop = models.OneToOneField(
        ShopProfile,
        on_delete=models.CASCADE,
        related_name="master_data",
    )
    legal_name = models.CharField(max_length=160, blank=True)
    address_line1 = models.CharField(max_length=160, blank=True)
    address_line2 = models.CharField(max_length=160, blank=True)
    postal_code = models.CharField(max_length=24, blank=True)
    city = models.CharField(max_length=80, blank=True)
    country = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    vat_number = models.CharField(max_length=40, blank=True)
    company_logo = models.ImageField(upload_to="shop_logos/", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shop_master_data"

    def __str__(self) -> str:
        return self.legal_name or self.shop.shop_name


class RepairWorkOrder(models.Model):
    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    STATUS_NEW = "new"
    STATUS_ASSIGNED = "assigned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_READY = "ready"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_ASSIGNED, "Assigned"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_READY, "Ready for Invoice"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    shop = models.ForeignKey(
        ShopProfile,
        on_delete=models.CASCADE,
        related_name="work_orders",
    )
    customer = models.ForeignKey(
        "Customer",
        on_delete=models.PROTECT,
        related_name="work_orders",
        null=True,
        blank=True,
    )
    car = models.ForeignKey(
        "CustomerCar",
        on_delete=models.SET_NULL,
        related_name="work_orders",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_work_orders",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_work_orders",
    )
    description = models.TextField()
    technician_notes = models.TextField(blank=True)
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_NEW)
    invoice = models.OneToOneField(
        "Invoice",
        on_delete=models.SET_NULL,
        related_name="work_order",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "repair_work_order"
        ordering = ["-created_at"]

    def __str__(self):
        return f"WorkOrder #{self.id} ({self.status})"

    def assign(self, user):
        self.assigned_to = user
        self.status = self.STATUS_ASSIGNED
        self.save()

    def complete(self):
        self.status = self.STATUS_COMPLETED
        self.save()

    def cancel(self):
        self.status = self.STATUS_CANCELLED
        self.save()

    @property
    def subtotal(self):
        return sum((line.line_total for line in self.service_lines.all()), 0)

    @property
    def vat_total(self):
        return sum((line.vat_amount for line in self.service_lines.all()), 0)

    @property
    def service_total(self):
        return sum((line.line_total for line in self.service_lines.filter(line_type=RepairWorkOrderLine.TYPE_SERVICE)), 0)

    @property
    def part_total(self):
        return sum((line.line_total for line in self.service_lines.filter(line_type=RepairWorkOrderLine.TYPE_PART)), 0)


class RepairWorkOrderLine(models.Model):
    TYPE_SERVICE = "service"
    TYPE_PART = "part"
    TYPE_CHOICES = [
        (TYPE_SERVICE, "Service"),
        (TYPE_PART, "Part"),
    ]

    work_order = models.ForeignKey(
        RepairWorkOrder,
        on_delete=models.CASCADE,
        related_name="service_lines",
    )
    price_item = models.ForeignKey(
        "InvoicePriceItem",
        on_delete=models.SET_NULL,
        related_name="work_order_lines",
        null=True,
        blank=True,
    )
    line_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=TYPE_SERVICE)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1, validators=[MinValueValidator(0.01)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=25)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "repair_work_order_line"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.description

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    @property
    def vat_amount(self):
        return self.line_total * (self.vat_percent / 100)

class Customer(models.Model):
    PAYMENT_DUE_NONE = ""
    PAYMENT_DUE_DAYS = "days"
    PAYMENT_DUE_RUNNING_WEEK = "running_week"
    PAYMENT_DUE_RUNNING_MONTH = "running_month"
    PAYMENT_DUE_RUNNING_WEEK_DAYS = "running_week_days"
    PAYMENT_DUE_RUNNING_MONTH_DAYS = "running_month_days"
    PAYMENT_DUE_CHOICES = [
        (PAYMENT_DUE_NONE, _("No automatic due date")),
        (PAYMENT_DUE_DAYS, _("+day")),
        (PAYMENT_DUE_RUNNING_WEEK, _("running week")),
        (PAYMENT_DUE_RUNNING_MONTH, _("running month")),
        (PAYMENT_DUE_RUNNING_WEEK_DAYS, _("running week + days")),
        (PAYMENT_DUE_RUNNING_MONTH_DAYS, _("running month + days")),
    ]

    shop = models.ForeignKey(
        ShopProfile,
        on_delete=models.CASCADE,
        related_name="customers",
    )
    full_name = models.CharField(max_length=140)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    payment_due_condition = models.CharField(max_length=32, choices=PAYMENT_DUE_CHOICES, blank=True, default="")
    payment_due_days = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer"
        ordering = ["full_name", "id"]
        unique_together = ("shop", "full_name", "phone")

    def __str__(self) -> str:
        return f"{self.full_name} ({self.shop.shop_name})"

    def calculate_invoice_due_date(self, issue_date):
        if not issue_date or not self.payment_due_condition:
            return None

        extra_days = self.payment_due_days or 0

        if self.payment_due_condition == self.PAYMENT_DUE_DAYS:
            return issue_date + timedelta(days=extra_days)

        if self.payment_due_condition in {self.PAYMENT_DUE_RUNNING_WEEK, self.PAYMENT_DUE_RUNNING_WEEK_DAYS}:
            week_end = issue_date + timedelta(days=(6 - issue_date.weekday()))
            if self.payment_due_condition == self.PAYMENT_DUE_RUNNING_WEEK_DAYS:
                week_end += timedelta(days=extra_days)
            return week_end

        if self.payment_due_condition in {self.PAYMENT_DUE_RUNNING_MONTH, self.PAYMENT_DUE_RUNNING_MONTH_DAYS}:
            month_end_day = calendar.monthrange(issue_date.year, issue_date.month)[1]
            month_end = issue_date.replace(day=month_end_day)
            if self.payment_due_condition == self.PAYMENT_DUE_RUNNING_MONTH_DAYS:
                month_end += timedelta(days=extra_days)
            return month_end

        return None


class CustomerCar(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="cars",
    )
    make = models.CharField(max_length=80)
    model = models.CharField(max_length=80)
    year = models.PositiveIntegerField(null=True, blank=True)
    plate_number = models.CharField(max_length=32, blank=True)
    vin = models.CharField(max_length=64, blank=True)
    color = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)
    inspection_type = models.CharField(max_length=64, blank=True)
    inspection_date = models.DateField(null=True, blank=True)
    inspection_result = models.CharField(max_length=64, blank=True)
    inspection_status = models.CharField(max_length=64, blank=True)
    inspection_status_date = models.DateField(null=True, blank=True)
    inspection_mileage = models.PositiveIntegerField(null=True, blank=True)
    next_inspection_date = models.DateField(null=True, blank=True)
    tire_hotel_enabled = models.BooleanField(default=False)
    tire_hotel_location = models.CharField(max_length=80, blank=True)
    tire_hotel_notes = models.TextField(blank=True)
    tire_label_count = models.PositiveSmallIntegerField(default=4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer_car"
        ordering = ["-created_at", "id"]

    def __str__(self) -> str:
        year_text = f"{self.year} " if self.year else ""
        return f"{year_text}{self.make} {self.model}".strip()


class InvoicePriceItem(models.Model):
    TYPE_SERVICE = "service"
    TYPE_PART = "part"
    TYPE_CHOICES = [
        (TYPE_SERVICE, "Service"),
        (TYPE_PART, "Part"),
    ]

    shop = models.ForeignKey(
        ShopProfile,
        on_delete=models.CASCADE,
        related_name="invoice_price_items",
    )
    item_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=TYPE_SERVICE)
    code = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=255)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=25)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoice_price_item"
        ordering = ["item_type", "description", "id"]

    def __str__(self) -> str:
        return f"{self.description} ({self.unit_price})"


class InvoiceNumberSeries(models.Model):
    shop = models.OneToOneField(
        ShopProfile,
        on_delete=models.CASCADE,
        related_name="invoice_number_series",
    )
    prefix = models.CharField(max_length=16, default="INV")
    next_number = models.PositiveIntegerField(default=1)
    padding = models.PositiveSmallIntegerField(default=6)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoice_number_series"

    def __str__(self) -> str:
        return f"{self.shop.shop_name}: {self.prefix}-{self.next_number}"


def get_next_invoice_number(shop: ShopProfile) -> str:
    """Allocate the next invoice number from the shop-specific number series."""
    with transaction.atomic():
        series, _ = InvoiceNumberSeries.objects.select_for_update().get_or_create(
            shop=shop,
            defaults={"prefix": "INV", "next_number": 1, "padding": 6},
        )
        number = series.next_number
        series.next_number = number + 1
        series.save(update_fields=["next_number", "updated_at"])

    return f"{series.prefix}-{number:0{series.padding}d}"


class Invoice(models.Model):
    REBATE_NONE = "none"
    REBATE_PERCENT = "percent"
    REBATE_AMOUNT = "amount"
    REBATE_TYPE_CHOICES = [
        (REBATE_NONE, "No rebate"),
        (REBATE_PERCENT, "Percent (%)"),
        (REBATE_AMOUNT, "Fixed amount"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_ISSUED = "issued"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_PAID, "Paid"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    shop = models.ForeignKey(
        ShopProfile,
        on_delete=models.CASCADE,
        related_name="invoices",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    car = models.ForeignKey(
        CustomerCar,
        on_delete=models.SET_NULL,
        related_name="invoices",
        null=True,
        blank=True,
    )
    invoice_number = models.CharField(max_length=40, blank=True)
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    total_rebate_type = models.CharField(max_length=16, choices=REBATE_TYPE_CHOICES, default=REBATE_NONE)
    total_rebate_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoice"
        ordering = ["-issue_date", "-id"]

    def __str__(self) -> str:
        number = self.invoice_number or f"INV-{self.pk}"
        return f"{number} - {self.customer.full_name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number and self.shop_id:
            self.invoice_number = get_next_invoice_number(self.shop)
        if self.customer_id and self.issue_date:
            calculated_due_date = self.customer.calculate_invoice_due_date(self.issue_date)
            if calculated_due_date is not None:
                self.due_date = calculated_due_date
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        return sum((line.line_total for line in self.lines.all()), 0)

    @property
    def total_rebate_amount(self):
        subtotal = self.subtotal
        value = self.total_rebate_value or 0
        if self.total_rebate_type == self.REBATE_PERCENT:
            amount = subtotal * (value / 100)
            return min(amount, subtotal)
        if self.total_rebate_type == self.REBATE_AMOUNT:
            return min(value, subtotal)
        return 0

    @property
    def grand_total(self):
        return self.subtotal - self.total_rebate_amount

    @property
    def vat_total(self):
        return sum((line.vat_amount for line in self.lines.all()), 0)

    @property
    def grand_total_incl_vat(self):
        return self.grand_total + self.vat_total


class InvoiceLine(models.Model):
    REBATE_NONE = "none"
    REBATE_PERCENT = "percent"
    REBATE_AMOUNT = "amount"
    REBATE_TYPE_CHOICES = [
        (REBATE_NONE, "No rebate"),
        (REBATE_PERCENT, "Percent (%)"),
        (REBATE_AMOUNT, "Fixed amount"),
    ]

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    price_item = models.ForeignKey(
        InvoicePriceItem,
        on_delete=models.SET_NULL,
        related_name="invoice_lines",
        null=True,
        blank=True,
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1, validators=[MinValueValidator(0.01)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=25)
    rebate_type = models.CharField(max_length=16, choices=REBATE_TYPE_CHOICES, default=REBATE_NONE)
    rebate_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoice_line"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.description

    @property
    def line_subtotal(self):
        return self.quantity * self.unit_price

    @property
    def rebate_amount(self):
        subtotal = self.line_subtotal
        value = self.rebate_value or 0
        if self.rebate_type == self.REBATE_PERCENT:
            amount = subtotal * (value / 100)
            return min(amount, subtotal)
        if self.rebate_type == self.REBATE_AMOUNT:
            return min(value, subtotal)
        return 0

    @property
    def line_total(self):
        return self.line_subtotal - self.rebate_amount

    @property
    def vat_amount(self):
        return self.line_total * ((self.vat_percent or 0) / 100)
