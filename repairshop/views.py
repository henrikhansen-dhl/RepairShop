import base64
import io
import json
import os
import re
import ssl
from urllib import error as urllib_error
from urllib import request as urllib_request

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.conf import settings as django_settings
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from repairshop.access_control import get_shop_context_for_user, require_shop_right
from repairshop.tenant_db import ensure_tenant_database_alias
from shops.forms import (
    CustomerCarForm,
    CustomerForm,
    InvoiceForm,
    InvoiceEmailForm,
    InvoiceLineForm,
    InvoicePriceItemForm,
    RepairWorkOrderLineForm,
    RepairWorkOrderForm,
    ShopMasterDataForm,
    ShopEditForm,
    ShopOnboardingForm,
    ShopUserAccessCreateForm,
    ShopUserAccessEditForm,
)
from shops.models import Customer, CustomerCar, Invoice, InvoiceLine, InvoicePriceItem, RepairWorkOrder, RepairWorkOrderLine, ShopMasterData, ShopProfile, ShopUserAccess


INVOICE_PUBLIC_LINK_SALT = "invoice-public-link"
INVOICE_PUBLIC_LINK_MAX_AGE_SECONDS = 60 * 60 * 24 * 90  # 90 days


def _build_public_invoice_token(invoice_id: int) -> str:
    return signing.dumps({"invoice_id": invoice_id}, salt=INVOICE_PUBLIC_LINK_SALT, compress=True)


def _load_public_invoice_token(token: str) -> dict:
    return signing.loads(
        token,
        salt=INVOICE_PUBLIC_LINK_SALT,
        max_age=INVOICE_PUBLIC_LINK_MAX_AGE_SECONDS,
    )


def _generate_invoice_pdf_bytes(*, shop, master_data, invoice, lines, printed_at):
    """Build a simple A4 invoice PDF in memory for email attachment."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError("PDF generation dependency is missing. Install reportlab.") from exc

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 40
    y = height - margin

    def draw_line(text, *, size=10, gap=14):
        nonlocal y
        if y < 60:
            pdf.showPage()
            y = height - margin
        pdf.setFont("Helvetica", size)
        pdf.drawString(margin, y, text)
        y -= gap

    def draw_pair(label, value):
        nonlocal y
        if y < 60:
            pdf.showPage()
            y = height - margin
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margin, y, f"{label}:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(margin + 110, y, str(value or "-"))
        y -= 14

    sender_name = master_data.legal_name or shop.shop_name

    draw_line(f"Invoice {invoice.invoice_number}", size=16, gap=22)
    draw_pair("Issue Date", invoice.issue_date)
    draw_pair("Due Date", invoice.due_date or "-")
    draw_pair("Status", invoice.get_status_display())
    y -= 4

    draw_line("From", size=12, gap=16)
    draw_line(sender_name)
    if master_data.address_line1:
        draw_line(master_data.address_line1)
    if master_data.address_line2:
        draw_line(master_data.address_line2)
    city_line = f"{master_data.postal_code or ''} {master_data.city or ''}".strip()
    if city_line:
        draw_line(city_line)
    if master_data.country:
        draw_line(master_data.country)
    if master_data.phone:
        draw_line(f"Phone: {master_data.phone}")
    if master_data.email:
        draw_line(f"Email: {master_data.email}")
    if master_data.vat_number:
        draw_line(f"VAT: {master_data.vat_number}")
    y -= 4

    draw_line("To", size=12, gap=16)
    draw_line(invoice.customer.full_name)
    if invoice.customer.address:
        for address_line in str(invoice.customer.address).splitlines():
            draw_line(address_line)
    if invoice.customer.phone:
        draw_line(f"Phone: {invoice.customer.phone}")
    if invoice.customer.email:
        draw_line(f"Email: {invoice.customer.email}")
    if invoice.car:
        draw_line(f"Car: {invoice.car}")
    y -= 6

    draw_line("Lines", size=12, gap=16)
    for line in lines:
        desc = (line.description or "")[:64]
        qty = line.quantity
        unit = f"{line.unit_price:.2f}"
        total = f"{line.line_total:.2f}"
        draw_line(f"- {desc}")
        draw_line(f"  Qty: {qty}  Unit: {unit}  VAT%: {line.vat_percent}  Total ex VAT: {total}")

    y -= 6
    draw_pair("Subtotal", f"{invoice.subtotal:.2f}")
    if invoice.line_rebate_amount:
        draw_pair("Line Rebate", f"{invoice.line_rebate_amount:.2f}")
    if invoice.invoice_rebate_amount:
        draw_pair("Invoice Rebate", f"{invoice.invoice_rebate_amount:.2f}")
    draw_pair("Total Rebate", f"{invoice.total_rebate_amount:.2f}")
    draw_pair("Total ex VAT", f"{invoice.grand_total:.2f}")
    draw_pair("VAT Total", f"{invoice.vat_total:.2f}")
    draw_pair("Grand Total incl VAT", f"{invoice.grand_total_incl_vat:.2f}")
    draw_pair("Printed", printed_at.strftime("%Y-%m-%d %H:%M"))

    if invoice.notes:
        y -= 6
        draw_line("Notes", size=12, gap=16)
        for note_line in str(invoice.notes).splitlines():
            draw_line(note_line)

    pdf.save()
    return buffer.getvalue()


PLATE_REGEX = re.compile(r"^[A-Z]{2}\d{5}$")


def _normalize_plate(value: str) -> str:
    """Normalize user input to expected Danish plate format, for example AB12345."""
    compact = (value or "").upper().replace(" ", "").replace("-", "")
    return compact


def _extract_first(payload: dict, keys: tuple[str, ...], default=""):
    """Read first matching key from payload and nested 'vehicle' object."""
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return payload.get(key)

    vehicle_data = payload.get("vehicle") if isinstance(payload, dict) else None
    if isinstance(vehicle_data, dict):
        for key in keys:
            if key in vehicle_data and vehicle_data.get(key) not in (None, ""):
                return vehicle_data.get(key)

    return default


def _build_vehicle_notes(payload: dict) -> str:
    """Build a compact notes summary from optional MotorAPI vehicle fields."""
    if not isinstance(payload, dict):
        return ""

    notes_parts = []

    variant = _extract_first(payload, ("variant",))
    fuel_type = _extract_first(payload, ("fuel_type", "fuel"))
    engine_power = _extract_first(payload, ("engine_power",))
    first_registration = _extract_first(payload, ("first_registration",))
    status = _extract_first(payload, ("status",))

    if variant:
        notes_parts.append(f"Variant: {variant}")
    if fuel_type:
        notes_parts.append(f"Fuel: {fuel_type}")
    if engine_power not in ("", None):
        notes_parts.append(f"Engine Power: {engine_power} kW")
    if first_registration:
        notes_parts.append(f"First Registration: {first_registration}")
    if status:
        notes_parts.append(f"Registration Status: {status}")

    mot_info = payload.get("mot_info") if isinstance(payload, dict) else None
    if isinstance(mot_info, dict):
        inspection_parts = []
        mot_type = mot_info.get("type")
        mot_date = mot_info.get("date")
        mot_result = mot_info.get("result")
        mot_status = mot_info.get("status")
        mot_status_date = mot_info.get("status_date")
        mot_mileage = mot_info.get("mileage")
        next_inspection = mot_info.get("next_inspection_date")

        if mot_type:
            inspection_parts.append(f"Inspection Type: {mot_type}")
        if mot_date:
            inspection_parts.append(f"Inspection Date: {mot_date}")
        if mot_result:
            inspection_parts.append(f"Inspection Result: {mot_result}")
        if mot_status:
            inspection_parts.append(f"Inspection Status: {mot_status}")
        if mot_status_date:
            inspection_parts.append(f"Inspection Status Date: {mot_status_date}")
        if mot_mileage not in (None, ""):
            inspection_parts.append(f"Mileage at Inspection: {mot_mileage}")
        if next_inspection:
            inspection_parts.append(f"Next Inspection: {next_inspection}")

        if inspection_parts:
            notes_parts.append("MOT: " + ", ".join(inspection_parts))

    return " | ".join(notes_parts)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _qr_png_data_uri(text: str) -> str:
    """Generate a PNG data-URI QR code for label printing."""
    try:
        import qrcode
    except ImportError:
        return ""

    qr = qrcode.QRCode(version=1, box_size=4, border=1)
    qr.add_data(text)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _customer_payment_terms_payload(shop):
    return list(
        Customer.objects.filter(shop=shop)
        .order_by("full_name", "id")
        .values("id", "payment_due_condition", "payment_due_days")
    )


def landing_page(request):
    return render(request, "landing.html")


@login_required
def shop_dashboard(request):
    shop_context = get_shop_context_for_user(request.user)
    return render(
        request,
        "shop_dashboard.html",
        {
            "shop_context": shop_context,
            "shop": shop_context["shop"] if shop_context else None,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_REPAIR_ORDERS)
def create_repair_order(request):
    user = request.user
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Repair orders are available for shop users only.")

    initial = {}
    customer_id = request.GET.get("customer")
    car_id = request.GET.get("car")
    if customer_id:
        initial["customer"] = customer_id
    if car_id:
        initial["car"] = car_id

    work_orders = (
        RepairWorkOrder.objects.filter(shop=shop)
        .select_related("customer", "car", "assigned_to", "invoice")
        .prefetch_related("service_lines")
        .order_by("-created_at")
    )

    form = RepairWorkOrderForm(user=user, shop=shop)
    if request.method == "POST":
        form = RepairWorkOrderForm(request.POST, user=user, shop=shop)
        if form.is_valid():
            work_order = form.save(commit=False)
            work_order.created_by = user
            work_order.shop = shop
            work_order.save()
            messages.success(request, f"Work order #{work_order.pk} created.")
            return redirect("repair_work_order_detail", work_order_id=work_order.pk)
    else:
        form = RepairWorkOrderForm(user=user, shop=shop, initial=initial)

    customer_cars = list(
        CustomerCar.objects.filter(customer__shop=shop)
        .select_related("customer")
        .order_by("customer__full_name", "make", "model")
        .values("id", "customer_id", "make", "model", "year", "plate_number")
    )

    return render(request, "work_order_list_create.html", {
        "form": form,
        "work_orders": work_orders,
        "title": _("Create Repair Order"),
        "description": _("This is where you create and dispatch repair orders."),
        "shop": shop,
        "shop_name": shop.shop_name if shop else "",
        "customer_cars_json": customer_cars,
    })


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_REPAIR_ORDERS)
def repair_work_order_detail(request, work_order_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Repair orders are available for shop users only.")

    work_order = get_object_or_404(
        RepairWorkOrder.objects.select_related("customer", "car", "assigned_to", "created_by", "invoice"),
        pk=work_order_id,
        shop=shop,
    )

    header_form = RepairWorkOrderForm(user=request.user, shop=shop, instance=work_order)
    line_form = RepairWorkOrderLineForm(shop)
    active_edit_line_id = None
    is_work_order_locked = bool(work_order.invoice_id)
    transition_map = {
        RepairWorkOrder.STATUS_NEW: [RepairWorkOrder.STATUS_ASSIGNED, RepairWorkOrder.STATUS_CANCELLED],
        RepairWorkOrder.STATUS_ASSIGNED: [RepairWorkOrder.STATUS_IN_PROGRESS, RepairWorkOrder.STATUS_CANCELLED],
        RepairWorkOrder.STATUS_IN_PROGRESS: [RepairWorkOrder.STATUS_READY, RepairWorkOrder.STATUS_CANCELLED],
        RepairWorkOrder.STATUS_READY: [RepairWorkOrder.STATUS_COMPLETED, RepairWorkOrder.STATUS_IN_PROGRESS, RepairWorkOrder.STATUS_CANCELLED],
        RepairWorkOrder.STATUS_COMPLETED: [],
        RepairWorkOrder.STATUS_CANCELLED: [RepairWorkOrder.STATUS_NEW],
    }

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "change_status":
            target_status = request.POST.get("target_status", "").strip()
            allowed_targets = transition_map.get(work_order.status, [])
            if target_status not in allowed_targets:
                messages.error(request, "Invalid status transition.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)

            if target_status == RepairWorkOrder.STATUS_READY and not work_order.service_lines.exists():
                messages.error(request, "Add at least one line item before marking the work order ready.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)

            work_order.status = target_status
            work_order.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Work order status changed to '{work_order.get_status_display()}'.")
            return redirect("repair_work_order_detail", work_order_id=work_order.pk)

        if action == "update_work_order":
            if is_work_order_locked:
                messages.error(request, "This work order is linked to an invoice and its details are locked.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)
            header_form = RepairWorkOrderForm(request.POST, user=request.user, shop=shop, instance=work_order)
            if header_form.is_valid():
                updated_work_order = header_form.save(commit=False)
                updated_work_order.shop = shop
                updated_work_order.save()
                messages.success(request, f"Work order #{work_order.pk} updated.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)

        if action == "add_line":
            if is_work_order_locked:
                messages.error(request, "This work order is linked to an invoice and its line items are locked.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)
            line_form = RepairWorkOrderLineForm(shop, request.POST)
            if line_form.is_valid():
                line = line_form.save(commit=False)
                line.work_order = work_order
                if line.price_item:
                    if not line.description:
                        line.description = line.price_item.description
                    if line.unit_price in (None, ""):
                        line.unit_price = line.price_item.unit_price
                    if line.vat_percent in (None, ""):
                        line.vat_percent = line.price_item.vat_percent
                line.save()
                messages.success(request, "Line item added.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)

        if action == "delete_line":
            if is_work_order_locked:
                messages.error(request, "This work order is linked to an invoice and its line items are locked.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)
            line_id = request.POST.get("line_id", "").strip()
            line = get_object_or_404(RepairWorkOrderLine, pk=line_id, work_order=work_order)
            line.delete()
            messages.success(request, "Line item removed.")
            return redirect("repair_work_order_detail", work_order_id=work_order.pk)

        if action == "update_line":
            if is_work_order_locked:
                messages.error(request, "This work order is linked to an invoice and its line items are locked.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)
            line_id = request.POST.get("line_id", "").strip()
            line = get_object_or_404(RepairWorkOrderLine, pk=line_id, work_order=work_order)
            active_edit_line_id = line.pk
            edit_form = RepairWorkOrderLineForm(shop, request.POST, instance=line, prefix=f"line-{line.pk}")
            if edit_form.is_valid():
                updated_line = edit_form.save(commit=False)
                updated_line.work_order = work_order
                if updated_line.price_item:
                    if not updated_line.description:
                        updated_line.description = updated_line.price_item.description
                    if updated_line.unit_price in (None, ""):
                        updated_line.unit_price = updated_line.price_item.unit_price
                    if updated_line.vat_percent in (None, ""):
                        updated_line.vat_percent = updated_line.price_item.vat_percent
                updated_line.save()
                messages.success(request, "Line item updated.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)

        if action == "create_invoice":
            if work_order.invoice_id:
                messages.success(request, f"Invoice '{work_order.invoice.invoice_number}' already exists for this work order.")
                return redirect("invoice_detail", invoice_id=work_order.invoice_id)

            if not work_order.customer_id:
                messages.error(request, "Select a customer before creating an invoice.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)

            work_order_lines = list(work_order.service_lines.select_related("price_item").all())
            if not work_order_lines:
                messages.error(request, "Add at least one line item before creating an invoice.")
                return redirect("repair_work_order_detail", work_order_id=work_order.pk)

            invoice = Invoice.objects.create(
                shop=shop,
                customer=work_order.customer,
                car=work_order.car,
                issue_date=timezone.localdate(),
                notes=(f"Work order #{work_order.pk}\n\n{work_order.technician_notes}".strip()),
            )

            for work_order_line in work_order_lines:
                InvoiceLine.objects.create(
                    invoice=invoice,
                    price_item=work_order_line.price_item,
                    description=work_order_line.description,
                    quantity=work_order_line.quantity,
                    unit_price=work_order_line.unit_price,
                    vat_percent=work_order_line.vat_percent,
                )

            work_order.invoice = invoice
            work_order.save(update_fields=["invoice", "updated_at"])
            messages.success(request, f"Invoice '{invoice.invoice_number}' created from work order #{work_order.pk}.")
            return redirect("invoice_detail", invoice_id=invoice.pk)

    lines = work_order.service_lines.select_related("price_item").all()
    line_edit_forms = {}
    for line in lines:
        prefix = f"line-{line.pk}"
        if active_edit_line_id == line.pk and request.method == "POST" and request.POST.get("action", "").strip() == "update_line":
            form = RepairWorkOrderLineForm(shop, request.POST, instance=line, prefix=prefix)
        else:
            form = RepairWorkOrderLineForm(shop, instance=line, prefix=prefix)
        line_edit_forms[line.pk] = form
        line.edit_form = form
        line.show_edit_form = active_edit_line_id == line.pk and form.errors

    service_lines = [line for line in lines if line.line_type == RepairWorkOrderLine.TYPE_SERVICE]
    part_lines = [line for line in lines if line.line_type == RepairWorkOrderLine.TYPE_PART]
    customer_cars = list(
        CustomerCar.objects.filter(customer__shop=shop)
        .select_related("customer")
        .order_by("customer__full_name", "make", "model")
        .values("id", "customer_id", "make", "model", "year", "plate_number")
    )

    return render(
        request,
        "work_order_detail.html",
        {
            "shop": shop,
            "work_order": work_order,
            "header_form": header_form,
            "line_form": line_form,
            "lines": lines,
            "service_lines": service_lines,
            "part_lines": part_lines,
            "available_status_targets": [
                {"value": status, "label": dict(RepairWorkOrder.STATUS_CHOICES).get(status, status)}
                for status in transition_map.get(work_order.status, [])
            ],
            "is_work_order_locked": is_work_order_locked,
            "customer_cars_json": customer_cars,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_INSPECTIONS)
def schedule_inspection(request):
    return render(
        request,
        "shop_operation.html",
        {
            "title": _("Schedule Vehicle Inspection"),
            "description": _("This is where your team can schedule and track inspections."),
            "shop_name": request.current_shop.shop_name,
        },
    )


@require_shop_right("can_manage_inventory", required_feature=ShopProfile.FEATURE_INVENTORY)
def manage_inventory(request):
    return render(
        request,
        "shop_operation.html",
        {
            "title": _("Manage Parts Inventory"),
            "description": _("This is where stock movements and part catalogs are managed."),
            "shop_name": request.current_shop.shop_name,
        },
    )


@require_shop_right("can_view_reports", required_feature=ShopProfile.FEATURE_REPORTS)
def view_reports(request):
    return render(
        request,
        "shop_operation.html",
        {
            "title": _("View Reports"),
            "description": _("This is where KPI, revenue, and technician productivity reports are shown."),
            "shop_name": request.current_shop.shop_name,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_INVOICES)
def invoice_list(request):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Invoice management is available for shop users only.")

    invoices = (
        Invoice.objects.filter(shop=shop)
        .select_related("customer", "car")
        .prefetch_related("lines")
        .order_by("-issue_date", "-id")
    )
    return render(
        request,
        "invoice_list.html",
        {
            "shop": shop,
            "invoices": invoices,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_INVOICES)
def invoice_create(request):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Invoice management is available for shop users only.")

    initial = {}
    customer_id = request.GET.get("customer")
    car_id = request.GET.get("car")
    if customer_id:
        initial["customer"] = customer_id
    if car_id:
        initial["car"] = car_id

    if request.method == "POST":
        form = InvoiceForm(shop, request.POST)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.shop = shop
            invoice.save()
            messages.success(request, f"Invoice '{invoice.invoice_number}' created.")
            return redirect("invoice_detail", invoice_id=invoice.pk)
    else:
        form = InvoiceForm(shop, initial=initial)

    customer_cars = list(
        CustomerCar.objects.filter(customer__shop=shop)
        .select_related("customer")
        .order_by("customer__full_name", "make", "model")
        .values("id", "customer_id", "make", "model", "year", "plate_number")
    )
    customer_payment_terms = _customer_payment_terms_payload(shop)

    return render(
        request,
        "invoice_form.html",
        {
            "shop": shop,
            "form": form,
            "title": _("Create Invoice"),
            "submit_label": _("Create Invoice"),
            "customer_cars_json": customer_cars,
            "customer_payment_terms_json": customer_payment_terms,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_INVOICES)
def invoice_detail(request, invoice_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Invoice management is available for shop users only.")

    master_data, _ = ShopMasterData.objects.get_or_create(shop=shop)

    invoice = get_object_or_404(
        Invoice.objects.select_related("customer", "car").prefetch_related("lines__price_item"),
        pk=invoice_id,
        shop=shop,
    )

    header_form = InvoiceForm(shop, instance=invoice)
    line_form = InvoiceLineForm(shop)
    active_edit_line_id = ""

    if request.method != "POST":
        requested_edit_line_id = (request.GET.get("edit_line") or "").strip()
        if requested_edit_line_id and invoice.status == Invoice.STATUS_DRAFT:
            edit_line = get_object_or_404(InvoiceLine, pk=requested_edit_line_id, invoice=invoice)
            active_edit_line_id = str(edit_line.pk)
            line_form = InvoiceLineForm(shop, instance=edit_line)

    transition_map = {
        Invoice.STATUS_DRAFT: [Invoice.STATUS_ISSUED, Invoice.STATUS_CANCELLED],
        Invoice.STATUS_ISSUED: [Invoice.STATUS_PAID, Invoice.STATUS_DRAFT, Invoice.STATUS_CANCELLED],
        Invoice.STATUS_PAID: [],
        Invoice.STATUS_CANCELLED: [Invoice.STATUS_DRAFT],
    }
    status_labels = dict(Invoice.STATUS_CHOICES)

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "change_status":
            target_status = request.POST.get("target_status", "").strip()
            allowed_targets = transition_map.get(invoice.status, [])

            if target_status not in allowed_targets:
                messages.error(request, "Invalid status transition.")
                return redirect("invoice_detail", invoice_id=invoice.pk)

            if target_status in {Invoice.STATUS_ISSUED, Invoice.STATUS_PAID} and not invoice.lines.exists():
                messages.error(request, "Add at least one line before issuing or marking invoice as paid.")
                return redirect("invoice_detail", invoice_id=invoice.pk)

            invoice.status = target_status
            invoice.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Invoice status changed to '{invoice.get_status_display()}'.")
            return redirect("invoice_detail", invoice_id=invoice.pk)

        if action in {"update_invoice", "add_line", "update_line", "delete_line"} and invoice.status != Invoice.STATUS_DRAFT:
            messages.error(request, "Only draft invoices can be edited. Set status back to Draft to modify lines.")
            return redirect("invoice_detail", invoice_id=invoice.pk)

        if action == "update_invoice":
            header_form = InvoiceForm(shop, request.POST, instance=invoice)
            if header_form.is_valid():
                header_form.save()
                messages.success(request, "Invoice updated.")
                return redirect("invoice_detail", invoice_id=invoice.pk)

        if action == "add_line":
            line_form = InvoiceLineForm(shop, request.POST)
            if line_form.is_valid():
                line = line_form.save(commit=False)
                line.invoice = invoice
                if line.price_item:
                    if not line.description:
                        line.description = line.price_item.description
                    if line.unit_price is None:
                        line.unit_price = line.price_item.unit_price
                    if line.vat_percent is None:
                        line.vat_percent = line.price_item.vat_percent
                if line.vat_percent is None:
                    line.vat_percent = 25
                line.save()
                messages.success(request, "Invoice line added.")
                return redirect("invoice_detail", invoice_id=invoice.pk)

        if action == "update_line":
            line_id = request.POST.get("line_id", "").strip()
            line = get_object_or_404(InvoiceLine, pk=line_id, invoice=invoice)
            line_form = InvoiceLineForm(shop, request.POST, instance=line)
            active_edit_line_id = str(line.pk)
            if line_form.is_valid():
                updated_line = line_form.save(commit=False)
                updated_line.invoice = invoice
                if updated_line.price_item:
                    if not updated_line.description:
                        updated_line.description = updated_line.price_item.description
                    if updated_line.unit_price is None:
                        updated_line.unit_price = updated_line.price_item.unit_price
                    if updated_line.vat_percent is None:
                        updated_line.vat_percent = updated_line.price_item.vat_percent
                if updated_line.vat_percent is None:
                    updated_line.vat_percent = 25
                updated_line.save()
                messages.success(request, "Invoice line updated.")
                return redirect("invoice_detail", invoice_id=invoice.pk)

        if action == "delete_line":
            line_id = request.POST.get("line_id", "").strip()
            line = get_object_or_404(InvoiceLine, pk=line_id, invoice=invoice)
            line.delete()
            messages.success(request, "Invoice line removed.")
            return redirect("invoice_detail", invoice_id=invoice.pk)

    lines = invoice.lines.select_related("price_item").all()
    customer_cars = list(
        CustomerCar.objects.filter(customer__shop=shop)
        .select_related("customer")
        .order_by("customer__full_name", "make", "model")
        .values("id", "customer_id", "make", "model", "year", "plate_number")
    )
    customer_payment_terms = _customer_payment_terms_payload(shop)
    invoice_price_items = list(
        InvoicePriceItem.objects.filter(shop=shop, is_active=True)
        .order_by("item_type", "description")
        .values("id", "description", "unit_price", "vat_percent")
    )
    return render(
        request,
        "invoice_detail.html",
        {
            "shop": shop,
            "master_data": master_data,
            "invoice": invoice,
            "lines": lines,
            "header_form": header_form,
            "line_form": line_form,
            "active_edit_line_id": active_edit_line_id,
            "is_locked": invoice.status != Invoice.STATUS_DRAFT,
            "available_status_targets": [
                {
                    "value": status,
                    "label": str(status_labels.get(status, status)),
                }
                for status in transition_map.get(invoice.status, [])
            ],
            "customer_cars_json": customer_cars,
            "customer_payment_terms_json": customer_payment_terms,
            "invoice_price_items_json": invoice_price_items,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_INVOICES)
def invoice_print(request, invoice_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Invoice management is available for shop users only.")

    invoice = get_object_or_404(
        Invoice.objects.select_related("customer", "car").prefetch_related("lines"),
        pk=invoice_id,
        shop=shop,
    )


def invoice_public(request, token):
    try:
        payload = _load_public_invoice_token(token)
    except signing.SignatureExpired:
        return HttpResponseForbidden("This invoice link has expired.")
    except signing.BadSignature:
        return HttpResponseForbidden("Invalid invoice link.")

    invoice_id = payload.get("invoice_id")
    if not invoice_id:
        return HttpResponseForbidden("Invalid invoice link payload.")

    invoice = get_object_or_404(
        Invoice.objects.select_related("shop", "customer", "car").prefetch_related("lines"),
        pk=invoice_id,
    )
    master_data, _ = ShopMasterData.objects.get_or_create(shop=invoice.shop)

    return render(
        request,
        "invoice_public.html",
        {
            "shop": invoice.shop,
            "master_data": master_data,
            "invoice": invoice,
            "lines": invoice.lines.all(),
            "printed_at": timezone.localtime(),
        },
    )
    master_data, _ = ShopMasterData.objects.get_or_create(shop=shop)

    return render(
        request,
        "invoice_print.html",
        {
            "shop": shop,
            "master_data": master_data,
            "invoice": invoice,
            "lines": invoice.lines.all(),
            "printed_at": timezone.localtime(),
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_INVOICES)
def invoice_email(request, invoice_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Invoice management is available for shop users only.")

    invoice = get_object_or_404(
        Invoice.objects.select_related("customer", "car").prefetch_related("lines"),
        pk=invoice_id,
        shop=shop,
    )
    master_data, _ = ShopMasterData.objects.get_or_create(shop=shop)
    email_backend = django_settings.EMAIL_BACKEND
    is_file_backend = email_backend == "django.core.mail.backends.filebased.EmailBackend"
    is_console_backend = email_backend == "django.core.mail.backends.console.EmailBackend"

    default_subject = f"Invoice {invoice.invoice_number} from {shop.shop_name}"
    default_message = (
        "Dear customer,\n\n"
        f"Please find invoice {invoice.invoice_number} attached as PDF. "
        "You can also view/print it from the secure link in this email.\n\n"
        "Best regards"
    )

    if request.method == "POST":
        form = InvoiceEmailForm(request.POST)
        if form.is_valid():
            recipient = form.cleaned_data["recipient_email"]
            subject = form.cleaned_data["subject"]
            custom_message = form.cleaned_data.get("message", "")
            attach_pdf = form.cleaned_data.get("attach_pdf", True)
            lines = invoice.lines.all()

            context = {
                "shop": shop,
                "master_data": master_data,
                "invoice": invoice,
                "lines": lines,
                "custom_message": custom_message,
                "invoice_public_url": request.build_absolute_uri(
                    reverse("invoice_public", kwargs={"token": _build_public_invoice_token(invoice.pk)})
                ),
            }

            text_body = render_to_string("emails/invoice_email.txt", context)
            html_body = render_to_string("emails/invoice_email.html", context)

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
            )
            email.attach_alternative(html_body, "text/html")

            if attach_pdf:
                try:
                    pdf_bytes = _generate_invoice_pdf_bytes(
                        shop=shop,
                        master_data=master_data,
                        invoice=invoice,
                        lines=lines,
                        printed_at=timezone.localtime(),
                    )
                except Exception as exc:
                    messages.error(request, f"Invoice PDF could not be generated: {exc}")
                    return render(
                        request,
                        "invoice_email_form.html",
                        {
                            "shop": shop,
                            "invoice": invoice,
                            "form": form,
                            "email_backend": email_backend,
                            "email_file_path": str(django_settings.EMAIL_FILE_PATH),
                            "is_file_backend": is_file_backend,
                            "is_console_backend": is_console_backend,
                        },
                    )

                email.attach(
                    f"invoice-{invoice.invoice_number}.pdf",
                    pdf_bytes,
                    "application/pdf",
                )
            try:
                email.send(fail_silently=False)
            except Exception as exc:
                messages.error(request, f"Invoice email could not be sent: {exc}")
                return render(
                    request,
                    "invoice_email_form.html",
                    {
                        "shop": shop,
                        "invoice": invoice,
                        "form": form,
                        "email_backend": email_backend,
                        "email_file_path": str(django_settings.EMAIL_FILE_PATH),
                        "is_file_backend": is_file_backend,
                        "is_console_backend": is_console_backend,
                    },
                )

            if is_file_backend:
                messages.success(
                    request,
                    f"Invoice email rendered to local files for development. Check {django_settings.EMAIL_FILE_PATH}.",
                )
            elif is_console_backend:
                messages.success(request, f"Invoice email rendered to the development server console for {recipient}.")
            else:
                messages.success(request, f"Invoice email sent to {recipient}.")
            return redirect("invoice_detail", invoice_id=invoice.pk)
    else:
        form = InvoiceEmailForm(
            initial={
                "recipient_email": invoice.customer.email,
                "subject": default_subject,
                "message": default_message,
            }
        )

    return render(
        request,
        "invoice_email_form.html",
        {
            "shop": shop,
            "invoice": invoice,
            "form": form,
            "email_backend": email_backend,
            "email_file_path": str(django_settings.EMAIL_FILE_PATH),
            "is_file_backend": is_file_backend,
            "is_console_backend": is_console_backend,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_INVOICES)
def invoice_price_table(request):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Invoice management is available for shop users only.")

    edit_item = None
    edit_item_id = request.GET.get("edit")
    if edit_item_id:
        edit_item = get_object_or_404(InvoicePriceItem, pk=edit_item_id, shop=shop)

    if request.method == "POST":
        action = request.POST.get("action", "save")

        if action == "delete":
            item = get_object_or_404(InvoicePriceItem, pk=request.POST.get("item_id"), shop=shop)
            item_description = item.description
            item.delete()
            messages.success(request, _("Price item '%(description)s' deleted.") % {"description": item_description})
            return redirect("invoice_price_table")

        item_id = request.POST.get("item_id")
        form_instance = get_object_or_404(InvoicePriceItem, pk=item_id, shop=shop) if item_id else None
        form = InvoicePriceItemForm(request.POST, instance=form_instance)
        if form.is_valid():
            item = form.save(commit=False)
            item.shop = shop
            item.save()
            message_text = (
                _("Price item '%(description)s' updated.")
                if form_instance
                else _("Price item '%(description)s' saved.")
            )
            messages.success(request, message_text % {"description": item.description})
            return redirect("invoice_price_table")
        edit_item = form_instance
    else:
        form = InvoicePriceItemForm(instance=edit_item)

    items = InvoicePriceItem.objects.filter(shop=shop).order_by("item_type", "description")
    return render(
        request,
        "invoice_price_table.html",
        {
            "shop": shop,
            "form": form,
            "items": items,
            "active_edit_item_id": edit_item.id if edit_item else None,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_INVOICES)
def invoice_masterdata(request):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Invoice management is available for shop users only.")

    master_data, _ = ShopMasterData.objects.get_or_create(shop=shop)

    if request.method == "POST":
        form = ShopMasterDataForm(request.POST, request.FILES, instance=master_data)
        if form.is_valid():
            form.save()
            messages.success(request, "Invoice masterdata updated.")
            return redirect("invoice_masterdata")
    else:
        form = ShopMasterDataForm(instance=master_data)

    return render(
        request,
        "invoice_masterdata.html",
        {
            "shop": shop,
            "form": form,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_CUSTOMERS)
def customer_list(request):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Customer management is available for shop users only.")

    search = request.GET.get("q", "").strip()
    customers = Customer.objects.filter(shop=shop).order_by("full_name", "id")
    if search:
        customers = customers.filter(full_name__icontains=search)

    return render(
        request,
        "customer_list.html",
        {
            "shop": shop,
            "customers": customers,
            "search": search,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_CUSTOMERS)
def customer_create(request):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Customer management is available for shop users only.")

    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.shop = shop
            customer.save()
            messages.success(request, f"Customer '{customer.full_name}' created.")
            return redirect(reverse("customer_detail", kwargs={"customer_id": customer.pk}))
    else:
        form = CustomerForm()

    return render(
        request,
        "customer_form.html",
        {
            "shop": shop,
            "form": form,
            "title": "Add Customer",
            "submit_label": "Create Customer",
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_CUSTOMERS)
def customer_detail(request, customer_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Customer management is available for shop users only.")

    customer = get_object_or_404(Customer.objects.prefetch_related("cars"), pk=customer_id, shop=shop)

    return render(
        request,
        "customer_detail.html",
        {
            "shop": shop,
            "customer": customer,
            "cars": customer.cars.all(),
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_CUSTOMERS)
def customer_car_create(request, customer_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Customer management is available for shop users only.")

    customer = get_object_or_404(Customer, pk=customer_id, shop=shop)

    if request.method == "POST":
        form = CustomerCarForm(request.POST)
        if form.is_valid():
            car = form.save(commit=False)
            car.customer = customer
            car.save()
            messages.success(request, f"Car '{car}' added for {customer.full_name}.")
            return redirect("customer_detail", customer_id=customer.pk)
    else:
        form = CustomerCarForm()

    return render(
        request,
        "customer_car_form.html",
        {
            "shop": shop,
            "customer": customer,
            "form": form,
            "is_create": True,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_CUSTOMERS)
def customer_edit(request, customer_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Customer management is available for shop users only.")

    customer = get_object_or_404(Customer, pk=customer_id, shop=shop)

    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, f"Customer '{customer.full_name}' updated.")
            return redirect("customer_detail", customer_id=customer.pk)
    else:
        form = CustomerForm(instance=customer)

    return render(
        request,
        "customer_form.html",
        {
            "shop": shop,
            "customer": customer,
            "form": form,
            "title": "Edit Customer",
            "submit_label": "Save Changes",
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_CUSTOMERS)
def customer_delete(request, customer_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Customer management is available for shop users only.")

    if request.method != "POST":
        return redirect("customer_detail", customer_id=customer_id)

    customer = get_object_or_404(Customer, pk=customer_id, shop=shop)
    customer_name = customer.full_name
    customer.delete()
    messages.success(request, f"Customer '{customer_name}' deleted.")
    return redirect("customer_list")


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_CUSTOMERS)
def customer_car_edit(request, customer_id, car_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Customer management is available for shop users only.")

    customer = get_object_or_404(Customer, pk=customer_id, shop=shop)
    car = get_object_or_404(CustomerCar, pk=car_id, customer=customer)

    if request.method == "POST":
        form = CustomerCarForm(request.POST, instance=car)
        if form.is_valid():
            form.save()
            messages.success(request, f"Car '{car}' updated.")
            return redirect("customer_detail", customer_id=customer.pk)
    else:
        form = CustomerCarForm(instance=car)

    return render(
        request,
        "customer_car_form.html",
        {
            "shop": shop,
            "customer": customer,
            "car": car,
            "form": form,
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_CUSTOMERS)
def customer_car_delete(request, customer_id, car_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Customer management is available for shop users only.")

    if request.method != "POST":
        return redirect("customer_detail", customer_id=customer_id)

    customer = get_object_or_404(Customer, pk=customer_id, shop=shop)
    car = get_object_or_404(CustomerCar, pk=car_id, customer=customer)
    car_name = str(car)
    car.delete()
    messages.success(request, f"Car '{car_name}' removed from customer '{customer.full_name}'.")
    return redirect("customer_detail", customer_id=customer.pk)


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_CUSTOMERS)
def customer_car_print_labels(request, customer_id, car_id):
    shop = getattr(request, "current_shop", None)
    if not shop:
        return HttpResponseForbidden("Customer management is available for shop users only.")

    customer = get_object_or_404(Customer, pk=customer_id, shop=shop)
    car = get_object_or_404(CustomerCar, pk=car_id, customer=customer)

    requested_count = request.GET.get("count", "").strip()
    requested_format = request.GET.get("format", "a4_2x7").strip().lower()

    format_presets = {
        "a4_2x7": {
            "name": "A4 Sheet 2x7",
            "columns": 2,
            "label_width_mm": 99,
            "label_height_mm": 38,
            "page_size": "A4",
            "default_count": 14,
        },
        "zebra_100x50": {
            "name": "Zebra 100x50 mm",
            "columns": 1,
            "label_width_mm": 100,
            "label_height_mm": 50,
            "page_size": "100mm 50mm",
            "default_count": 1,
        },
    }
    if requested_format not in format_presets:
        requested_format = "a4_2x7"

    preset = format_presets[requested_format]
    default_count = car.tire_label_count or preset["default_count"]
    try:
        label_count = int(requested_count) if requested_count else int(default_count)
    except ValueError:
        label_count = int(default_count)

    # Keep label sheets bounded to practical print sizes.
    label_count = max(1, min(label_count, 40))

    labels = []
    for idx in range(1, label_count + 1):
        qr_payload = {
            "shop": shop.shop_name,
            "customer": customer.full_name,
            "car": str(car),
            "plate": car.plate_number,
            "vin": car.vin,
            "location": car.tire_hotel_location,
            "label": f"{idx}/{label_count}",
        }
        qr_text = json.dumps(qr_payload, ensure_ascii=False, separators=(",", ":"))
        labels.append(
            {
                "index": idx,
                "qr_text": qr_text,
                "qr_image": _qr_png_data_uri(qr_text),
            }
        )

    return render(
        request,
        "tire_labels_print.html",
        {
            "shop": shop,
            "customer": customer,
            "car": car,
            "labels": labels,
            "label_count": label_count,
            "format_key": requested_format,
            "format_preset": preset,
            "format_presets": format_presets,
            "printed_at": timezone.localtime(),
        },
    )


@require_shop_right("can_create_repair_order", required_feature=ShopProfile.FEATURE_CUSTOMERS)
def api_vehicle_lookup(request, plate):
    """
    Proxy endpoint for MotorAPI plate lookup.

    This keeps the API token on the server and returns JSON to the frontend.
    """
    shop = getattr(request, "current_shop", None)
    if not shop:
        return JsonResponse(
            {
                "error": "Shop context missing",
                "message": "Vehicle lookup is available for active shop users only.",
            },
            status=403,
        )

    api_key = os.getenv("MOTORAPI_AUTH_TOKEN", "").strip()
    if not api_key:
        return JsonResponse(
            {
                "error": "Missing API key",
                "message": "Set MOTORAPI_AUTH_TOKEN in environment variables.",
            },
            status=500,
        )

    normalized_plate = _normalize_plate(plate)
    if not PLATE_REGEX.match(normalized_plate):
        return JsonResponse(
            {
                "error": "Invalid plate",
                "message": "Expected format like AB12345.",
            },
            status=400,
        )

    motorapi_base_url = os.getenv("MOTORAPI_BASE_URL", "https://v1.motorapi.dk").strip().rstrip("/")
    url = f"{motorapi_base_url}/vehicles/{normalized_plate}"
    req = urllib_request.Request(
        url,
        headers={
            "X-AUTH-TOKEN": api_key,
            "Accept": "application/json",
        },
        method="GET",
    )

    verify_ssl = _env_bool("MOTORAPI_VERIFY_SSL", default=True)
    ssl_context = None
    if not verify_ssl:
        # Local-only fallback for environments with broken/intercepted TLS cert chains.
        ssl_context = ssl._create_unverified_context()

    try:
        with urllib_request.urlopen(req, timeout=12, context=ssl_context) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw_body) if raw_body else {}

        # Include mapped fields for simple frontend auto-fill while preserving full upstream payload.
        mapped = {
            "plate_number": normalized_plate,
            "make": _extract_first(payload, ("make", "brand", "manufacturer"), ""),
            "model": _extract_first(payload, ("model", "model_name", "variant"), ""),
            "year": _extract_first(payload, ("year", "registration_year", "model_year"), ""),
            "color": _extract_first(payload, ("color", "vehicle_color"), ""),
            "vin": _extract_first(payload, ("vin", "chassis_number"), ""),
            "notes": _build_vehicle_notes(payload),
            "inspection": payload.get("mot_info", {}),
        }
        return JsonResponse({"vehicle": payload, "mapped": mapped}, status=200)

    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            upstream_payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            upstream_payload = {"raw": body}

        if exc.code == 500 and not upstream_payload:
            return JsonResponse(
                {
                    "error": "MotorAPI internal error",
                    "status": 500,
                    "message": (
                        "MotorAPI returned HTTP 500 with an empty response body. "
                        "This is usually an upstream outage or API-key/account issue on the provider side."
                    ),
                },
                status=502,
            )

        if exc.code == 404:
            return JsonResponse(
                {
                    "error": "Invalid plate",
                    "message": "No vehicle found for this plate.",
                    "motorapi": upstream_payload,
                },
                status=404,
            )
        if exc.code in (401, 403):
            return JsonResponse(
                {
                    "error": "MotorAPI authentication error",
                    "message": "Check MOTORAPI_AUTH_TOKEN.",
                    "motorapi": upstream_payload,
                },
                status=502,
            )

        return JsonResponse(
            {
                "error": "MotorAPI error",
                "status": exc.code,
                "message": "MotorAPI returned an error response.",
                "motorapi": upstream_payload,
            },
            status=502,
        )
    except ssl.SSLCertVerificationError as exc:
        return JsonResponse(
            {
                "error": "SSL verification failed",
                "message": (
                    "TLS certificate verification failed for MotorAPI. "
                    "If this is local development with an intercepted certificate, "
                    "set MOTORAPI_VERIFY_SSL=False in .env."
                ),
                "detail": str(exc),
            },
            status=502,
        )
    except (urllib_error.URLError, TimeoutError) as exc:
        return JsonResponse(
            {
                "error": "MotorAPI unreachable",
                "message": str(exc),
            },
            status=502,
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "error": "Invalid upstream response",
                "message": "MotorAPI returned non-JSON content.",
            },
            status=502,
        )


@staff_member_required
def add_shop(request):
    created_credentials = request.session.pop("created_credentials", None)

    if request.method == "POST":
        form = ShopOnboardingForm(request.POST)
        if form.is_valid():
            user, shop_profile, plain_password = form.save()
            ensure_tenant_database_alias(shop_profile.database_name)
            request.session["created_credentials"] = {
                "shop_name": shop_profile.shop_name,
                "username": user.username,
                "password": plain_password,
                "database_name": shop_profile.database_name,
            }
            messages.success(
                request,
                (
                    f"Shop '{shop_profile.shop_name}' created. "
                    f"Login user: {user.username}"
                ),
            )
            return redirect("add_shop")
    else:
        form = ShopOnboardingForm()

    return render(
        request,
        "add_shop.html",
        {
            "form": form,
            "created_credentials": created_credentials,
        },
    )


@staff_member_required
def shop_list(request):
    shops = list(ShopProfile.objects.select_related("owner").order_by("shop_name"))
    logo_map = {
        md.shop_id: md.company_logo.url
        for md in ShopMasterData.objects.filter(shop_id__in=[shop.pk for shop in shops]).exclude(company_logo="")
    }
    for shop in shops:
        shop.logo_url = logo_map.get(shop.pk, "")

    return render(request, "shop_list.html", {"shops": shops})


@staff_member_required
def edit_shop(request, shop_id):
    shop = get_object_or_404(ShopProfile.objects.select_related("owner"), pk=shop_id)

    if request.method == "POST":
        form = ShopEditForm(request.POST, instance=shop)
        if form.is_valid():
            updated_shop, generated_password = form.save()
            ensure_tenant_database_alias(updated_shop.database_name)
            if generated_password:
                request.session["reset_credentials"] = {
                    "shop_name": updated_shop.shop_name,
                    "username": updated_shop.owner.username,
                    "password": generated_password,
                }
            messages.success(request, f"Updated '{updated_shop.shop_name}'.")
            return redirect("edit_shop", shop_id=updated_shop.pk)
    else:
        form = ShopEditForm(instance=shop)

    reset_credentials = request.session.pop("reset_credentials", None)
    return render(
        request,
        "edit_shop.html",
        {
            "form": form,
            "shop": shop,
            "reset_credentials": reset_credentials,
        },
    )


@staff_member_required
def toggle_shop_active(request, shop_id):
    if request.method != "POST":
        return redirect("shop_list")

    shop = get_object_or_404(ShopProfile.objects.select_related("owner"), pk=shop_id)
    shop.is_active = not shop.is_active
    shop.owner.is_active = shop.is_active
    shop.owner.save(update_fields=["is_active"])
    shop.save(update_fields=["is_active", "updated_at"])

    state = "activated" if shop.is_active else "deactivated"
    messages.success(request, f"Shop '{shop.shop_name}' {state}.")
    return redirect("shop_list")


@login_required
def manage_shop_users(request, shop_id):
    if request.user.is_staff:
        shop = get_object_or_404(ShopProfile.objects.select_related("owner"), pk=shop_id)
    else:
        user_context = get_shop_context_for_user(request.user)
        if not user_context or not user_context.get("features", {}).get(ShopProfile.FEATURE_USER_MANAGEMENT, False):
            return HttpResponseForbidden("User management is not included in your shop subscription.")
        if not user_context or not user_context["rights"].get("can_manage_users", False):
            return HttpResponseForbidden("You do not have permission to manage shop users.")
        if user_context["shop"].pk != shop_id:
            return HttpResponseForbidden("You can only manage users for your own shop.")
        shop = get_object_or_404(ShopProfile.objects.select_related("owner"), pk=shop_id)

    created_user_credentials = request.session.pop("created_user_credentials", None)

    if request.method == "POST":
        form = ShopUserAccessCreateForm(shop, request.POST)
        if form.is_valid():
            access, created, plain_password = form.save()
            if plain_password:
                request.session["created_user_credentials"] = {
                    "shop_name": shop.shop_name,
                    "username": access.user.username,
                    "password": plain_password,
                }
            message = "added" if created else "updated"
            messages.success(
                request,
                f"User '{access.user.username}' {message} for shop '{shop.shop_name}'.",
            )
            return redirect("manage_shop_users", shop_id=shop.pk)
    else:
        form = ShopUserAccessCreateForm(shop)

    accesses = shop.user_accesses.select_related("user").order_by("user__username")
    return render(
        request,
        "manage_shop_users.html",
        {
            "shop": shop,
            "form": form,
            "accesses": accesses,
            "created_user_credentials": created_user_credentials,
        },
    )


@login_required
def edit_shop_user_rights(request, shop_id, access_id):
    if request.user.is_staff:
        shop = get_object_or_404(ShopProfile, pk=shop_id)
    else:
        user_context = get_shop_context_for_user(request.user)
        if not user_context or not user_context.get("features", {}).get(ShopProfile.FEATURE_USER_MANAGEMENT, False):
            return HttpResponseForbidden("User management is not included in your shop subscription.")
        if not user_context or not user_context["rights"].get("can_manage_users", False):
            return HttpResponseForbidden("You do not have permission to edit shop user rights.")
        if user_context["shop"].pk != shop_id:
            return HttpResponseForbidden("You can only edit rights for your own shop.")
        shop = get_object_or_404(ShopProfile, pk=shop_id)

    access = get_object_or_404(ShopUserAccess.objects.select_related("user", "shop"), pk=access_id, shop=shop)

    if request.method == "POST":
        form = ShopUserAccessEditForm(request.POST, instance=access)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated rights for '{access.user.username}'.")
            return redirect("manage_shop_users", shop_id=shop.pk)
    else:
        form = ShopUserAccessEditForm(instance=access)

    return render(
        request,
        "edit_shop_user_rights.html",
        {
            "shop": shop,
            "access": access,
            "form": form,
        },
    )
