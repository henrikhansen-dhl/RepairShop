from shops.models import ShopMasterData
from repairshop.access_control import get_shop_context_for_user


def shop_branding(request):
    """Expose current shop master data and logo URL to templates."""
    shop = getattr(request, "current_shop", None)
    if not shop:
        shop_context = get_shop_context_for_user(getattr(request, "user", None))
        if shop_context:
            shop = shop_context.get("shop")

    if not shop:
        return {
            "current_shop_master_data": None,
            "current_shop_logo_url": "",
        }

    try:
        master_data = shop.master_data
    except ShopMasterData.DoesNotExist:
        master_data = None

    logo_url = ""
    if master_data and master_data.company_logo:
        logo_url = master_data.company_logo.url

    return {
        "current_shop_master_data": master_data,
        "current_shop_logo_url": logo_url,
    }
