from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from shops.models import ShopProfile, ShopUserAccess


def get_shop_feature_flags(shop):
    if not shop:
        return {}
    return {code: shop.has_feature(code) for code, _label in ShopProfile.FEATURE_CHOICES}


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
            "features": get_shop_feature_flags(shop_profile),
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
        "features": get_shop_feature_flags(access.shop),
        "rights": {
            "can_manage_users": access.can_manage_users,
            "can_create_repair_order": access.can_create_repair_order,
            "can_manage_inventory": access.can_manage_inventory,
            "can_view_reports": access.can_view_reports,
        },
    }


def apply_shop_context_to_request(request, context):
    """Attach resolved shop context to the current request object."""
    request.current_shop = context["shop"]
    request.current_shop_access = context["access"]
    request.current_shop_rights = context["rights"]
    request.current_shop_features = context.get("features", {})


def require_shop_right(required_right: str | None = None, required_feature: str | None = None):
    """
    Ensure authenticated user has an active shop context and optional right.

    Staff users bypass rights checks.
    """

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            context = get_shop_context_for_user(request.user)
            if context:
                apply_shop_context_to_request(request, context)

            if request.user.is_staff:
                if not context:
                    messages.error(request, "No active shop access was found for your account.")
                    return redirect("landing")
                return view_func(request, *args, **kwargs)

            if not context:
                messages.error(request, "No active shop access was found for your account.")
                return redirect("landing")

            if required_feature and not context.get("features", {}).get(required_feature, False):
                messages.error(request, "This function is not included in your shop subscription.")
                return redirect("shop_dashboard")

            if required_right and not context["rights"].get(required_right, False):
                return HttpResponseForbidden("You do not have permission for this shop function.")

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
