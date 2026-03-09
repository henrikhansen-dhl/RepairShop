from django.utils.deprecation import MiddlewareMixin
from django.utils import translation

from .tenant_db import ensure_tenant_database_alias
from .tenant_context import clear_current_db, set_current_db
from shops.models import ShopUserAccess


class TenantDatabaseMiddleware(MiddlewareMixin):
    """
    Resolve the tenant DB alias from the authenticated user and store it
    in thread-local storage for the duration of the request.
    """

    def process_request(self, request):
        clear_current_db()
        translation.deactivate_all()

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return

        preferred_language = "en"

        # ShopProfile lives in the shared/default DB.
        shop_profile = getattr(user, "shop_profile", None)
        if shop_profile and shop_profile.is_active:
            ensure_tenant_database_alias(shop_profile.database_name)
            set_current_db(shop_profile.database_name)

            owner_access = (
                ShopUserAccess.objects.select_related("shop")
                .filter(shop=shop_profile, user=user, is_active=True)
                .first()
            )
            if owner_access and owner_access.preferred_language:
                preferred_language = owner_access.preferred_language
            translation.activate(preferred_language)
            request.LANGUAGE_CODE = preferred_language
            return

        # Non-owner shop users are resolved from explicit access mapping.
        access = (
            ShopUserAccess.objects.select_related("shop")
            .filter(user=user, is_active=True, shop__is_active=True)
            .order_by("created_at")
            .first()
        )
        if access:
            ensure_tenant_database_alias(access.shop.database_name)
            set_current_db(access.shop.database_name)
            if access.preferred_language:
                preferred_language = access.preferred_language

        translation.activate(preferred_language)
        request.LANGUAGE_CODE = preferred_language

    def process_response(self, request, response):
        clear_current_db()
        translation.deactivate_all()
        return response

    def process_exception(self, request, exception):
        clear_current_db()
        translation.deactivate_all()
        return None
