from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from shops.models import ShopUserAccess


def get_shop_context_for_user(user):
    """
    Resolve active shop context for a user.

    Returns a dict with shop/access/rights or None.
    """
    if not user.is_authenticated:
        return None

    shop_profile = getattr(user, "shop_profile", None)
    if shop_profile and shop_profile.is_active:
        return {
            "shop": shop_profile,
            "access": None,
            "is_owner": True,
            "rights": {
                "can_manage_users": True,
                "can_create_repair_order": True,
                "can_manage_inventory": True,
                "can_view_reports": True,
            },
        }

    access = (
        ShopUserAccess.objects.select_related("shop")
        .filter(user=user, is_active=True, shop__is_active=True)
        .order_by("created_at")
        .first()
    )
    if not access:
        return None

    return {
        "shop": access.shop,
        "access": access,
        "is_owner": False,
        "rights": {
            "can_manage_users": access.can_manage_users,
            "can_create_repair_order": access.can_create_repair_order,
            "can_manage_inventory": access.can_manage_inventory,
            "can_view_reports": access.can_view_reports,
        },
    }


def require_shop_right(required_right: str | None = None):
    """
    Ensure authenticated user has an active shop context and optional right.

    Staff users bypass rights checks.
    """

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.is_staff:
                return view_func(request, *args, **kwargs)

            context = get_shop_context_for_user(request.user)
            if not context:
                messages.error(request, "No active shop access was found for your account.")
                return redirect("landing")

            request.current_shop = context["shop"]
            request.current_shop_access = context["access"]
            request.current_shop_rights = context["rights"]

            if required_right and not context["rights"].get(required_right, False):
                return HttpResponseForbidden("You do not have permission for this shop function.")

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
