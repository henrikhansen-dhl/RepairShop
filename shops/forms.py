from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import get_language, gettext_lazy as _
import secrets
import string

from .models import Customer, CustomerCar, Invoice, InvoiceLine, InvoicePriceItem, RepairWorkOrder, RepairWorkOrderLine, ShopMasterData, ShopProfile, ShopUserAccess, default_shop_features


class WorkOrderPriceItemSelect(forms.Select):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item_type_by_value = {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        value_key = str(option.get("value") or "")
        item_type = self.item_type_by_value.get(value_key)
        if item_type:
            option.setdefault("attrs", {})["data-item-type"] = item_type
        return option


class WorkOrderPriceItemChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        type_label = _("Service") if obj.item_type == InvoicePriceItem.TYPE_SERVICE else _("Part")
        code_text = f"{obj.code} - " if obj.code else ""
        return f"[{type_label}] {code_text}{obj.description}"


def generate_strong_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class ShopOnboardingForm(forms.Form):
    shop_name = forms.CharField(max_length=120, label=_("Shop name"))
    username = forms.CharField(max_length=150, label=_("Login username"))
    email = forms.EmailField(required=False, label=_("Email"))
    enabled_features = forms.MultipleChoiceField(
        required=False,
        choices=ShopProfile.FEATURE_CHOICES,
        initial=default_shop_features(),
        widget=forms.CheckboxSelectMultiple,
        label=_("Paid functions"),
        help_text=_("Only selected functions will be visible and usable for this shop."),
    )
    generate_password = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Generate strong password automatically"),
        help_text=_("If checked, the system generates a strong temporary password."),
    )
    password1 = forms.CharField(widget=forms.PasswordInput, required=False, label=_("Temporary password"))
    password2 = forms.CharField(widget=forms.PasswordInput, required=False, label=_("Confirm password"))
    database_name = forms.CharField(
        max_length=64,
        required=False,
        label=_("Database alias (optional)"),
        help_text=_("Optional alias, for example: downtown_db. Leave blank to auto-generate."),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            raise forms.ValidationError(_("This username already exists."))
        return username

    def clean(self):
        cleaned_data = super().clean()
        generate_password = cleaned_data.get("generate_password", False)
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if generate_password:
            generated = generate_strong_password()
            cleaned_data["password1"] = generated
            cleaned_data["password2"] = generated
            self.generated_password = generated
        else:
            if not password1:
                self.add_error("password1", _("Enter a password or enable auto-generation."))
            if password1 and len(password1) < 8:
                self.add_error("password1", _("Use at least 8 characters."))
            if password1 and password2 and password1 != password2:
                self.add_error("password2", _("Passwords do not match."))
            self.generated_password = password1 or ""

        db_alias = cleaned_data.get("database_name", "").strip()
        if not db_alias:
            shop_slug = slugify(cleaned_data.get("shop_name", ""))
            db_alias = f"{shop_slug.replace('-', '_')}_db" if shop_slug else "shop_db"

        cleaned_data["database_name"] = db_alias

        if ShopProfile.objects.filter(database_name=db_alias).exists():
            self.add_error("database_name", _("This database alias is already in use."))

        return cleaned_data

    @transaction.atomic
    def save(self):
        user_model = get_user_model()
        plain_password = self.cleaned_data["password1"]
        user = user_model.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data.get("email", ""),
            password=plain_password,
            is_active=True,
        )

        shop_profile = ShopProfile.objects.create(
            owner=user,
            shop_name=self.cleaned_data["shop_name"],
            database_name=self.cleaned_data["database_name"],
            is_active=True,
            enabled_features=self.cleaned_data.get("enabled_features", []),
        )

        ShopUserAccess.objects.create(
            shop=shop_profile,
            user=user,
            role=ShopUserAccess.ROLE_OWNER,
            preferred_language=ShopUserAccess.LANGUAGE_EN,
            can_manage_users=True,
            can_create_repair_order=True,
            can_manage_inventory=True,
            can_view_reports=True,
            is_active=True,
        )

        return user, shop_profile, plain_password


def _date_placeholder_for_language(language_code: str) -> str:
    language_prefix = (language_code or "en").split("-")[0].lower()
    if language_prefix == "da":
        return "dd/mm/yyyy"
    if language_prefix == "de":
        return "dd.mm.yyyy"
    return "yyyy-mm-dd"


def _configure_localized_date_field(field: forms.Field, language_code: str) -> None:
    language_prefix = (language_code or "en").split("-")[0].lower()
    if language_prefix == "da":
        input_formats = ["%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d"]
        display_format = "%d/%m/%Y"
    elif language_prefix == "de":
        input_formats = ["%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]
        display_format = "%d.%m.%Y"
    else:
        input_formats = ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d.%m.%Y"]
        display_format = "%Y-%m-%d"

    field.input_formats = input_formats
    attrs = dict(getattr(field.widget, "attrs", {}))
    attrs["type"] = "text"
    attrs.setdefault("class", "js-local-date")
    attrs.setdefault("autocomplete", "off")
    attrs.setdefault("placeholder", _date_placeholder_for_language(language_code))
    field.widget = forms.DateInput(format=display_format, attrs=attrs)


class RepairWorkOrderForm(forms.ModelForm):
    class Meta:
        model = RepairWorkOrder
        fields = ["customer", "car", "description", "technician_notes", "assigned_to", "priority", "due_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "technician_notes": forms.Textarea(attrs={"rows": 5}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "customer": _("Customer"),
            "car": _("Car"),
            "description": _("Description"),
            "technician_notes": _("Mechanic notes"),
            "assigned_to": _("Assigned to"),
            "priority": _("Priority"),
            "due_date": _("Due date"),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        shop = kwargs.pop("shop", None)
        super().__init__(*args, **kwargs)
        accessible_users = get_user_model().objects.none()

        if shop is not None:
            self.fields["customer"].queryset = Customer.objects.filter(shop=shop).order_by("full_name")
            car_queryset = CustomerCar.objects.filter(customer__shop=shop).select_related("customer").order_by(
                "customer__full_name", "make", "model"
            )
            accessible_users = get_user_model().objects.filter(
                shop_accesses__shop=shop,
                shop_accesses__is_active=True,
            ).order_by("username").distinct()
        elif user is not None:
            accessible_shops = ShopProfile.objects.filter(
                user_accesses__user=user,
                user_accesses__is_active=True,
            )
            self.fields["customer"].queryset = Customer.objects.filter(shop__in=accessible_shops).order_by("full_name")
            car_queryset = CustomerCar.objects.filter(customer__shop__in=accessible_shops).select_related("customer").order_by(
                "customer__full_name", "make", "model"
            )
            accessible_users = get_user_model().objects.filter(
                shop_accesses__shop__in=accessible_shops,
                shop_accesses__is_active=True,
            ).order_by("username").distinct()

        else:
            self.fields["customer"].queryset = Customer.objects.none()
            car_queryset = CustomerCar.objects.none()

        selected_customer_id = None
        if self.is_bound:
            selected_customer_id = self.data.get("customer") or None
        elif self.instance.pk and self.instance.customer_id:
            selected_customer_id = str(self.instance.customer_id)
        elif self.initial.get("customer"):
            selected_customer_id = str(self.initial.get("customer"))

        if selected_customer_id:
            car_queryset = car_queryset.filter(customer_id=selected_customer_id)

        self.fields["car"].queryset = car_queryset
        self.fields["assigned_to"].queryset = accessible_users
        self.fields["assigned_to"].required = False

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get("customer")
        car = cleaned_data.get("car")
        if customer and car and car.customer_id != customer.pk:
            self.add_error("car", _("Selected car does not belong to the chosen customer."))
        return cleaned_data

    def save(self, commit=True):
        work_order = super().save(commit=False)
        if work_order.pk:
            if work_order.assigned_to and work_order.status == RepairWorkOrder.STATUS_NEW:
                work_order.status = RepairWorkOrder.STATUS_ASSIGNED
            elif not work_order.assigned_to and work_order.status == RepairWorkOrder.STATUS_ASSIGNED:
                work_order.status = RepairWorkOrder.STATUS_NEW
        else:
            work_order.status = (
                RepairWorkOrder.STATUS_ASSIGNED if work_order.assigned_to else RepairWorkOrder.STATUS_NEW
            )

        if commit:
            work_order.save()
        return work_order


class RepairWorkOrderLineForm(forms.ModelForm):
    class Meta:
        model = RepairWorkOrderLine
        fields = ["line_type", "price_item", "description", "quantity", "unit_price", "vat_percent"]
        widgets = {
            "line_type": forms.Select(attrs={"class": "line-type-select"}),
        }
        labels = {
            "line_type": _("Line type"),
            "price_item": _("Price item"),
            "description": _("Line description"),
            "quantity": _("Quantity"),
            "unit_price": _("Unit price"),
            "vat_percent": _("VAT %"),
        }

    def __init__(self, shop: ShopProfile, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shop = shop
        price_items = InvoicePriceItem.objects.filter(shop=shop, is_active=True).order_by(
            "item_type", "description"
        )
        widget = WorkOrderPriceItemSelect()
        widget.item_type_by_value = {str(item.pk): item.item_type for item in price_items}
        self.fields["price_item"] = WorkOrderPriceItemChoiceField(
            queryset=price_items,
            required=False,
            label=_("Price item"),
            widget=widget,
        )
        self.fields["price_item"].empty_label = _("Choose a price item")
        self.fields["description"].required = False
        self.fields["unit_price"].required = False
        self.fields["vat_percent"].required = False

    def clean(self):
        cleaned_data = super().clean()
        price_item = cleaned_data.get("price_item")
        if price_item:
            cleaned_data["line_type"] = price_item.item_type
            if not cleaned_data.get("description"):
                cleaned_data["description"] = price_item.description
            if cleaned_data.get("unit_price") in (None, ""):
                cleaned_data["unit_price"] = price_item.unit_price
            if cleaned_data.get("vat_percent") in (None, ""):
                cleaned_data["vat_percent"] = price_item.vat_percent
        else:
            if not cleaned_data.get("description"):
                self.add_error("description", _("Enter a description or choose a price item."))
            if cleaned_data.get("unit_price") in (None, ""):
                self.add_error("unit_price", _("Enter a unit price or choose a price item."))
            if cleaned_data.get("vat_percent") in (None, ""):
                cleaned_data["vat_percent"] = 25
        return cleaned_data


class ShopEditForm(forms.ModelForm):
    username = forms.CharField(max_length=150, label=_("Login username"))
    email = forms.EmailField(required=False, label=_("Email"))
    enabled_features = forms.MultipleChoiceField(
        required=False,
        choices=ShopProfile.FEATURE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label=_("Paid functions"),
        help_text=_("Only selected functions will be visible and usable for this shop."),
    )
    owner_is_active = forms.BooleanField(required=False, initial=True, label=_("Owner user is active"))
    reset_password = forms.BooleanField(
        required=False,
        label=_("Reset password to a new random value"),
        help_text=_("Generate a new temporary password for this shop user."),
    )

    class Meta:
        model = ShopProfile
        fields = ["shop_name", "database_name", "is_active", "enabled_features"]
        labels = {
            "shop_name": _("Shop name"),
            "database_name": _("Database alias"),
            "is_active": _("Shop is active"),
            "enabled_features": _("Paid functions"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        owner = self.instance.owner
        self.fields["username"].initial = owner.username
        self.fields["email"].initial = owner.email
        self.fields["owner_is_active"].initial = owner.is_active
        self.fields["enabled_features"].initial = self.instance.get_enabled_features()

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        user_model = get_user_model()
        qs = user_model.objects.filter(username=username).exclude(pk=self.instance.owner.pk)
        if qs.exists():
            raise forms.ValidationError(_("This username already exists."))
        return username

    def clean_database_name(self):
        value = self.cleaned_data["database_name"].strip()
        if ShopProfile.objects.filter(database_name=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("This database alias is already in use."))
        return value

    @transaction.atomic
    def save(self, commit=True):
        shop = super().save(commit=False)
        owner = shop.owner
        owner.username = self.cleaned_data["username"]
        owner.email = self.cleaned_data.get("email", "")
        owner.is_active = self.cleaned_data.get("owner_is_active", True)
        shop.enabled_features = self.cleaned_data.get("enabled_features", [])

        generated_password = ""
        if self.cleaned_data.get("reset_password"):
            generated_password = generate_strong_password()
            owner.set_password(generated_password)

        if commit:
            owner.save()
            shop.save()

        return shop, generated_password


class ShopUserAccessCreateForm(forms.Form):
    create_new_user = forms.BooleanField(required=False, initial=True, label=_("Create new user account"))
    existing_user = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(),
        required=False,
        label=_("Existing user"),
        help_text=_("Choose an existing user when not creating a new account."),
    )
    username = forms.CharField(max_length=150, required=False, label=_("New username"))
    email = forms.EmailField(required=False, label=_("New user email"))
    generate_password = forms.BooleanField(required=False, initial=True, label=_("Generate password"))
    password1 = forms.CharField(widget=forms.PasswordInput, required=False, label=_("Password"))
    password2 = forms.CharField(widget=forms.PasswordInput, required=False, label=_("Confirm password"))
    role = forms.ChoiceField(choices=ShopUserAccess.ROLE_CHOICES, initial=ShopUserAccess.ROLE_CLERK, label=_("Role"))
    preferred_language = forms.ChoiceField(choices=ShopUserAccess.LANGUAGE_CHOICES, initial=ShopUserAccess.LANGUAGE_EN, label=_("Preferred language"))
    can_manage_users = forms.BooleanField(required=False, label=_("Can manage users"))
    can_create_repair_order = forms.BooleanField(required=False, initial=True, label=_("Can create repair orders"))
    can_manage_inventory = forms.BooleanField(required=False, label=_("Can manage inventory"))
    can_view_reports = forms.BooleanField(required=False, label=_("Can view reports"))
    is_active = forms.BooleanField(required=False, initial=True, label=_("Access active"))

    def __init__(self, shop: ShopProfile, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shop = shop
        already_member_ids = shop.user_accesses.values_list("user_id", flat=True)
        self.fields["existing_user"].queryset = get_user_model().objects.exclude(pk__in=already_member_ids).order_by("username")

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if self.cleaned_data.get("create_new_user") and not username:
            raise forms.ValidationError(_("Enter a username for the new user."))
        if username and get_user_model().objects.filter(username=username).exists():
            raise forms.ValidationError(_("This username already exists."))
        return username

    def clean(self):
        cleaned_data = super().clean()
        create_new = cleaned_data.get("create_new_user", False)

        if not create_new and not cleaned_data.get("existing_user"):
            self.add_error("existing_user", _("Select an existing user or create a new one."))

        if create_new:
            generate_password = cleaned_data.get("generate_password", False)
            password1 = cleaned_data.get("password1")
            password2 = cleaned_data.get("password2")
            if generate_password:
                generated = generate_strong_password()
                cleaned_data["password1"] = generated
                cleaned_data["password2"] = generated
                self.generated_password = generated
            else:
                if not password1:
                    self.add_error("password1", _("Enter a password or enable auto-generation."))
                if password1 and len(password1) < 8:
                    self.add_error("password1", _("Use at least 8 characters."))
                if password1 and password2 and password1 != password2:
                    self.add_error("password2", _("Passwords do not match."))
                self.generated_password = password1 or ""
        else:
            self.generated_password = ""

        return cleaned_data

    @transaction.atomic
    def save(self):
        create_new = self.cleaned_data.get("create_new_user", False)

        if create_new:
            user = get_user_model().objects.create_user(
                username=self.cleaned_data["username"],
                email=self.cleaned_data.get("email", ""),
                password=self.cleaned_data["password1"],
                is_active=True,
            )
            plain_password = self.cleaned_data["password1"]
        else:
            user = self.cleaned_data["existing_user"]
            plain_password = ""

        access, created = ShopUserAccess.objects.update_or_create(
            shop=self.shop,
            user=user,
            defaults={
                "role": self.cleaned_data["role"],
                "preferred_language": self.cleaned_data["preferred_language"],
                "can_manage_users": self.cleaned_data.get("can_manage_users", False),
                "can_create_repair_order": self.cleaned_data.get("can_create_repair_order", False),
                "can_manage_inventory": self.cleaned_data.get("can_manage_inventory", False),
                "can_view_reports": self.cleaned_data.get("can_view_reports", False),
                "is_active": self.cleaned_data.get("is_active", False),
            },
        )

        return access, created, plain_password


class ShopUserAccessEditForm(forms.ModelForm):
    class Meta:
        model = ShopUserAccess
        fields = [
            "role",
            "preferred_language",
            "can_manage_users",
            "can_create_repair_order",
            "can_manage_inventory",
            "can_view_reports",
            "is_active",
        ]
        labels = {
            "role": _("Role"),
            "preferred_language": _("Preferred language"),
            "can_manage_users": _("Can manage users"),
            "can_create_repair_order": _("Can create repair orders"),
            "can_manage_inventory": _("Can manage inventory"),
            "can_view_reports": _("Can view reports"),
            "is_active": _("Access active"),
        }


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["full_name", "phone", "email", "address", "payment_due_condition", "payment_due_days", "notes"]
        widgets = {
            "payment_due_days": forms.NumberInput(attrs={"min": 0}),
        }
        labels = {
            "full_name": _("Name"),
            "phone": _("Phone"),
            "email": _("Email"),
            "address": _("Address"),
            "payment_due_condition": _("Payment due date condition"),
            "payment_due_days": _("Payment due days"),
            "notes": _("Notes"),
        }


class CustomerCarForm(forms.ModelForm):
    class Meta:
        model = CustomerCar
        fields = [
            "make",
            "model",
            "year",
            "plate_number",
            "vin",
            "color",
            "notes",
            "tire_hotel_enabled",
            "tire_hotel_location",
            "tire_hotel_notes",
            "tire_label_count",
            "inspection_type",
            "inspection_date",
            "inspection_result",
            "inspection_status",
            "inspection_status_date",
            "inspection_mileage",
            "next_inspection_date",
        ]
        widgets = {
            "inspection_type": forms.HiddenInput(),
            "inspection_date": forms.HiddenInput(),
            "inspection_result": forms.HiddenInput(),
            "inspection_status": forms.HiddenInput(),
            "inspection_status_date": forms.HiddenInput(),
            "inspection_mileage": forms.HiddenInput(),
            "next_inspection_date": forms.HiddenInput(),
        }
        labels = {
            "make": _("Make"),
            "model": _("Model"),
            "year": _("Year"),
            "plate_number": _("Plate number"),
            "vin": _("VIN"),
            "color": _("Color"),
            "notes": _("Notes"),
            "tire_hotel_enabled": _("Tire hotel enabled"),
            "tire_hotel_location": _("Tire hotel location"),
            "tire_hotel_notes": _("Tire hotel notes"),
            "tire_label_count": _("Tire label count"),
            "inspection_type": _("Inspection type"),
            "inspection_date": _("Inspection date"),
            "inspection_result": _("Inspection result"),
            "inspection_status": _("Inspection status"),
            "inspection_status_date": _("Inspection status date"),
            "inspection_mileage": _("Inspection mileage"),
            "next_inspection_date": _("Next inspection date"),
        }


class InvoicePriceItemForm(forms.ModelForm):
    class Meta:
        model = InvoicePriceItem
        fields = ["item_type", "code", "description", "unit_price", "vat_percent", "is_active"]
        labels = {
            "item_type": _("Type"),
            "code": _("Code"),
            "description": _("Description"),
            "unit_price": _("Unit Price"),
            "vat_percent": _("VAT %"),
            "is_active": _("Active"),
        }


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            "customer",
            "car",
            "issue_date",
            "due_date",
            "status",
            "total_rebate_type",
            "total_rebate_value",
            "notes",
        ]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "text"}),
            "due_date": forms.DateInput(attrs={"type": "text"}),
        }
        labels = {
            "customer": _("Customer"),
            "car": _("Car"),
            "issue_date": _("Issue Date"),
            "due_date": _("Due Date"),
            "status": _("Status"),
            "total_rebate_type": _("Total rebate type"),
            "total_rebate_value": _("Total rebate value"),
            "notes": _("Notes"),
        }

    def __init__(self, shop: ShopProfile, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shop = shop
        language_code = get_language() or "en"
        _configure_localized_date_field(self.fields["issue_date"], language_code)
        _configure_localized_date_field(self.fields["due_date"], language_code)
        self.fields["notes"].widget.attrs.setdefault("rows", 2)
        self.fields["due_date"].required = False
        self.fields["customer"].queryset = Customer.objects.filter(shop=shop).order_by("full_name")
        car_queryset = CustomerCar.objects.filter(customer__shop=shop).select_related("customer").order_by("customer__full_name", "make", "model")

        selected_customer_id = None
        if self.is_bound:
            selected_customer_id = self.data.get("customer") or None
        elif self.instance.pk and self.instance.customer_id:
            selected_customer_id = str(self.instance.customer_id)
        elif self.initial.get("customer"):
            selected_customer_id = str(self.initial.get("customer"))

        if selected_customer_id:
            car_queryset = car_queryset.filter(customer_id=selected_customer_id)

        self.fields["car"].queryset = car_queryset
        if not self.instance.pk:
            self.fields["issue_date"].initial = timezone.localdate()
            self.fields["status"].initial = Invoice.STATUS_DRAFT

        selected_customer = self.fields["customer"].queryset.filter(pk=selected_customer_id).first() if selected_customer_id else None
        issue_date = self.initial.get("issue_date") or getattr(self.instance, "issue_date", None) or self.fields["issue_date"].initial
        if selected_customer and issue_date and not self.instance.pk:
            calculated_due_date = selected_customer.calculate_invoice_due_date(issue_date)
            if calculated_due_date is not None:
                self.fields["due_date"].initial = calculated_due_date

    def clean_car(self):
        car = self.cleaned_data.get("car")
        if car and car.customer.shop_id != self.shop.pk:
            raise forms.ValidationError(_("Selected car does not belong to this shop."))
        return car

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get("customer")
        car = cleaned_data.get("car")
        issue_date = cleaned_data.get("issue_date")
        if customer and customer.shop_id != self.shop.pk:
            self.add_error("customer", _("Selected customer does not belong to this shop."))
        if customer and car and car.customer_id != customer.pk:
            self.add_error("car", _("Selected car does not belong to the chosen customer."))
        if customer and issue_date:
            calculated_due_date = customer.calculate_invoice_due_date(issue_date)
            if calculated_due_date is not None:
                cleaned_data["due_date"] = calculated_due_date
        return cleaned_data


class InvoiceLineForm(forms.ModelForm):
    class Meta:
        model = InvoiceLine
        fields = [
            "price_item",
            "description",
            "quantity",
            "unit_price",
            "vat_percent",
            "rebate_type",
            "rebate_value",
        ]
        labels = {
            "price_item": _("Price item"),
            "description": _("Description"),
            "quantity": _("Qty"),
            "unit_price": _("Unit Price"),
            "vat_percent": _("VAT %"),
            "rebate_type": _("Rebate type"),
            "rebate_value": _("Rebate value"),
        }

    def __init__(self, shop: ShopProfile, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shop = shop
        self.fields["price_item"].required = False
        self.fields["description"].required = False
        self.fields["unit_price"].required = False
        self.fields["vat_percent"].required = False
        self.fields["price_item"].queryset = InvoicePriceItem.objects.filter(shop=shop, is_active=True).order_by("item_type", "description")

    def clean(self):
        cleaned_data = super().clean()
        price_item = cleaned_data.get("price_item")
        description = (cleaned_data.get("description") or "").strip()
        unit_price = cleaned_data.get("unit_price")

        if price_item and price_item.shop_id != self.shop.pk:
            self.add_error("price_item", _("Selected price item does not belong to this shop."))

        if not price_item and not description:
            self.add_error("description", _("Provide a manual description or choose a price item."))

        if not price_item and unit_price is None:
            self.add_error("unit_price", _("Provide a unit price for manual lines."))

        if cleaned_data.get("vat_percent") is None:
            cleaned_data["vat_percent"] = price_item.vat_percent if price_item else 25

        return cleaned_data


class ShopMasterDataForm(forms.ModelForm):
    class Meta:
        model = ShopMasterData
        fields = [
            "legal_name",
            "address_line1",
            "address_line2",
            "postal_code",
            "city",
            "country",
            "phone",
            "email",
            "vat_number",
            "company_logo",
        ]
        labels = {
            "legal_name": _("Legal name"),
            "address_line1": _("Address line 1"),
            "address_line2": _("Address line 2"),
            "postal_code": _("Postal code"),
            "city": _("City"),
            "country": _("Country"),
            "phone": _("Phone"),
            "email": _("Email"),
            "vat_number": _("VAT number"),
            "company_logo": _("Company logo"),
        }


class InvoiceEmailForm(forms.Form):
    recipient_email = forms.EmailField(label=_("Recipient email"))
    subject = forms.CharField(max_length=220, label=_("Subject"))
    message = forms.CharField(widget=forms.Textarea, required=False, label=_("Message"))
    attach_pdf = forms.BooleanField(required=False, initial=True, label=_("Attach PDF copy"))
