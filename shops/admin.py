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

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status != Invoice.STATUS_DRAFT:
            return self.fields
        return ()

    def has_add_permission(self, request, obj=None):
        if obj and obj.status != Invoice.STATUS_DRAFT:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status != Invoice.STATUS_DRAFT:
            return False
        return super().has_delete_permission(request, obj)


class RepairWorkOrderLineInline(admin.TabularInline):
    model = RepairWorkOrderLine
    extra = 0
    fields = ("line_type", "description", "price_item", "quantity", "unit_price", "vat_percent")
    autocomplete_fields = ("price_item",)
    show_change_link = True

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.invoice_id:
            return self.fields
        return ()

    def has_add_permission(self, request, obj=None):
        if obj and obj.invoice_id:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.invoice_id:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(ShopProfile)
class ShopProfileAdmin(admin.ModelAdmin):
    list_display = ("shop_name", "database_name", "owner", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("shop_name", "database_name", "owner__username", "owner__email")
    ordering = ("shop_name",)
    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("shop_name", "database_name", "owner", "is_active")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


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
    fieldsets = (
        (None, {"fields": ("shop", "user", "role", "preferred_language", "is_active")}),
        ("Permissions", {"fields": ("can_manage_users", "can_create_repair_order", "can_manage_inventory", "can_view_reports")}),
    )


@admin.register(ShopMasterData)
class ShopMasterDataAdmin(admin.ModelAdmin):
    list_display = ("shop", "legal_name", "email", "phone", "updated_at")
    search_fields = ("shop__shop_name", "legal_name", "email", "phone", "vat_number")
    ordering = ("shop__shop_name",)
    autocomplete_fields = ("shop",)
    readonly_fields = ("updated_at",)
    fieldsets = (
        (None, {"fields": ("shop", "legal_name", "company_logo")}),
        ("Address", {"fields": ("address_line1", "address_line2", "postal_code", "city", "country")}),
        ("Contact", {"fields": ("phone", "email", "vat_number")}),
        ("Timestamps", {"fields": ("updated_at",)}),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "shop", "phone", "email", "created_at")
    list_filter = ("shop", "created_at")
    search_fields = ("full_name", "phone", "email", "address", "shop__shop_name")
    ordering = ("full_name",)
    autocomplete_fields = ("shop",)
    inlines = (CustomerCarInline,)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("shop", "full_name", "phone", "email")}),
        ("Details", {"fields": ("address", "notes")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(CustomerCar)
class CustomerCarAdmin(admin.ModelAdmin):
    list_display = ("__str__", "customer", "plate_number", "vin", "tire_hotel_enabled", "next_inspection_date")
    list_filter = ("tire_hotel_enabled", "inspection_status", "customer__shop")
    search_fields = ("customer__full_name", "customer__shop__shop_name", "make", "model", "plate_number", "vin")
    ordering = ("customer__full_name", "make", "model")
    autocomplete_fields = ("customer",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("customer", "make", "model", "year", "plate_number", "vin", "color")}),
        ("Inspection", {"fields": ("inspection_type", "inspection_date", "inspection_result", "inspection_status", "inspection_status_date", "inspection_mileage", "next_inspection_date")}),
        ("Tire Hotel", {"fields": ("tire_hotel_enabled", "tire_hotel_location", "tire_hotel_notes", "tire_label_count")}),
        ("Notes & Timestamps", {"fields": ("notes", "created_at", "updated_at")}),
    )


@admin.register(InvoicePriceItem)
class InvoicePriceItemAdmin(admin.ModelAdmin):
    list_display = ("description", "item_type", "code", "shop", "unit_price", "vat_percent", "is_active")
    list_filter = ("shop", "item_type", "is_active")
    search_fields = ("description", "code", "shop__shop_name")
    ordering = ("shop__shop_name", "item_type", "description")
    autocomplete_fields = ("shop",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("shop", "item_type", "code", "description")}),
        ("Pricing", {"fields": ("unit_price", "vat_percent", "is_active")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(InvoiceNumberSeries)
class InvoiceNumberSeriesAdmin(admin.ModelAdmin):
    list_display = ("shop", "prefix", "next_number", "padding", "updated_at")
    search_fields = ("shop__shop_name", "prefix")
    ordering = ("shop__shop_name",)
    autocomplete_fields = ("shop",)
    readonly_fields = ("updated_at",)


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
    fieldsets = (
        (None, {"fields": ("shop", "customer", "car", "invoice_number", "status")}),
        ("Dates", {"fields": ("issue_date", "due_date")}),
        ("Rebate & Notes", {"fields": ("total_rebate_type", "total_rebate_value", "notes")}),
        ("Totals", {"fields": ("subtotal_display", "grand_total_display", "grand_total_incl_vat_display")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.status != Invoice.STATUS_DRAFT:
            readonly_fields.extend([
                "shop",
                "customer",
                "car",
                "issue_date",
                "due_date",
                "status",
                "total_rebate_type",
                "total_rebate_value",
                "notes",
            ])
        return tuple(dict.fromkeys(readonly_fields))

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

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.invoice.status != Invoice.STATUS_DRAFT:
            return ("invoice", "price_item", "description", "quantity", "unit_price", "vat_percent", "rebate_type", "rebate_value")
        return ()

    def has_delete_permission(self, request, obj=None):
        if obj and obj.invoice.status != Invoice.STATUS_DRAFT:
            return False
        return super().has_delete_permission(request, obj)


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
    fieldsets = (
        (None, {"fields": ("shop", "customer", "car", "description", "technician_notes")}),
        ("Assignment & Workflow", {"fields": ("created_by", "assigned_to", "priority", "due_date", "status", "invoice")}),
        ("Totals", {"fields": ("service_total_display", "part_total_display", "subtotal_display")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.invoice_id:
            readonly_fields.extend([
                "shop",
                "customer",
                "car",
                "description",
                "technician_notes",
                "created_by",
                "assigned_to",
                "priority",
                "due_date",
                "status",
                "invoice",
            ])
        return tuple(dict.fromkeys(readonly_fields))

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

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.work_order.invoice_id:
            return ("work_order", "line_type", "price_item", "description", "quantity", "unit_price", "vat_percent")
        return ()

    def has_delete_permission(self, request, obj=None):
        if obj and obj.work_order.invoice_id:
            return False
        return super().has_delete_permission(request, obj)