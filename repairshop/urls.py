from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from .views import (
    add_shop,
    customer_car_delete,
    customer_car_edit,
    customer_car_print_labels,
    customer_car_create,
    customer_create,
    customer_delete,
    customer_detail,
    customer_edit,
    customer_list,
    api_vehicle_lookup,
    create_repair_order,
    edit_shop,
    edit_shop_user_rights,
    invoice_create,
    invoice_detail,
    invoice_email,
    invoice_list,
    invoice_masterdata,
    invoice_print,
    invoice_price_table,
    landing_page,
    manage_shop_users,
    manage_inventory,
    schedule_inspection,
    shop_dashboard,
    shop_list,
    toggle_shop_active,
    view_reports,
)
from shops.views_workorder import work_order_list_create

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", landing_page, name="landing"),
    path("shop/", shop_dashboard, name="shop_dashboard"),
    path("shop/workorders/", work_order_list_create, name="work_order_list_create"),
    path("shop/repairs/new/", create_repair_order, name="create_repair_order"),
    path("shop/inspections/schedule/", schedule_inspection, name="schedule_inspection"),
    path("shop/inventory/", manage_inventory, name="manage_inventory"),
    path("shop/reports/", view_reports, name="view_reports"),
    path("shop/invoices/", invoice_list, name="invoice_list"),
    path("shop/invoices/new/", invoice_create, name="invoice_create"),
    path("shop/invoices/<int:invoice_id>/", invoice_detail, name="invoice_detail"),
    path("shop/invoices/<int:invoice_id>/email/", invoice_email, name="invoice_email"),
    path("shop/invoices/<int:invoice_id>/print/", invoice_print, name="invoice_print"),
    path("shop/invoices/price-table/", invoice_price_table, name="invoice_price_table"),
    path("shop/invoices/masterdata/", invoice_masterdata, name="invoice_masterdata"),
    path("shop/customers/", customer_list, name="customer_list"),
    path("shop/customers/new/", customer_create, name="customer_create"),
    path("shop/customers/<int:customer_id>/", customer_detail, name="customer_detail"),
    path("shop/customers/<int:customer_id>/edit/", customer_edit, name="customer_edit"),
    path("shop/customers/<int:customer_id>/delete/", customer_delete, name="customer_delete"),
    path(
        "shop/customers/<int:customer_id>/cars/new/",
        customer_car_create,
        name="customer_car_create",
    ),
    path(
        "shop/customers/<int:customer_id>/cars/<int:car_id>/edit/",
        customer_car_edit,
        name="customer_car_edit",
    ),
    path(
        "shop/customers/<int:customer_id>/cars/<int:car_id>/delete/",
        customer_car_delete,
        name="customer_car_delete",
    ),
    path(
        "shop/customers/<int:customer_id>/cars/<int:car_id>/labels/",
        customer_car_print_labels,
        name="customer_car_print_labels",
    ),
    path("api/vehicle/<str:plate>/", api_vehicle_lookup, name="api_vehicle_lookup"),
    path("shops/", shop_list, name="shop_list"),
    path("shops/new/", add_shop, name="add_shop"),
    path("shops/<int:shop_id>/edit/", edit_shop, name="edit_shop"),
    path("shops/<int:shop_id>/toggle-active/", toggle_shop_active, name="toggle_shop_active"),
    path("shops/<int:shop_id>/users/", manage_shop_users, name="manage_shop_users"),
    path(
        "shops/<int:shop_id>/users/<int:access_id>/edit/",
        edit_shop_user_rights,
        name="edit_shop_user_rights",
    ),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
