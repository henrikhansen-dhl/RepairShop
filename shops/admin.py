from django.contrib import admin

from .models import (
    Customer,
    CustomerCar,
    Invoice,
    InvoiceLine,
    InvoiceNumberSeries,
    InvoicePriceItem,
    RepairWorkOrder,
    RepairWorkOrderLine,
    ShopMasterData,
    ShopProfile,
    ShopUserAccess,
)


class CustomerCarInline(admin.TabularInline):
    model = CustomerCar
    extra = 0
    fields = ("make", "model", "year", "plate_number", "vin", "tire_hotel_enabled")
    show_change_link = True


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    fields = ("description", "price_item", "quantity", "unit_price", "vat_percent", "rebate_type", "rebate_value")
    autocomplete_fields = ("price_item",)
    show_change_link = True


class RepairWorkOrderLineInline(admin.TabularInline):
    model = RepairWorkOrderLine
    extra = 0
    fields = ("line_type", "description", "price_item", "quantity", "unit_price", "vat_percent")
    autocomplete_fields = ("price_item",)
    show_change_link = True


@admin.register(ShopProfile)
class ShopProfileAdmin(admin.ModelAdmin):
    list_display = ("shop_name", "database_name", "owner", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("shop_name", "database_name", "owner__username", "owner__email")
    ordering = ("shop_name",)
    autocomplete_fields = ("owner",)


@admin.register(ShopUserAccess)
class ShopUserAccessAdmin(admin.ModelAdmin):
    list_display = (
        "shop",
        "user",
        "role",
        "preferred_language",
        "is_active",
        "can_manage_users",
        "can_create_repair_order",
        "can_manage_inventory",
        "can_view_reports",
    )
    list_filter = ("shop", "role", "preferred_language", "is_active")
    search_fields = ("shop__shop_name", "user__username", "user__email")
    ordering = ("shop__shop_name", "user__username")
    autocomplete_fields = ("shop", "user")


@admin.register(ShopMasterData)
class ShopMasterDataAdmin(admin.ModelAdmin):
    list_display = ("shop", "legal_name", "email", "phone", "updated_at")
    search_fields = ("shop__shop_name", "legal_name", "email", "phone", "vat_number")
    ordering = ("shop__shop_name",)
    autocomplete_fields = ("shop",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "shop", "phone", "email", "created_at")
    list_filter = ("shop", "created_at")
    search_fields = ("full_name", "phone", "email", "address", "shop__shop_name")
    ordering = ("full_name",)
    autocomplete_fields = ("shop",)
    inlines = (CustomerCarInline,)


@admin.register(CustomerCar)
class CustomerCarAdmin(admin.ModelAdmin):
    list_display = ("__str__", "customer", "plate_number", "vin", "tire_hotel_enabled", "next_inspection_date")
    list_filter = ("tire_hotel_enabled", "inspection_status", "customer__shop")
    search_fields = ("customer__full_name", "customer__shop__shop_name", "make", "model", "plate_number", "vin")
    ordering = ("customer__full_name", "make", "model")
    autocomplete_fields = ("customer",)


@admin.register(InvoicePriceItem)
class InvoicePriceItemAdmin(admin.ModelAdmin):
    list_display = ("description", "item_type", "code", "shop", "unit_price", "vat_percent", "is_active")
    list_filter = ("shop", "item_type", "is_active")
    search_fields = ("description", "code", "shop__shop_name")
    ordering = ("shop__shop_name", "item_type", "description")
    autocomplete_fields = ("shop",)


@admin.register(InvoiceNumberSeries)
class InvoiceNumberSeriesAdmin(admin.ModelAdmin):
    list_display = ("shop", "prefix", "next_number", "padding", "updated_at")
    search_fields = ("shop__shop_name", "prefix")
    ordering = ("shop__shop_name",)
    autocomplete_fields = ("shop",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "shop",
        "customer",
        "car",
        "issue_date",
        "due_date",
        "status",
        "grand_total_display",
    )
    list_filter = ("shop", "status", "issue_date")
    search_fields = ("invoice_number", "shop__shop_name", "customer__full_name", "car__plate_number")
    ordering = ("-issue_date", "-id")
    autocomplete_fields = ("shop", "customer", "car")
    inlines = (InvoiceLineInline,)
    date_hierarchy = "issue_date"
    readonly_fields = ("invoice_number", "created_at", "updated_at", "subtotal_display", "grand_total_display", "grand_total_incl_vat_display")

    @admin.display(description="Subtotal")
    def subtotal_display(self, obj):
        return f"{obj.subtotal:.2f}"

    @admin.display(description="Total ex VAT")
    def grand_total_display(self, obj):
        return f"{obj.grand_total:.2f}"

    @admin.display(description="Total incl VAT")
    def grand_total_incl_vat_display(self, obj):
        return f"{obj.grand_total_incl_vat:.2f}"


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ("description", "invoice", "price_item", "quantity", "unit_price", "vat_percent", "rebate_type")
    list_filter = ("invoice__shop", "rebate_type")
    search_fields = ("description", "invoice__invoice_number", "invoice__customer__full_name", "price_item__description")
    ordering = ("invoice__invoice_number", "id")
    autocomplete_fields = ("invoice", "price_item")


@admin.register(RepairWorkOrder)
class RepairWorkOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "shop",
        "customer",
        "car",
        "assigned_to",
        "priority",
        "status",
        "due_date",
        "invoice",
        "created_at",
    )
    list_filter = ("shop", "status", "priority", "due_date")
    search_fields = (
        "description",
        "customer__full_name",
        "car__plate_number",
        "assigned_to__username",
        "created_by__username",
        "invoice__invoice_number",
        "shop__shop_name",
    )
    ordering = ("-created_at",)
    autocomplete_fields = ("shop", "customer", "car", "created_by", "assigned_to", "invoice")
    inlines = (RepairWorkOrderLineInline,)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at", "service_total_display", "part_total_display", "subtotal_display")

    @admin.display(description="Service total")
    def service_total_display(self, obj):
        return f"{obj.service_total:.2f}"

    @admin.display(description="Part total")
    def part_total_display(self, obj):
        return f"{obj.part_total:.2f}"

    @admin.display(description="Subtotal")
    def subtotal_display(self, obj):
        return f"{obj.subtotal:.2f}"


@admin.register(RepairWorkOrderLine)
class RepairWorkOrderLineAdmin(admin.ModelAdmin):
    list_display = ("description", "work_order", "line_type", "price_item", "quantity", "unit_price", "vat_percent")
    list_filter = ("line_type", "work_order__shop")
    search_fields = ("description", "work_order__id", "work_order__customer__full_name", "price_item__description")
    ordering = ("work_order__id", "id")
    autocomplete_fields = ("work_order", "price_item")